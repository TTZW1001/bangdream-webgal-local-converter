from __future__ import annotations

import json
from pathlib import Path

from .models import AppConfig, CharacterConfig, SceneConfig


class ConfigError(ValueError):
    """Raised when local converter configuration is invalid."""


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing config file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc


def _load_scene_config(config_path: Path) -> tuple[dict[str, str], SceneConfig]:
    raw = _load_json(config_path / "scene_keywords.json")
    if "scenes" not in raw and "rules" not in raw and "aliases" not in raw and "time_markers" not in raw:
        legacy_keywords = {str(k): str(v) for k, v in raw.items()}
        return legacy_keywords, SceneConfig(legacy_keywords=legacy_keywords)

    legacy_raw = raw.get("legacy_keywords", {})
    legacy_file = raw.get("legacy_file")
    if legacy_file:
        legacy_path = config_path / str(legacy_file)
        legacy_from_file = _load_json(legacy_path)
        if not isinstance(legacy_from_file, dict):
            raise ConfigError(f"Legacy scene config must be a JSON object: {legacy_path}")
        legacy_raw = legacy_from_file

    legacy_keywords = {str(k): str(v) for k, v in legacy_raw.items()}
    scene_config = SceneConfig(
        scenes={str(k): v for k, v in raw.get("scenes", {}).items()},
        aliases={str(k): str(v) for k, v in raw.get("aliases", {}).items()},
        rules={str(k): str(v) for k, v in raw.get("rules", {}).items()},
        time_markers={
            str(label): [str(marker) for marker in markers]
            for label, markers in raw.get("time_markers", {}).items()
        },
        legacy_keywords=legacy_keywords,
    )
    return legacy_keywords, scene_config


def load_config(config_dir: str | Path) -> AppConfig:
    config_path = Path(config_dir)
    aliases_raw = _load_json(config_path / "aliases.json")
    characters_raw = _load_json(config_path / "characters.json")
    scene_keywords, scene_config = _load_scene_config(config_path)

    aliases = {str(k): str(v) for k, v in aliases_raw.items()}
    characters: dict[str, CharacterConfig] = {}
    for character_id, data in characters_raw.items():
        characters[str(character_id)] = CharacterConfig(
            character_id=str(character_id),
            display_name=str(data.get("display_name") or character_id),
            full_name=str(data.get("full_name") or data.get("display_name") or character_id),
            band=data.get("band"),
            generic_character_id=data.get("generic_character_id"),
            default_expression=str(data.get("default_expression") or "default"),
            default_motion_31=str(data.get("default_motion_31") or "idle01"),
            default_motion_generic=str(data.get("default_motion_generic") or "idle01"),
            default_model_31=data.get("default_model_31"),
            default_model_generic=data.get("default_model_generic"),
            models_31={str(k): str(v) for k, v in data.get("models_31", {}).items()},
            models_generic={str(k): str(v) for k, v in data.get("models_generic", {}).items()},
        )

    unknown_aliases = sorted({target for target in aliases.values() if target not in characters})
    if unknown_aliases:
        raise ConfigError("Alias table references missing characters: " + ", ".join(unknown_aliases))

    return AppConfig(
        aliases=aliases,
        characters=characters,
        scene_keywords=scene_keywords,
        scene_config=scene_config,
    )
