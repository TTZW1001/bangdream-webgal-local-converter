from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
