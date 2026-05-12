from __future__ import annotations

from .models import AppConfig


class SceneDetector:
    # Time-only markers stay separate from location rules so phrases like
    # "放学后" refine a school scene's time of day without hard-coding one
    # particular campus into the keyword table.
    TIME_ONLY_KEYWORDS = {"清晨", "黄昏", "夕阳", "晚上", "夜晚", "雨天", "雨夜", "雪天"}
    DEFAULT_TIME_MARKERS = {
        "清晨": ["清晨", "黎明", "天刚亮", "一早"],
        "黄昏": ["放学后", "隔天放学后", "傍晚", "黄昏", "夕阳"],
        "夜晚": ["晚上", "夜晚", "深夜", "夜里", "入夜"],
        "雨天": ["雨天", "下雨", "雨幕"],
        "雨夜": ["雨夜"],
        "雪天": ["雪天", "下雪"],
    }
    SCHOOL_NAMES = ("羽丘", "花咲川", "月之森")
    MENTAL_SCENE_MARKERS = {"脑海里", "浮现", "闪过", "心里", "想着", "想起", "想象", "回忆起"}
    DISCUSSION_SCENE_MARKERS = {
        "企划",
        "计划",
        "设定",
        "怎么实现",
        "如何",
        "阻止",
        "讨论",
        "这件事",
        "这种事情",
        "才行",
    }
    LOCATION_TRANSITION_MARKERS = {"走进", "进来", "来到", "走到", "站在", "门口", "到齐", "集合", "回到", "来到"}
    BOUNDARY_CHARS = " \t\r\n,，。！？!?；;：“”\"'（）()【】[]《》<>、-—~…"
    STAGE_PERSIST_MARKERS = {"舞台", "观众席", "谢幕", "米歇尔", "演出", "临时舞台"}
    BACKSTAGE_ROOM_MARKERS = {"散场后台", "专属房间", "摘下头套", "黑衣人", "换上自己的便装", "换好衣服", "换衣服"}
    BACKSTAGE_HALLWAY_MARKERS = {"走廊拐角", "走出房间", "拐角", "走廊"}
    GENERIC_SCENE_SUFFIX_GROUPS = (
        ("的房间", "房间", "卧室"),
        ("家客厅", "客厅", "家里", "家中"),
        ("家门口", "门口", "入口"),
        ("家外部", "家外", "家前", "家外景"),
        ("家侧门", "侧门"),
        ("家正门", "正门"),
        ("家玄关", "玄关", "门厅"),
        ("家楼梯", "楼梯", "楼道"),
        ("家阳台", "阳台", "露台"),
        ("家中庭", "中庭", "院子"),
        ("前台", "大厅"),
        ("后台", "后场"),
        ("休息室", "休息区"),
    )
    SCENE_ID_PREFIX_DISPLAY_MAP = {
        "circle_": "CiRCLE",
        "ring_": "RiNG",
        "mujica_": "Mujica",
        "gwave_": "G：wave",
        "galaxy_": "Galaxy",
    }

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.scene_config = config.scene_config
        self._keywords = sorted(config.scene_keywords.items(), key=lambda item: self._score(item[0]), reverse=True)
        self._structured_rules = sorted(self.scene_config.rules.items(), key=lambda item: self._score(item[0]), reverse=True)
        self._time_markers = self.scene_config.time_markers or self.DEFAULT_TIME_MARKERS
        self._generic_alias_index = self._build_generic_alias_index()

    def _score(self, keyword: str) -> tuple[int, int]:
        is_time_only = keyword in self.TIME_ONLY_KEYWORDS
        return (0 if is_time_only else 1, len(keyword))

    def detect_initial(self, texts: list[str], school_context: str | None = None) -> str | None:
        # Prefer explicit location mentions over time-only ambience when
        # bootstrapping the very first background.
        context_window = ""
        for text in texts[:6]:
            context_window = f"{context_window}{text}"
            for detector in (
                self._detect_structured_alias,
                self._detect_generic_structured_alias,
                self._detect_structured_rule,
            ):
                matched, background = detector(context_window, None, school_context)
                if matched and background:
                    return background
        for text in texts[:6]:
            detected = self.detect(text, school_context=school_context)
            if detected:
                return detected
        return None

    def detect(
        self,
        text: str,
        current_background: str | None = None,
        school_context: str | None = None,
    ) -> str | None:
        # Detection order matters:
        # 1. ignore purely mental references
        # 2. keep stage/backstage continuity stable
        # 3. resolve structured aliases and scene rules
        # 4. fall back to legacy flat keywords for broad compatibility
        if any(marker in text for marker in self.MENTAL_SCENE_MARKERS):
            return None
        if self._looks_like_scene_discussion(text, current_background):
            return None
        if current_background and "演出、排练/" in current_background:
            if any(marker in text for marker in self.BACKSTAGE_HALLWAY_MARKERS):
                background = "演出、排练/其他演出场地/后台2.png"
                return background if background != current_background else None
            if any(marker in text for marker in self.BACKSTAGE_ROOM_MARKERS):
                background = "演出、排练/其他演出场地/后台1.png"
                return background if background != current_background else None
            if any(marker in text for marker in self.STAGE_PERSIST_MARKERS):
                return None

        effective_school = self._explicit_school_name(text) or school_context
        if effective_school and self._is_time_only_text(text):
            return None

        alias_matched, alias_background = self._detect_structured_alias(text, current_background, effective_school)
        if alias_matched:
            return alias_background

        generic_alias_matched, generic_alias_background = self._detect_generic_structured_alias(text, current_background, effective_school)
        if generic_alias_matched:
            return generic_alias_background

        structured_matched, structured_background = self._detect_structured_rule(text, current_background, effective_school)
        if structured_matched:
            return structured_background

        if effective_school:
            generic_school_background = self._generic_school_time_background(text, effective_school)
            if generic_school_background:
                if generic_school_background != current_background:
                    return generic_school_background
                return None

        if any(school_name in text for school_name in self.SCHOOL_NAMES):
            detected = self._detect_by_keywords(text, current_background)
            if detected:
                return detected

        return self._detect_by_keywords(text, current_background)

    def _detect_structured_alias(
        self,
        text: str,
        current_background: str | None,
        school_context: str | None,
    ) -> tuple[bool, str | None]:
        for alias, scene_id in sorted(self.scene_config.aliases.items(), key=lambda item: len(item[0]), reverse=True):
            if alias in text:
                background = self._resolve_scene_background(scene_id, text, school_context, current_background)
                if background and background != current_background:
                    return True, background
                return True, None
        return False, None

    def _detect_generic_structured_alias(
        self,
        text: str,
        current_background: str | None,
        school_context: str | None,
    ) -> tuple[bool, str | None]:
        for candidate, scene_id in self._generic_alias_index:
            if candidate in text:
                background = self._resolve_scene_background(scene_id, text, school_context, current_background)
                if background and background != current_background:
                    return True, background
                return True, None
        return False, None

    def _detect_structured_rule(
        self,
        text: str,
        current_background: str | None,
        school_context: str | None,
    ) -> tuple[bool, str | None]:
        for keyword, scene_id in self._structured_rules:
            if not self._keyword_matches(text, keyword):
                continue
            background = self._resolve_scene_background(scene_id, text, school_context, current_background)
            if not background:
                continue
            if (
                current_background
                and "演出、排练/" in current_background
                and background.startswith(("学校、工作/", "公园/", "自然风光/"))
                and any(
                    marker in text
                    for marker in self.STAGE_PERSIST_MARKERS | self.BACKSTAGE_ROOM_MARKERS | self.BACKSTAGE_HALLWAY_MARKERS
                )
            ):
                continue
            if background != current_background:
                return True, background
            return True, None
        return False, None

    def _resolve_scene_background(
        self,
        scene_id: str,
        text: str,
        school_context: str | None,
        current_background: str | None,
    ) -> str | None:
        scene = self.scene_config.scenes.get(scene_id)
        if not isinstance(scene, dict):
            return None
        scene_type = str(scene.get("type") or "fixed")
        if scene_type == "school":
            return self._resolve_school_scene_background(scene, text, school_context, current_background)
        return self._resolve_fixed_scene_background(scene, text, current_background)

    def _resolve_school_scene_background(
        self,
        scene: dict,
        text: str,
        school_context: str | None,
        current_background: str | None,
    ) -> str | None:
        if not school_context:
            return None
        variants = scene.get("variants", {})
        school_variant = variants.get(school_context)
        if not isinstance(school_variant, dict):
            return None
        time_label = self._time_label_for_text(text, current_background)
        times = school_variant.get("times", {})
        if time_label and isinstance(times, dict):
            timed_background = times.get(time_label)
            if timed_background:
                return str(timed_background)
        background = school_variant.get("default")
        return str(background) if background else None

    def _resolve_fixed_scene_background(
        self,
        scene: dict,
        text: str,
        current_background: str | None,
    ) -> str | None:
        time_label = self._time_label_for_text(text, current_background)
        times = scene.get("times", {})
        if time_label and isinstance(times, dict):
            timed_background = times.get(time_label)
            if timed_background:
                return str(timed_background)
        background = scene.get("default")
        return str(background) if background else None

    def _detect_by_keywords(self, text: str, current_background: str | None = None) -> str | None:
        # Legacy keyword lookup stays as the compatibility net for the large
        # existing resource table. The structured rules only need to cover the
        # places where context-aware resolution matters most.
        for keyword, background in self._keywords:
            if keyword and self._keyword_matches(text, keyword):
                if (
                    current_background
                    and "演出、排练/" in current_background
                    and background.startswith(("学校、工作/", "公园/", "自然风光/"))
                    and any(
                        marker in text
                        for marker in self.STAGE_PERSIST_MARKERS | self.BACKSTAGE_ROOM_MARKERS | self.BACKSTAGE_HALLWAY_MARKERS
                    )
                ):
                    continue
                if background != current_background:
                    return background
                return None
        return None

    def _generic_school_time_background(self, text: str, school_context: str) -> str | None:
        if not self._time_label_for_text(text, None):
            return None
        return self._resolve_scene_background("campus", text, school_context, None)

    def _time_label_for_text(self, text: str, current_background: str | None) -> str | None:
        for time_label, markers in self._time_markers.items():
            if any(marker in text for marker in markers):
                return time_label
        if current_background:
            for time_label in self._time_markers:
                if f"（{time_label}）" in current_background:
                    return time_label
        return None

    def _explicit_school_name(self, text: str) -> str | None:
        for school_name in self.SCHOOL_NAMES:
            if school_name in text:
                return school_name
        return None

    def _keyword_matches(self, text: str, keyword: str) -> bool:
        position = text.find(keyword)
        if position < 0:
            return False
        if len(keyword) > 1:
            return True
        previous = text[position - 1] if position > 0 else ""
        next_index = position + len(keyword)
        following = text[next_index] if next_index < len(text) else ""
        return self._is_boundary(previous) and self._is_boundary(following)

    def _is_boundary(self, ch: str) -> bool:
        if not ch:
            return True
        if ch in self.BOUNDARY_CHARS:
            return True
        return not ("\u4e00" <= ch <= "\u9fff" or ch.isalnum())

    def _build_generic_alias_index(self) -> list[tuple[str, str]]:
        # Derive a small set of reusable natural-language variants from the
        # structured scene rules, so "爱音房间" can resolve through the same
        # scene as "爱音的房间" without needing one-off aliases everywhere.
        variants: dict[str, str] = {}
        structured_sources = {}
        structured_sources.update(self.scene_config.rules)
        structured_sources.update(self.scene_config.aliases)
        for label, scene_id in structured_sources.items():
            for candidate in self._generic_alias_variants_for_label(label, scene_id):
                variants.setdefault(candidate, scene_id)
        return sorted(variants.items(), key=lambda item: len(item[0]), reverse=True)

    def _looks_like_scene_discussion(self, text: str, current_background: str | None) -> bool:
        if not current_background:
            return False
        if not any(marker in text for marker in self.DISCUSSION_SCENE_MARKERS):
            return False
        if any(marker in text for marker in self.LOCATION_TRANSITION_MARKERS):
            return False
        return "舞台" in text or "后台" in text or "教室" in text or "会议室" in text

    def _is_time_only_text(self, text: str) -> bool:
        stripped = text.strip().strip("。；;，,！？!?")
        if not stripped:
            return False
        return any(stripped == marker for markers in self._time_markers.values() for marker in markers)

    def _generic_alias_variants_for_label(self, label: str, scene_id: str) -> list[str]:
        candidates = [label]
        for suffix_group in self.GENERIC_SCENE_SUFFIX_GROUPS:
            base = self._strip_known_suffix(label, suffix_group)
            if base is None:
                scene_prefix = self._scene_display_prefix(scene_id)
                if scene_prefix and label in suffix_group:
                    candidates.extend(scene_prefix + suffix for suffix in suffix_group)
                continue
            candidates.extend(base + suffix for suffix in suffix_group)
        return list(dict.fromkeys(candidate for candidate in candidates if len(candidate) >= 2))

    def _strip_known_suffix(self, label: str, suffix_group: tuple[str, ...]) -> str | None:
        for suffix in suffix_group:
            if label.endswith(suffix) and len(label) > len(suffix):
                return label[: -len(suffix)]
        return None

    def _scene_display_prefix(self, scene_id: str) -> str | None:
        for prefix, display in self.SCENE_ID_PREFIX_DISPLAY_MAP.items():
            if scene_id.startswith(prefix):
                return display
        return None
