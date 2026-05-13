from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SegmentKind(str, Enum):
    NARRATION = "narration"
    DIALOGUE = "dialogue"


@dataclass
class CharacterConfig:
    character_id: str
    display_name: str
    full_name: str
    band: str | None = None
    generic_character_id: str | None = None
    default_expression: str = "default"
    default_motion_31: str = "idle01"
    default_motion_generic: str = "idle01"
    default_model_31: str | None = None
    default_model_generic: str | None = None
    models_31: dict[str, str] = field(default_factory=dict)
    models_generic: dict[str, str] = field(default_factory=dict)


@dataclass
class SceneConfig:
    scenes: dict[str, dict] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    rules: dict[str, str] = field(default_factory=dict)
    time_markers: dict[str, list[str]] = field(default_factory=dict)
    legacy_keywords: dict[str, str] = field(default_factory=dict)


@dataclass
class AppConfig:
    aliases: dict[str, str]
    characters: dict[str, CharacterConfig]
    scene_keywords: dict[str, str]
    scene_config: SceneConfig = field(default_factory=SceneConfig)


@dataclass
class TextSegment:
    kind: SegmentKind
    text: str
    raw: str
    index: int
    speaker_hint: str | None = None


@dataclass
class ResolvedSegment:
    kind: SegmentKind
    text: str
    raw: str
    index: int
    speaker_id: str | None = None
    speaker_name: str | None = None
    speaker_hint: str | None = None
    mentioned_character_ids: list[str] = field(default_factory=list)


@dataclass
class PendingItem:
    index: int
    raw: str
    issue_type: str
    suggestion: str
    segment_index: int | None = None


@dataclass
class ConversionResult:
    script: str
    pending_items: list[PendingItem]
    segments: list[ResolvedSegment]


@dataclass
class FigureModelEntry:
    model_key: str
    model_path: str
    resource_type: str
    character_dir_name: str
    motions: list[str] = field(default_factory=list)
    expressions: list[str] = field(default_factory=list)


@dataclass
class FigureCharacterEntry:
    source_name: str
    mapped_character_id: str | None = None
    mapping_source: str | None = None
    models: dict[str, FigureModelEntry] = field(default_factory=dict)


@dataclass
class FigureResourceIndex:
    root_dir: Path
    characters: dict[str, FigureCharacterEntry] = field(default_factory=dict)

    @property
    def total_characters(self) -> int:
        return len(self.characters)

    @property
    def total_models(self) -> int:
        return sum(len(entry.models) for entry in self.characters.values())

    @property
    def mapped_characters(self) -> int:
        return sum(1 for entry in self.characters.values() if entry.mapped_character_id)

    @property
    def unmapped_characters(self) -> list[str]:
        return sorted(
            entry.source_name
            for entry in self.characters.values()
            if not entry.mapped_character_id
        )

    def summary_text(self) -> str:
        if not self.characters:
            return "未扫描到可识别的 figure 资源"
        resource_types = {
            model.resource_type
            for entry in self.characters.values()
            for model in entry.models.values()
        }
        type_label = " / ".join(sorted(resource_types)) if resource_types else "unknown"
        return (
            f"角色 {self.total_characters} 个，模型 {self.total_models} 个，"
            f"已映射 {self.mapped_characters} 个，资源类型：{type_label}"
        )

    def models_for_character_id(self, character_id: str) -> dict[str, FigureModelEntry]:
        results: dict[str, FigureModelEntry] = {}
        for entry in self.characters.values():
            if entry.mapped_character_id != character_id:
                continue
            for model_key, model in entry.models.items():
                option_key = f"{entry.source_name}/{model_key}"
                results[option_key] = model
        return results
