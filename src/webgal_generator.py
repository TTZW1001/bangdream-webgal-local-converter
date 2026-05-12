from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from .models import AppConfig, PendingItem, ResolvedSegment, SegmentKind
from .scene_detector import SceneDetector


@dataclass
class GenerationState:
    # Runtime state for one script generation pass. Keeping these fields in a
    # single object makes it easier to evolve background and figure handling
    # independently without threading many local variables through helpers.
    lines: list[str] = field(default_factory=list)
    shown_figures: set[str] = field(default_factory=set)
    shown_order: list[str] = field(default_factory=list)
    figure_positions: dict[str, str] = field(default_factory=dict)
    missing_figure_warnings: set[str] = field(default_factory=set)
    current_background: str | None = None
    current_school_context: str | None = None
    figure_event_index: int = 0
    segment_locked_background: str | None = None


class WebGALGenerator:
    # These marker groups decide when narration should affect stage state,
    # scene switching, or home-scene inference. They are intentionally narrow
    # so the generator stays predictable on prose-heavy text.
    MENTAL_REFERENCE_MARKERS = ("脑海里", "浮现", "闪过", "心里", "想着", "想象", "回忆")
    NARRATION_STAGE_MARKERS = (
        "走进",
        "进来",
        "来到",
        "走到",
        "凑了上来",
        "凑上来",
        "抱着",
        "推开",
        "倒进",
        "坐在",
        "站在",
    )
    HOME_SCENE_MARKERS = ("床", "枕头", "睡着", "房间里", "躺在床上", "倒进床里", "摘下头套", "换上自己的便装")
    STAGE_SCENE_MARKERS = ("舞台", "后台", "谢幕", "观众席", "米歇尔", "散场后台", "临时舞台")
    NIGHT_PARK_MARKERS = ("夜风", "夜色", "晚上", "夜晚", "天色已晚")
    CHARACTER_SCHOOL_HINTS = {
        "kasumi": "花咲川",
        "tae": "花咲川",
        "rimi": "花咲川",
        "saya": "花咲川",
        "arisa": "花咲川",
        "kokoro": "花咲川",
        "kaoru": "花咲川",
        "hagumi": "花咲川",
        "kanon": "花咲川",
        "misaki": "花咲川",
        "mashiro": "花咲川",
        "toko": "花咲川",
        "nanami": "花咲川",
        "tsukushi": "花咲川",
        "rui": "花咲川",
        "taki": "花咲川",
        "umiri": "花咲川",
        "uika": "花咲川",
        "mana": "花咲川",
        "ran": "羽丘",
        "moca": "羽丘",
        "himari": "羽丘",
        "tomoe": "羽丘",
        "tsugumi": "羽丘",
        "aya": "羽丘",
        "hina": "羽丘",
        "chisato": "羽丘",
        "maya": "羽丘",
        "eve": "羽丘",
        "yukina": "羽丘",
        "sayo": "羽丘",
        "lisa": "羽丘",
        "ako": "羽丘",
        "rinko": "羽丘",
        "layer": "羽丘",
        "lock": "羽丘",
        "masuki": "羽丘",
        "pareo": "羽丘",
        "anon": "羽丘",
        "rana": "羽丘",
        "mutsumi": "月之森",
        "sakiko": "月之森",
    }

    def __init__(
        self,
        config: AppConfig,
        resource_mode: str = "generic",
        model_overrides: dict[str, str] | None = None,
        scene_school: str = "auto",
        scene_lock: str | None = None,
        segment_scene_locks: dict[int, str] | None = None,
        figure_controls: dict[str, dict[str, str]] | None = None,
        figure_event_overrides: dict[int, dict[str, str]] | None = None,
        auto_change_background: bool = True,
        insert_figure_on_first_appearance: bool = True,
        fallback_background: str = "纯黑.png",
    ) -> None:
        self.config = config
        self.resource_mode = resource_mode
        self.model_overrides = model_overrides or {}
        self.scene_school = scene_school
        self.scene_lock = scene_lock.strip() if scene_lock else None
        self.segment_scene_locks = segment_scene_locks or {}
        self.figure_controls = figure_controls or {}
        self.figure_event_overrides = figure_event_overrides or {}
        self.auto_change_background = auto_change_background
        self.insert_figure_on_first_appearance = insert_figure_on_first_appearance
        self.fallback_background = fallback_background
        self.scene_detector = SceneDetector(config)
        self.project_root = Path(__file__).resolve().parents[1]
        self.generic_figure_root = self.project_root.parent / "游戏内资源示例" / "figure（适用于全角色）"
        self.figure_31_root = self.project_root.parent / "游戏内资源示例" / "figure（仅适用于3.1版本引擎自带的mygo&mujica）"

    def generate(self, segments: list[ResolvedSegment], pending: list[PendingItem] | None = None) -> tuple[str, list[PendingItem]]:
        # Generation walks resolved segments once while maintaining two kinds
        # of state: current background and currently visible figures.
        pending_items = list(pending or [])
        state = GenerationState()
        locked_background = self._resolve_scene_lock(self.scene_lock)
        self._initialize_background(segments, locked_background, state)

        for segment_order, segment in enumerate(segments):
            self._apply_segment_scene_lock(segment_order, locked_background, state)
            self._maybe_update_background_for_narration(segment, locked_background, state)
            self._maybe_stage_narration_characters(segment, segment_order, pending_items, state)

            if segment.kind == SegmentKind.NARRATION:
                state.lines.append(f":{segment.text};")
                continue

            if not segment.speaker_id:
                display_name = segment.speaker_name or self._unknown_display_name(segment)
                state.lines.append(f"{display_name}:{segment.text};")
                continue

            character = self.config.characters.get(segment.speaker_id)
            if character is None:
                display_name = segment.speaker_name or segment.speaker_id
                state.lines.append(f"{display_name}:{segment.text};")
                continue

            if not self._maybe_stage_speaking_character(segment, segment_order, character.display_name, pending_items, state):
                continue
            display_name = segment.speaker_name or character.display_name
            state.lines.append(f"{display_name}:{segment.text} -id -figureId={segment.speaker_id};")

        return "\n".join(state.lines) + "\n", pending_items

    def _narration_stage_mentions(self, segment: ResolvedSegment) -> list[str]:
        # Only let concrete stage-action narration bring figures on screen.
        # Mental references should not summon characters into the scene.
        if any(marker in segment.text for marker in self.MENTAL_REFERENCE_MARKERS):
            return []
        if not any(marker in segment.text for marker in self.NARRATION_STAGE_MARKERS):
            return []
        return segment.mentioned_character_ids[:1]

    def _detect_home_background(self, segment: ResolvedSegment) -> str | None:
        # Home-scene detection is a small overlay above generic scene rules:
        # room/bed/home wording often conveys stronger location evidence than a
        # broad school keyword left over from earlier narration.
        if any(marker in segment.text for marker in self.MENTAL_REFERENCE_MARKERS):
            return None
        if "公园" in segment.text and any(marker in segment.text for marker in self.NIGHT_PARK_MARKERS):
            return "公园/公园1（晚上）.png"
        if not any(marker in segment.text for marker in self.HOME_SCENE_MARKERS):
            return None
        if any(marker in segment.text for marker in self.STAGE_SCENE_MARKERS):
            return None
        candidate_ids = list(segment.mentioned_character_ids)
        if segment.speaker_id and segment.speaker_id not in candidate_ids:
            candidate_ids.insert(0, segment.speaker_id)
        for character_id in candidate_ids:
            character = self.config.characters.get(character_id)
            if not character:
                continue
            name_variants = [character.display_name]
            if len(character.display_name) >= 2:
                name_variants.append(character.display_name[-2:])
            for variant in name_variants:
                room_background = self.config.scene_keywords.get(f"{variant}的房间")
                if room_background:
                    return room_background
                for keyword, background in self.config.scene_keywords.items():
                    if variant in keyword and "房间" in keyword:
                        return background
        return None

    def _initialize_background(
        self,
        segments: list[ResolvedSegment],
        locked_background: str | None,
        state: GenerationState,
    ) -> None:
        if locked_background:
            state.current_background = locked_background
            state.lines.append(f"changeBg:{state.current_background} -next;")
            return
        if 0 in self.segment_scene_locks:
            state.segment_locked_background = self._resolve_scene_lock(self.segment_scene_locks[0])
            if state.segment_locked_background:
                state.current_background = state.segment_locked_background
                state.lines.append(f"changeBg:{state.current_background} -next;")
                return
        if not self.auto_change_background:
            return
        # Initial background uses the first few segments so the output starts
        # with a plausible scene before later narration refines it.
        initial_school = self._school_for_segments(segments[:6])
        state.current_school_context = initial_school
        first_background = self.scene_detector.detect_initial(
            [segment.raw for segment in segments],
            school_context=initial_school,
        )
        state.current_background = first_background or self.fallback_background
        state.lines.append(f"changeBg:{state.current_background} -next;")

    def _apply_segment_scene_lock(
        self,
        segment_order: int,
        locked_background: str | None,
        state: GenerationState,
    ) -> None:
        if segment_order not in self.segment_scene_locks or locked_background:
            return
        requested_background = self._resolve_scene_lock(self.segment_scene_locks[segment_order])
        state.segment_locked_background = requested_background
        if requested_background and requested_background != state.current_background:
            self._close_all_figures(state)
            state.current_background = requested_background
            state.lines.append(f"changeBg:{state.current_background} -next;")

    def _maybe_update_background_for_narration(
        self,
        segment: ResolvedSegment,
        locked_background: str | None,
        state: GenerationState,
    ) -> None:
        if (
            not self.auto_change_background
            or locked_background
            or state.segment_locked_background
            or segment.kind != SegmentKind.NARRATION
        ):
            return
        # Only narration drives automatic scene switching. This keeps a
        # dialogue line that merely mentions another place from causing a
        # sudden background jump.
        school_context = self._school_for_segment(segment) or state.current_school_context
        if school_context:
            state.current_school_context = school_context
        home_background = self._detect_home_background(segment)
        detected_background = home_background or self.scene_detector.detect(
            segment.raw,
            state.current_background,
            school_context=school_context,
        )
        if detected_background and detected_background != state.current_background:
            self._close_all_figures(state)
            state.current_background = detected_background
            state.lines.append(f"changeBg:{state.current_background} -next;")

    def _maybe_stage_narration_characters(
        self,
        segment: ResolvedSegment,
        segment_order: int,
        pending_items: list[PendingItem],
        state: GenerationState,
    ) -> None:
        if not self.insert_figure_on_first_appearance or segment.kind != SegmentKind.NARRATION:
            return
        # Narration can also stage a character before they speak. This makes
        # prose like "美咲走进来" show the figure early.
        for mentioned_id in self._narration_stage_mentions(segment):
            self._stage_character_if_needed(mentioned_id, segment, segment_order, pending_items, state)

    def _maybe_stage_speaking_character(
        self,
        segment: ResolvedSegment,
        segment_order: int,
        display_name: str,
        pending_items: list[PendingItem],
        state: GenerationState,
    ) -> bool:
        if not self.insert_figure_on_first_appearance or segment.speaker_id in state.shown_figures:
            return True
        speaker_id = segment.speaker_id
        if speaker_id is None:
            return True
        # Dialogue-triggered figure insertion is the fallback when a character
        # was not already staged by narration.
        if self._figure_visibility(speaker_id) == "hide":
            state.lines.append(f"{display_name}:{segment.text} -id -figureId={speaker_id};")
            return False
        self._stage_character_if_needed(speaker_id, segment, segment_order, pending_items, state)
        # Even if staging fails because no valid figure asset exists, keep the
        # dialogue line itself. Missing figures should degrade gracefully.
        return True

    def _stage_character_if_needed(
        self,
        character_id: str,
        segment: ResolvedSegment,
        segment_order: int,
        pending_items: list[PendingItem],
        state: GenerationState,
    ) -> bool:
        if character_id in state.shown_figures or character_id not in self.config.characters:
            return True
        if self._figure_visibility(character_id) == "hide":
            return True
        position = self._position_for(character_id, state.figure_positions)
        figure_line = self._figure_line(character_id, position, state.figure_event_index)
        if figure_line:
            self._make_room_for_figure(state)
            state.lines.append(figure_line)
            state.figure_event_index += 1
            state.shown_figures.add(character_id)
            state.shown_order.append(character_id)
            state.figure_positions[character_id] = position
            return True
        self._append_missing_figure_warning(character_id, segment, segment_order, pending_items, state)
        return False

    def _append_missing_figure_warning(
        self,
        character_id: str,
        segment: ResolvedSegment,
        segment_order: int,
        pending_items: list[PendingItem],
        state: GenerationState,
    ) -> None:
        if character_id in state.missing_figure_warnings:
            return
        state.missing_figure_warnings.add(character_id)
        pending_items.append(
            PendingItem(
                index=segment.index,
                raw=segment.raw,
                issue_type="立绘缺省",
                suggestion=f"角色 {character_id} 当前没有可用本地立绘，已只输出文本。",
                segment_index=segment_order,
            )
        )

    def _unknown_display_name(self, segment: ResolvedSegment) -> str:
        if segment.speaker_hint:
            hint = segment.speaker_hint.strip().rstrip(":：")
            if "老师" in hint:
                return "老师"
            compact = re.sub(r"[，,。！？、\s].*$", "", hint)
            if compact:
                return compact[-8:]
            return hint[-8:]
        return "未知"

    def _close_all_figures(self, state: GenerationState) -> None:
        # WebGAL keeps visual state until explicitly cleared, so any hard scene
        # switch must also clear staged figures to avoid ghost carry-over.
        for character_id in list(state.shown_figures):
            state.lines.append(f"changeFigure: -id={character_id} -next;")
        state.shown_figures.clear()
        state.shown_order.clear()
        state.figure_positions.clear()

    def _make_room_for_figure(self, state: GenerationState) -> None:
        # The current UI targets at most two simultaneous on-screen figures, so
        # later entries push out the oldest visible character.
        while len(state.shown_order) >= 2:
            character_id = state.shown_order.pop(0)
            if character_id in state.shown_figures:
                state.lines.append(f"changeFigure: -id={character_id} -next;")
                state.shown_figures.remove(character_id)
                state.figure_positions.pop(character_id, None)

    def _position_for(self, character_id: str, figure_positions: dict[str, str]) -> str:
        forced_position = self._figure_control_value(character_id, "position")
        if forced_position in {"-left", "-right"}:
            return forced_position
        if character_id in figure_positions:
            return figure_positions[character_id]
        used = set(figure_positions.values())
        if "-left" not in used:
            return "-left"
        if "-right" not in used:
            return "-right"
        return "-left"

    def _figure_line(self, character_id: str, position: str, figure_event_index: int) -> str | None:
        # Figure selection merges several override layers:
        # single-line override -> per-character control -> global override ->
        # default model for the chosen resource mode -> filesystem fallback.
        character = self.config.characters[character_id]
        event_override = self.figure_event_overrides.get(figure_event_index, {})
        model_key = event_override.get("model_key") or self._figure_control_value(character_id, "model_key") or self.model_overrides.get(character_id)
        mode = self._mode_for(character_id, model_key)
        explicit_model_selected = False
        if mode == "31":
            model = character.default_model_31
            if model_key and model_key in character.models_31:
                model = character.models_31[model_key]
                explicit_model_selected = True
            motion = event_override.get("motion") or character.default_motion_31
            root = self.figure_31_root
        else:
            model = character.default_model_generic
            if model_key and model_key in character.models_generic:
                model = character.models_generic[model_key]
                explicit_model_selected = True
            motion = event_override.get("motion") or character.default_motion_generic
            root = self.generic_figure_root

        # When the caller explicitly names a model key, treat that config as
        # authoritative and emit the requested asset path even if the local
        # sample resource pack does not contain it. Existence probing is still
        # useful for implicit defaults and fallbacks.
        if not model or (not explicit_model_selected and not self._model_exists(root, model)):
            fallback_model = self._first_available_model(character, mode, root, preferred_key=model_key)
            if not fallback_model:
                return None
            model = fallback_model

        if not explicit_model_selected and not self._model_exists(root, model):
            return None

        expression = event_override.get("expression") or character.default_expression or "default"
        position = event_override.get("position") or position
        return (
            f"changeFigure:{model} -id={character_id} "
            f"-motion={motion} -expression={expression} {position} -next;"
        )

    def _model_exists(self, root: Path, model: str) -> bool:
        return (root / model.replace("/", "\\")).exists()

    def _first_available_model(
        self,
        character,
        mode: str,
        root: Path,
        preferred_key: str | None = None,
    ) -> str | None:
        # Fallback ordering prefers the most common everyday variants first so
        # missing default models still degrade to something visually plausible.
        model_map = character.models_31 if mode == "31" else character.models_generic
        ordered_keys: list[str] = []
        if preferred_key and preferred_key in model_map:
            ordered_keys.append(preferred_key)
        ordered_keys.extend(
            key
            for key in ("school_winter", "school_summer", "casual_winter", "casual_summer", "casual", "live")
            if key in model_map and key not in ordered_keys
        )
        ordered_keys.extend(key for key in model_map if key not in ordered_keys)
        for key in ordered_keys:
            model = model_map.get(key)
            if model and self._model_exists(root, model):
                return model
        return None

    def _mode_for(self, character_id: str, model_key: str | None = None) -> str:
        # `auto` mode prefers 3.1 assets when the configured default actually
        # exists on disk; otherwise it gracefully falls back to generic assets.
        character = self.config.characters[character_id]
        if model_key:
            if self.resource_mode == "31" and model_key in character.models_31:
                return "31"
            if self.resource_mode == "generic" and model_key in character.models_generic:
                return "generic"
            if model_key in character.models_31:
                return "31"
            if model_key in character.models_generic:
                return "generic"
        if self.resource_mode in {"31", "generic"}:
            return self.resource_mode
        if character.default_model_31 and self._model_exists(self.figure_31_root, character.default_model_31):
            return "31"
        return "generic"

    def _resolve_scene_lock(self, scene_lock: str | None) -> str | None:
        if not scene_lock:
            return None
        normalized = scene_lock.strip()
        if not normalized or normalized == "auto":
            return None
        scene_id = self.config.scene_config.aliases.get(normalized) or self.config.scene_config.rules.get(normalized)
        if scene_id:
            background = self.scene_detector._resolve_scene_background(scene_id, normalized, self.scene_school, None)
            if background:
                return background
        direct = self.config.scene_keywords.get(normalized)
        if direct:
            return direct
        for keyword, background in sorted(self.config.scene_keywords.items(), key=lambda item: len(item[0]), reverse=True):
            if normalized in keyword:
                return background
        return normalized

    def _figure_visibility(self, character_id: str) -> str:
        return self._figure_control_value(character_id, "visibility") or "auto"

    def _figure_control_value(self, character_id: str, key: str) -> str | None:
        character_control = self.figure_controls.get(character_id, {})
        if key in character_control:
            return character_control[key]
        return self.figure_controls.get("__all__", {}).get(key)

    def _school_for_segments(self, segments: list[ResolvedSegment]) -> str | None:
        character_ids: list[str] = []
        for segment in segments:
            if segment.speaker_id:
                character_ids.append(segment.speaker_id)
            character_ids.extend(segment.mentioned_character_ids)
        return self._school_for_character_ids(character_ids)

    def _school_for_segment(self, segment: ResolvedSegment) -> str | None:
        character_ids = list(segment.mentioned_character_ids)
        if segment.speaker_id:
            character_ids.append(segment.speaker_id)
        return self._school_for_character_ids(character_ids)

    def _school_for_character_ids(self, character_ids: list[str]) -> str | None:
        # School context is only a soft heuristic for generic school scenes,
        # so explicit UI selection still overrides all inferred counts.
        if self.scene_school != "auto":
            return self.scene_school
        counts: dict[str, int] = {}
        for character_id in character_ids:
            school = self.CHARACTER_SCHOOL_HINTS.get(character_id)
            if school:
                counts[school] = counts.get(school, 0) + 1
        if not counts:
            return None
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
