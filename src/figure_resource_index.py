from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import AppConfig, FigureCharacterEntry, FigureModelEntry, FigureResourceIndex


def scan_figure_directory(
    root_dir: str | Path,
    config: AppConfig,
    manual_mappings: dict[str, str] | None = None,
) -> FigureResourceIndex:
    """Scan a user-selected figure root and build a unified resource index."""

    root_path = Path(root_dir)
    index = FigureResourceIndex(root_dir=root_path)
    mapper = _CharacterMapper(config)
    manual_mappings = manual_mappings or {}

    if not root_path.exists() or not root_path.is_dir():
        return index

    for child in sorted(root_path.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        mapped_character_id, mapping_source = _resolve_character_mapping(
            child.name,
            mapper,
            manual_mappings,
        )
        character_entry = FigureCharacterEntry(
            source_name=child.name,
            mapped_character_id=mapped_character_id,
            mapping_source=mapping_source,
        )
        _merge_models(character_entry.models, _scan_live2d_models(root_path, child))
        _merge_models(character_entry.models, _scan_legacy_model_jsons(root_path, child))
        _merge_models(character_entry.models, _scan_legacy_models(root_path, child))
        if character_entry.models:
            index.characters[child.name] = character_entry

    return index


def _merge_models(target: dict[str, FigureModelEntry], items: dict[str, FigureModelEntry]) -> None:
    for model_key, model in items.items():
        if model_key not in target:
            target[model_key] = model
            continue
        existing = target[model_key]
        existing.motions = sorted(set(existing.motions).union(model.motions))
        existing.expressions = sorted(set(existing.expressions).union(model.expressions))


@dataclass
class _CharacterMapper:
    config: AppConfig

    def __post_init__(self) -> None:
        self.lookup: dict[str, str] = {}
        for character_id, character in self.config.characters.items():
            for candidate in {
                character_id,
                character.display_name,
                character.full_name,
            }:
                normalized = _normalize_name(candidate)
                if normalized:
                    self.lookup.setdefault(normalized, character_id)
        for alias, character_id in self.config.aliases.items():
            normalized = _normalize_name(alias)
            if normalized:
                self.lookup.setdefault(normalized, character_id)

    def match_character_id(self, source_name: str) -> str | None:
        normalized = _normalize_name(source_name)
        if not normalized:
            return None
        if normalized in self.lookup:
            return self.lookup[normalized]

        # Try a slightly looser match for names that add spaces, underscores, or separators.
        collapsed = re.sub(r"[_\-.]+", "", normalized)
        if collapsed in self.lookup:
            return self.lookup[collapsed]
        return None


def _resolve_character_mapping(
    source_name: str,
    mapper: _CharacterMapper,
    manual_mappings: dict[str, str],
) -> tuple[str | None, str | None]:
    manual_value = str(manual_mappings.get(source_name, "")).strip()
    if manual_value and manual_value in mapper.config.characters:
        return manual_value, "manual"
    matched = mapper.match_character_id(source_name)
    if matched:
        return matched, "auto"
    return None, None


def _normalize_name(value: str) -> str:
    normalized = value.casefold().strip()
    normalized = re.sub(r"[\s\u3000]+", "", normalized)
    normalized = re.sub(r"[()（）\[\]{}·•'\"`~!@#$%^&*,，。！？；：/\\|<>+=]+", "", normalized)
    return normalized


def _scan_live2d_models(root_path: Path, character_dir: Path) -> dict[str, FigureModelEntry]:
    models: dict[str, FigureModelEntry] = {}
    for model_json in character_dir.rglob("model.json"):
        if any(part.startswith(".") for part in model_json.relative_to(character_dir).parts):
            continue
        if ".mtn_exp" in model_json.parts:
            continue
        model_dir = model_json.parent
        relative_model = model_dir.relative_to(root_path).as_posix()
        model_key = model_dir.name
        payload = _safe_load_json(model_json)
        motions = _extract_live2d_names(payload, "motions")
        expressions = _extract_live2d_names(payload, "expressions")
        models[model_key] = FigureModelEntry(
            model_key=model_key,
            model_path=f"{relative_model}/model.json",
            resource_type="live2d_json",
            character_dir_name=character_dir.name,
            motions=motions or ["idle01"],
            expressions=expressions or ["default"],
        )
    return models


def _scan_legacy_models(root_path: Path, character_dir: Path) -> dict[str, FigureModelEntry]:
    grouped: dict[str, dict[str, set[str] | str]] = {}
    for png_file in character_dir.rglob("*.png"):
        if any(part.startswith(".") for part in png_file.relative_to(character_dir).parts):
            continue
        if _belongs_to_legacy_model_json_tree(png_file, character_dir):
            continue
        if _is_live2d_texture_asset(png_file, character_dir):
            # Live2D texture atlases belong to a model.json tree and should
            # never be mistaken for legacy still-image figure assets.
            continue
        if png_file.parent == character_dir:
            model_key = "default"
        else:
            model_key = png_file.parent.name
        motion, expression = _parse_legacy_motion_expression(png_file.stem)
        relative_path = png_file.relative_to(root_path).as_posix()
        bucket = grouped.setdefault(
            model_key,
            {
                "motions": set(),
                "expressions": set(),
                "path": relative_path,
            },
        )
        bucket["motions"].add(motion)
        bucket["expressions"].add(expression)
    models: dict[str, FigureModelEntry] = {}
    for model_key, payload in grouped.items():
        models[model_key] = FigureModelEntry(
            model_key=model_key,
            model_path=str(payload["path"]),
            resource_type="legacy",
            character_dir_name=character_dir.name,
            motions=sorted(payload["motions"]),
            expressions=sorted(payload["expressions"]),
        )
    return models


def _scan_legacy_model_jsons(root_path: Path, character_dir: Path) -> dict[str, FigureModelEntry]:
    models: dict[str, FigureModelEntry] = {}
    pattern = re.compile(r"^(?P<prefix>\d+_)?(?P<model>.+?)model$", re.IGNORECASE)
    for model_json in character_dir.glob("*model.json"):
        if not model_json.is_file():
            continue
        match = pattern.match(model_json.stem)
        if not match:
            continue
        model_key = match.group("model")
        payload = _safe_load_json(model_json)
        motions = _extract_live2d_names(payload, "motions")
        expressions = _extract_live2d_names(payload, "expressions")
        models[model_key] = FigureModelEntry(
            model_key=model_key,
            model_path=model_json.relative_to(root_path).as_posix(),
            resource_type="legacy_json",
            character_dir_name=character_dir.name,
            motions=motions or ["idle01"],
            expressions=expressions or ["default"],
        )
    return models


def _is_live2d_texture_asset(png_file: Path, character_dir: Path) -> bool:
    if not re.fullmatch(r"texture_\d+", png_file.stem.casefold()):
        return False
    current = png_file.parent
    while True:
        if (current / "model.json").exists():
            return True
        if current == character_dir:
            return False
        if current.parent == current:
            return False
        current = current.parent


def _belongs_to_legacy_model_json_tree(png_file: Path, character_dir: Path) -> bool:
    current = png_file.parent
    while True:
        json_candidates = list(current.glob("*model.json"))
        if json_candidates:
            return True
        if current == character_dir:
            return False
        if current.parent == current:
            return False
        current = current.parent


def _parse_legacy_motion_expression(stem: str) -> tuple[str, str]:
    tokens = [token for token in re.split(r"[_\-.]+", stem) if token]
    if not tokens:
        return "idle01", "default"
    if len(tokens) == 1:
        return tokens[0], "default"
    return tokens[0], tokens[1]


def _safe_load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _extract_live2d_names(payload: dict, key: str) -> list[str]:
    values = payload.get(key)
    if isinstance(values, dict):
        if key == "motions":
            direct_names = [str(name).strip() for name in values.keys() if str(name).strip()]
            if direct_names:
                return sorted(set(direct_names))
        candidates = values.values()
    elif isinstance(values, list):
        candidates = values
    else:
        return []

    names: list[str] = []
    for item in candidates:
        names.extend(_extract_name_candidates(item))
    return sorted({name for name in names if name})


def _extract_name_candidates(item: object) -> list[str]:
    if isinstance(item, str):
        return [_basename_without_extension(item)]
    if isinstance(item, list):
        results: list[str] = []
        for nested in item:
            results.extend(_extract_name_candidates(nested))
        return results
    if not isinstance(item, dict):
        return []
    for field in ("Name", "name", "File", "file", "Path", "path"):
        raw = item.get(field)
        if isinstance(raw, str):
            return [_basename_without_extension(raw)]
    return []


def _basename_without_extension(raw: str) -> str:
    value = raw.replace("\\", "/").rstrip("/")
    value = value.rsplit("/", 1)[-1]
    for suffix in (".motion3.json", ".exp3.json", ".json", ".png"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    if "." in value:
        value = value.rsplit(".", 1)[0]
    return value
