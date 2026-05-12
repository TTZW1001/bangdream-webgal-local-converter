from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import AppConfig, PendingItem, ResolvedSegment, SegmentKind, TextSegment


PRONOUN_HINTS = {"她", "他", "ta", "TA", "那人", "对方"}
SPEECH_VERBS = ("轻声道", "低声说", "小声说", "回答", "开口", "说", "问", "喊", "叫", "道")
ADDRESSEE_PREFIXES = {"对", "向", "朝", "跟", "和", "与"}
CUSTOM_SPEAKER_PREFIX = "name:"
CHARACTER_OVERRIDE_PREFIX = "char:"
NARRATION_OVERRIDE_PREFIX = "kind:narration"
BOUNDARY_CHARS = " \t\r\n,，。！？!?；;：“”\"'（）()【】[]《》<>、-—~…"
ADDRESS_SUFFIXES = ("同学", "会长", "前辈", "老师", "同学你")
SINGLE_CHAR_ACTION_PREFIXES = (
    "抱",
    "连",
    "蹦",
    "恍",
    "兴",
    "走",
    "跑",
    "抬",
    "低",
    "皱",
    "笑",
    "眯",
    "摆",
    "咳",
    "清",
    "翻",
    "拿",
    "摇",
    "显",
    "秒",
    "耸",
    "举",
    "扶",
    "紧",
    "蹲",
    "冒",
    "附",
    "欠",
    "提",
    "从",
    "慢",
    "看",
    "想",
    "回",
    "被",
    "语",
    "对",
    "向",
    "也",
    "立",
    "帮",
)
CHARACTER_STYLE_HINTS: dict[str, tuple[str, ...]] = {
    "kokoro": (
        "大家——！今天也要尽情欢笑",
        "米歇尔——！",
        "今天也超级开心呢",
        "米歇尔？",
        "原来米歇尔也会累的吗",
        "米歇尔也是很努力地在做我们Hello Happy World的DJ呀",
        "所以大家要给米歇尔一点掌声",
        "大家——！今天的演出到这里就结束啦",
        "那我请美咲吃刚出炉的超大份薯条套餐",
        "有的哦",
        "没什么哦",
        "我也喜欢美咲",
        "我懂的哦",
    ),
    "kanon": (
        "心心！差不多该结束了哦",
        "米、米歇尔可能是有点冷了吧",
        "毕竟今天风有点大呢",
        "呼诶诶",
        "小美咲，是不是有些着凉了呢",
    ),
    "hagumi": (
        "没错！",
        "可乐饼",
        "走吧走吧小美",
        "你看！",
        "汉堡肉套餐",
        "所以大家回家一定要好好保暖哦",
        "小美",
        "我回来啦",
        "还有！",
    ),
    "kaoru": (
        "呼呼",
        "梦幻",
        "小猫咪",
        "秋天的风，总是让人不知不觉放松下来呢",
        "看完今天梦幻的演出",
        "玉米浓汤",
    ),
}
BODY_STATE_MARKERS = (
    "肌肉",
    "小腿",
    "喉咙",
    "鼻子",
    "发痒",
    "抽紧",
    "刺痛",
    "喷嚏",
    "低烧",
    "头晕",
    "受凉",
    "咳嗽",
    "咳",
    "阿嚏",
    "嘶",
)


@dataclass
class ResolveState:
    # Running state shared across segments. This lets the resolver make
    # incremental conversation judgments instead of re-parsing the whole
    # scene every time it sees a new line.
    pending: list[PendingItem] = field(default_factory=list)
    recent_mentions: list[str] = field(default_factory=list)
    active_characters: list[str] = field(default_factory=list)
    last_speaker_id: str | None = None
    last_action_speaker_id: str | None = None
    last_addressed_character_id: str | None = None
    last_narration_mentions_count: int = 0
    conversation_pair: list[str] = field(default_factory=list)
    last_dialogue_segment_order: int | None = None
    last_dialogue_had_explicit_clue: bool = False


@dataclass
class DialogueContext:
    # Precomputed evidence bundle for one dialogue segment. Keeping these
    # inputs together makes the downstream rule branches easier to read.
    dialogue_mentions_with_positions: list[tuple[int, str, str]]
    dialogue_mentions: list[str]
    style_speaker_id: str | None
    candidates: list[str]
    next_stage_mentions: list[str]
    next_dialogue_addresses: list[str]
    immediate_response_target: str | None
    pair_candidates: list[str]
    addressed_pair_targets: list[str]


class SpeakerResolver:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._aliases_by_length = sorted(config.aliases.items(), key=lambda item: len(item[0]), reverse=True)

    def resolve_alias(self, name: str | None) -> str | None:
        if not name:
            return None
        normalized = name.strip()
        if normalized in PRONOUN_HINTS:
            return None
        direct = self.config.aliases.get(normalized)
        if direct:
            return direct
        mentions = self.find_character_mentions(normalized)
        if len(mentions) == 1:
            return mentions[0]
        return None

    def resolve_speaker_hint(self, hint: str | None) -> str | None:
        speaker_id = self.resolve_alias(hint)
        if speaker_id:
            return speaker_id
        if not hint:
            return None
        cleaned_hint = re.sub(r"[“「][^“”「」]+[”」]", "", hint).strip()
        if cleaned_hint and cleaned_hint != hint:
            speaker_id = self.resolve_alias(cleaned_hint)
            if speaker_id:
                return speaker_id
            hint = cleaned_hint

        speech_pos = max(hint.rfind(verb) for verb in SPEECH_VERBS)
        mentions = self.find_character_mentions_with_positions(hint)
        if speech_pos < 0:
            return self._infer_action_speaker(hint)

        candidates: list[tuple[int, str, str]] = []
        for position, alias, character_id in mentions:
            if position > speech_pos:
                continue
            previous = hint[position - 1] if position > 0 else ""
            if previous in ADDRESSEE_PREFIXES:
                continue
            candidates.append((position, alias, character_id))
        if candidates:
            return candidates[0][2]
        return None

    def find_character_mentions(self, text: str) -> list[str]:
        return [character_id for _position, _alias, character_id in self.find_character_mentions_with_positions(text)]

    def find_character_mentions_with_positions(self, text: str) -> list[tuple[int, str, str]]:
        mentions: list[tuple[int, str, str]] = []
        for alias, character_id in self._aliases_by_length:
            start = 0
            while True:
                position = text.find(alias, start)
                if position < 0:
                    break
                if self._is_valid_alias_match(text, position, alias):
                    mentions.append((position, alias, character_id))
                    break
                start = position + len(alias)
        return sorted(mentions, key=lambda item: item[0])

    def resolve(
        self,
        segments: list[TextSegment],
        speaker_overrides: dict[int, str] | None = None,
    ) -> tuple[list[ResolvedSegment], list[PendingItem]]:
        resolved: list[ResolvedSegment] = []
        overrides = speaker_overrides or {}
        state = ResolveState()
        narration_stage_mentions = [
            self._infer_stage_mentions(segment.text) if segment.kind == SegmentKind.NARRATION else []
            for segment in segments
        ]
        narration_action_speakers = [
            self._infer_action_speaker(segment.text) if segment.kind == SegmentKind.NARRATION else None
            for segment in segments
        ]

        for segment_order, segment in enumerate(segments):
            # Mentions are used by both narration-state updates and dialogue
            # resolution, so compute them once per segment.
            segment_mentions = self.find_character_mentions(segment.text if segment.kind == SegmentKind.NARRATION else segment.raw)
            override = overrides.get(segment_order)
            if override == NARRATION_OVERRIDE_PREFIX and segment.kind == SegmentKind.DIALOGUE:
                resolved.append(
                    ResolvedSegment(
                        kind=SegmentKind.NARRATION,
                        text=segment.text,
                        raw=segment.raw,
                        index=segment.index,
                        speaker_hint=segment.speaker_hint,
                        mentioned_character_ids=self.find_character_mentions(segment.text),
                    )
                )
                state.last_dialogue_had_explicit_clue = False
                continue
            if segment.kind == SegmentKind.NARRATION and override and override != NARRATION_OVERRIDE_PREFIX:
                speaker_id, speaker_name = self._resolve_override(override)
                if speaker_id or speaker_name:
                    forced_dialogue = TextSegment(
                        kind=SegmentKind.DIALOGUE,
                        text=segment.text,
                        raw=segment.raw,
                        index=segment.index,
                        speaker_hint=segment.speaker_hint,
                    )
                    self._update_state_after_resolution(
                        segment=forced_dialogue,
                        segment_order=segment_order,
                        speaker_id=speaker_id,
                        dialogue_had_explicit_clue=True,
                        state=state,
                    )
                    if speaker_id and speaker_id in self.config.characters and speaker_name is None:
                        speaker_name = self.config.characters[speaker_id].display_name
                    resolved.append(
                        ResolvedSegment(
                            kind=SegmentKind.DIALOGUE,
                            text=segment.text,
                            raw=segment.raw,
                            index=segment.index,
                            speaker_id=speaker_id,
                            speaker_name=speaker_name,
                            speaker_hint=segment.speaker_hint,
                            mentioned_character_ids=segment_mentions,
                        )
                    )
                    continue
            speaker_id, speaker_name, dialogue_had_explicit_clue = self._resolve_segment(
                segment=segment,
                segment_order=segment_order,
                segment_mentions=segment_mentions,
                override=override,
                segments=segments,
                narration_stage_mentions=narration_stage_mentions,
                narration_action_speakers=narration_action_speakers,
                state=state,
            )

            self._update_state_after_resolution(
                segment=segment,
                segment_order=segment_order,
                speaker_id=speaker_id,
                dialogue_had_explicit_clue=dialogue_had_explicit_clue,
                state=state,
            )
            if speaker_id and speaker_id in self.config.characters and speaker_name is None:
                speaker_name = self.config.characters[speaker_id].display_name

            resolved.append(
                ResolvedSegment(
                    kind=segment.kind,
                    text=segment.text,
                    raw=segment.raw,
                    index=segment.index,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                    speaker_hint=segment.speaker_hint,
                    mentioned_character_ids=segment_mentions,
                )
            )
        return resolved, state.pending

    def _resolve_segment(
        self,
        segment: TextSegment,
        segment_order: int,
        segment_mentions: list[str],
        override: str | None,
        segments: list[TextSegment],
        narration_stage_mentions: list[list[str]],
        narration_action_speakers: list[str | None],
        state: ResolveState,
    ) -> tuple[str | None, str | None, bool]:
        # Resolution priority:
        # 1. narration only updates context
        # 2. manual overrides always win
        # 3. parser-provided hints are the strongest automatic clue
        # 4. only then do we enter heuristic dialogue inference
        if segment.kind == SegmentKind.NARRATION:
            self._update_narration_state(segment, segment_order, segment_mentions, narration_stage_mentions, state)
            return None, None, False
        if override:
            speaker_id, speaker_name = self._resolve_override(override)
            return speaker_id, speaker_name, True
        if segment.speaker_hint:
            return self._resolve_dialogue_with_hint(segment, segment_order, state)
        return self._resolve_dialogue_without_hint(
            segment=segment,
            segment_order=segment_order,
            segments=segments,
            narration_stage_mentions=narration_stage_mentions,
            narration_action_speakers=narration_action_speakers,
            state=state,
        )

    def _update_narration_state(
        self,
        segment: TextSegment,
        segment_order: int,
        segment_mentions: list[str],
        narration_stage_mentions: list[list[str]],
        state: ResolveState,
    ) -> None:
        # Narration drives stage context: who is present, who just acted, and
        # whether nearby short reaction lines should inherit that actor.
        stage_mentions = narration_stage_mentions[segment_order]
        action_speaker_id = stage_mentions[0] if stage_mentions else self._infer_action_speaker(segment.text)
        state.last_narration_mentions_count = len(segment_mentions)
        state.last_addressed_character_id = None
        if action_speaker_id:
            state.last_action_speaker_id = action_speaker_id
            state.recent_mentions = stage_mentions or [action_speaker_id]
        elif stage_mentions:
            state.recent_mentions = stage_mentions
            state.last_action_speaker_id = None
        elif segment_mentions:
            state.recent_mentions = list(dict.fromkeys(segment_mentions))
            state.last_action_speaker_id = None
        elif not segment_mentions and state.last_action_speaker_id and any(marker in segment.text for marker in BODY_STATE_MARKERS):
            state.recent_mentions = [state.last_action_speaker_id]
        elif segment.text.strip().startswith(("她", "他")) and state.last_action_speaker_id:
            state.recent_mentions = [state.last_action_speaker_id]
        else:
            state.last_action_speaker_id = None
        for mention in stage_mentions or list(dict.fromkeys(segment_mentions)):
            if mention not in state.active_characters:
                state.active_characters.append(mention)

    def _resolve_dialogue_with_hint(
        self,
        segment: TextSegment,
        segment_order: int,
        state: ResolveState,
    ) -> tuple[str | None, str | None, bool]:
        # `speaker_hint` comes from parser-recognized evidence such as
        # `爱音说：“...”` or `“对呀！”心笑眯眯地接话`.
        speaker_id = self.resolve_speaker_hint(segment.speaker_hint)
        state.last_addressed_character_id = None
        if speaker_id is None:
            self._append_hint_pending(segment, segment_order, state)
        return speaker_id, None, speaker_id is not None

    def _append_hint_pending(self, segment: TextSegment, segment_order: int, state: ResolveState) -> None:
        mentions = self.find_character_mentions(segment.speaker_hint or "")
        suggestion = f"请在 aliases.json 中添加“{segment.speaker_hint}”的角色映射。"
        if len(mentions) > 1:
            suggestion = "前缀里出现多个角色，请手动确认实际说话人。"
        if segment.speaker_hint and "老师" not in segment.speaker_hint:
            state.pending.append(
                PendingItem(
                    index=segment.index,
                    raw=segment.raw,
                    issue_type="说话人不明" if len(mentions) > 1 else "角色未映射",
                    suggestion=suggestion,
                    segment_index=segment_order,
                )
            )

    def _resolve_dialogue_without_hint(
        self,
        segment: TextSegment,
        segment_order: int,
        segments: list[TextSegment],
        narration_stage_mentions: list[list[str]],
        narration_action_speakers: list[str | None],
        state: ResolveState,
    ) -> tuple[str | None, str | None, bool]:
        # No explicit hint survived parsing, so gather all local evidence and
        # let the inference layers decide how much confidence we have.
        context = self._build_dialogue_context(
            segment=segment,
            segment_order=segment_order,
            segments=segments,
            narration_stage_mentions=narration_stage_mentions,
            narration_action_speakers=narration_action_speakers,
            state=state,
        )
        speaker_id, dialogue_had_explicit_clue = self._infer_dialogue_speaker(segment, segment_order, context, state)
        if speaker_id is None:
            state.pending.append(
                PendingItem(
                    index=segment.index,
                    raw=segment.raw,
                    issue_type="说话人不明",
                    suggestion="请手动指定该句对白的角色。",
                    segment_index=segment_order,
                )
            )
        return speaker_id, None, dialogue_had_explicit_clue

    def _build_dialogue_context(
        self,
        segment: TextSegment,
        segment_order: int,
        segments: list[TextSegment],
        narration_stage_mentions: list[list[str]],
        narration_action_speakers: list[str | None],
        state: ResolveState,
    ) -> DialogueContext:
        # Collect the raw ingredients that later heuristic branches will use:
        # mentions inside the line, active on-stage speakers, nearby actors,
        # and short-range reply/address relationships.
        dialogue_mentions_with_positions = self.find_character_mentions_with_positions(segment.text)
        dialogue_mentions = self.find_character_mentions(segment.text)
        return DialogueContext(
            dialogue_mentions_with_positions=dialogue_mentions_with_positions,
            dialogue_mentions=dialogue_mentions,
            style_speaker_id=self._match_character_style(segment.text, state.active_characters),
            candidates=[cid for cid in state.active_characters if cid != state.last_speaker_id],
            next_stage_mentions=self._next_stage_mentions(narration_stage_mentions, narration_action_speakers, segment_order),
            next_dialogue_addresses=self._next_dialogue_addresses(segments, segment_order, state.active_characters),
            immediate_response_target=self._immediate_response_target(segments, segment_order),
            pair_candidates=[cid for cid in state.conversation_pair if cid != state.last_speaker_id],
            addressed_pair_targets=[
                cid for cid in state.conversation_pair if self._dialogue_addresses_character(segment.text, cid)
            ],
        )

    def _infer_dialogue_speaker(
        self,
        segment: TextSegment,
        segment_order: int,
        context: DialogueContext,
        state: ResolveState,
    ) -> tuple[str | None, bool]:
        # First prefer strong evidence that should beat generic alternation:
        # style markers, obvious replies, or nearby explicit actor carry-over.
        if context.style_speaker_id:
            return context.style_speaker_id, True
        if (
            self._opens_with_address(context.dialogue_mentions_with_positions)
            and len(context.dialogue_mentions) == 1
        ):
            candidate_pool = list(dict.fromkeys(state.active_characters + state.recent_mentions))
            other_candidates = [cid for cid in candidate_pool if cid != context.dialogue_mentions[0]]
            if len(other_candidates) == 1:
                return other_candidates[0], False
        if (
            state.last_speaker_id
            and self._is_first_person_dialogue(segment.text)
            and len(context.dialogue_mentions) == 1
            and context.dialogue_mentions[0] != state.last_speaker_id
            and state.last_speaker_id in state.active_characters
        ):
            return state.last_speaker_id, False
        if (
            context.immediate_response_target
            and context.immediate_response_target != state.last_speaker_id
            and context.immediate_response_target not in context.dialogue_mentions
            and (
                not context.dialogue_mentions
                or self._is_first_person_dialogue(segment.text)
                or self._is_brief_reaction_dialogue(segment.text)
                or self._looks_like_calling_out_dialogue(segment.text, context.dialogue_mentions_with_positions)
            )
        ):
            return context.immediate_response_target, False
        if (
            state.last_addressed_character_id
            and state.last_addressed_character_id != state.last_speaker_id
            and state.last_addressed_character_id not in context.dialogue_mentions
            and not self._opens_with_address(context.dialogue_mentions_with_positions)
            and (
                not context.dialogue_mentions
                or self._is_first_person_dialogue(segment.text)
                or self._is_brief_reaction_dialogue(segment.text)
                or self._looks_like_direct_reply_dialogue(segment.text)
            )
        ):
            return state.last_addressed_character_id, False
        if (
            state.last_action_speaker_id
            and state.last_action_speaker_id not in context.dialogue_mentions
            and not (
                state.last_speaker_id is None
                and len(state.active_characters) == 2
                and self._is_brief_reaction_dialogue(segment.text)
            )
            and not (
                len(context.next_stage_mentions) == 1
                and context.next_stage_mentions[0] != state.last_action_speaker_id
                and state.last_narration_mentions_count == 1
                and not self._is_brief_reaction_dialogue(segment.text)
            )
            and self._should_prefer_recent_actor(segment.text, segment_order, state.last_dialogue_segment_order)
        ):
            return state.last_action_speaker_id, False
        if (
            state.last_speaker_id
            and state.last_dialogue_had_explicit_clue
            and state.last_dialogue_segment_order is not None
            and segment_order - state.last_dialogue_segment_order <= 2
            and not self._opens_with_address(context.dialogue_mentions_with_positions)
            and not context.addressed_pair_targets
            and not (
                state.conversation_pair
                and not context.dialogue_mentions
                and len(context.pair_candidates) == 1
                and self._is_passive_reaction_dialogue(segment.text)
            )
        ):
            return state.last_speaker_id, False
        # If no high-confidence clue fired, fall back to broader dialogue-flow
        # heuristics such as pair alternation and recent mentions.
        speaker_id = self._infer_from_dialogue_flow(segment.text, context, state)
        return speaker_id, False

    def _infer_from_dialogue_flow(
        self,
        text: str,
        context: DialogueContext,
        state: ResolveState,
    ) -> str | None:
        # Lower-confidence conversational heuristics. These branches model
        # addressing, alternation, reaction inheritance, and final fallback to
        # the last known speaker when the current line is weak on evidence.
        if (
            len(context.addressed_pair_targets) == 1
            and state.last_speaker_id
            and context.addressed_pair_targets[0] == state.last_speaker_id
            and context.pair_candidates
        ):
            return context.pair_candidates[0]
        if (
            not state.conversation_pair
            and state.last_speaker_id
            and state.last_action_speaker_id == state.last_speaker_id
            and state.last_narration_mentions_count == 1
            and not context.dialogue_mentions
            and not self._is_brief_reaction_dialogue(text)
        ):
            return state.last_speaker_id
        if (
            state.last_speaker_id
            and not context.dialogue_mentions
            and self._looks_like_same_speaker_continuation(text)
        ):
            return state.last_speaker_id
        if (
            state.last_speaker_id
            and not context.dialogue_mentions
            and self._looks_like_imperative_followup(text)
        ):
            return state.last_speaker_id
        if (
            state.conversation_pair
            and len(context.pair_candidates) == 1
            and self._looks_like_protest_interruption(text)
        ):
            return context.pair_candidates[0]
        if (
            not context.dialogue_mentions
            and len(context.next_stage_mentions) == 1
            and context.next_stage_mentions[0] != state.last_speaker_id
            and state.last_narration_mentions_count == 1
            and not self._is_brief_reaction_dialogue(text)
            and context.next_stage_mentions[0] not in state.conversation_pair
            and (
                not state.conversation_pair
                or (
                    "你们两个" in text
                    or "你们俩" in text
                    or (
                        not self._is_first_person_dialogue(text)
                        and not self._looks_like_direct_reply_dialogue(text)
                        and len(context.next_stage_mentions) == 1
                    )
                )
            )
        ):
            return context.next_stage_mentions[0]
        if (
            state.conversation_pair
            and len(context.pair_candidates) == 1
            and not context.dialogue_mentions
            and not context.addressed_pair_targets
            and not self._is_brief_reaction_dialogue(text)
        ):
            if state.last_action_speaker_id == state.last_speaker_id and state.last_narration_mentions_count == 1:
                return state.last_speaker_id
            return context.pair_candidates[0]
        if (
            state.conversation_pair
            and state.last_speaker_id
            and state.last_speaker_id in context.addressed_pair_targets
            and context.pair_candidates
        ):
            # In a stable two-person exchange, a line that opens by calling the
            # previous speaker is usually the other person replying to them.
            return context.pair_candidates[0]
        if (
            len(context.next_stage_mentions) == 1
            and context.dialogue_mentions
            and context.next_stage_mentions[0] not in context.dialogue_mentions
            and self._opens_with_address(context.dialogue_mentions_with_positions)
            and not state.conversation_pair
            and not state.last_speaker_id
        ):
            return context.next_stage_mentions[0]
        if (
            not context.dialogue_mentions
            and not state.conversation_pair
            and len(state.active_characters) == 2
            and len(context.next_dialogue_addresses) == 1
        ):
            return context.next_dialogue_addresses[0]
        if (
            not state.last_speaker_id
            and state.last_action_speaker_id
            and len(state.active_characters) == 2
            and not context.dialogue_mentions
        ):
            other_candidates = [cid for cid in state.active_characters if cid != state.last_action_speaker_id]
            if len(other_candidates) == 1:
                if self._dialogue_addresses_character(text, other_candidates[0]):
                    return state.last_action_speaker_id
                if not self._is_brief_reaction_dialogue(text):
                    return other_candidates[0]
        if (
            state.conversation_pair
            and not context.dialogue_mentions
            and len(context.pair_candidates) == 1
            and self._is_passive_reaction_dialogue(text)
        ):
            # A bare reaction after both sides have just been on stage usually
            # belongs to the non-current side of the established pair.
            if state.last_action_speaker_id == state.last_speaker_id and state.last_narration_mentions_count == 1:
                return state.last_speaker_id
            return context.pair_candidates[0]
        if (
            state.conversation_pair
            and not context.dialogue_mentions
            and state.last_addressed_character_id
            and state.last_addressed_character_id in state.conversation_pair
            and state.last_addressed_character_id != state.last_speaker_id
            and not context.addressed_pair_targets
            and (
                self._is_first_person_dialogue(text)
                or self._is_brief_reaction_dialogue(text)
                or self._looks_like_direct_reply_dialogue(text)
            )
        ):
            return state.last_addressed_character_id
        if (
            state.conversation_pair
            and len(context.addressed_pair_targets) == 1
            and context.addressed_pair_targets[0] != state.last_speaker_id
            and state.last_speaker_id in state.conversation_pair
        ):
            return state.last_speaker_id
        if state.last_speaker_id and state.last_speaker_id in context.dialogue_mentions and state.conversation_pair:
            return context.pair_candidates[0] if context.pair_candidates else None
        if len(state.active_characters) == 2 and state.last_speaker_id and state.last_speaker_id in context.dialogue_mentions:
            return context.candidates[0] if context.candidates else None
        if (
            state.last_action_speaker_id
            and len(state.active_characters) == 2
            and state.last_narration_mentions_count >= 2
            and not context.dialogue_mentions
        ):
            return context.candidates[0] if context.candidates else state.last_action_speaker_id
        if (
            state.last_action_speaker_id
            and state.last_action_speaker_id not in context.dialogue_mentions
            and (self._is_brief_reaction_dialogue(text) or len(state.active_characters) <= 1)
        ):
            return state.last_action_speaker_id
        if (
            not context.dialogue_mentions
            and state.conversation_pair
            and len(context.pair_candidates) == 1
            and context.next_stage_mentions == context.pair_candidates
        ):
            return context.pair_candidates[0]
        if (
            not context.dialogue_mentions
            and len(state.active_characters) == 2
            and len(context.next_stage_mentions) == 1
            and context.next_stage_mentions[0] != state.last_speaker_id
            and self._is_brief_reaction_dialogue(text)
        ):
            return context.next_stage_mentions[0]
        if (
            len(state.active_characters) <= 1
            and len(context.next_stage_mentions) == 1
            and context.dialogue_mentions
            and context.next_stage_mentions[0] not in context.dialogue_mentions
            and self._is_brief_reaction_dialogue(text)
        ):
            return context.next_stage_mentions[0]
        if not context.dialogue_mentions and len(state.active_characters) <= 1 and len(context.next_stage_mentions) == 1:
            return context.next_stage_mentions[0]
        if not context.dialogue_mentions and len(context.next_stage_mentions) == 1 and state.last_speaker_id and context.next_stage_mentions[0] != state.last_speaker_id:
            return state.last_speaker_id
        if len(context.dialogue_mentions) == 1 and len(state.active_characters) >= 2:
            if state.conversation_pair and context.dialogue_mentions[0] in context.pair_candidates:
                return context.dialogue_mentions[0]
            other = [cid for cid in state.active_characters if cid != context.dialogue_mentions[0]]
            if len(other) == 1:
                return other[0]
            if state.last_speaker_id and state.last_speaker_id != context.dialogue_mentions[0]:
                return state.last_speaker_id
            if other:
                return other[0]
        if len(context.dialogue_mentions) == 1 and context.dialogue_mentions[0] in state.conversation_pair:
            others = [cid for cid in state.conversation_pair if cid != context.dialogue_mentions[0]]
            if others:
                return others[0]
        if state.last_speaker_id:
            return state.last_speaker_id
        if len(state.active_characters) == 2 and state.last_speaker_id:
            return context.candidates[0] if context.candidates else state.active_characters[0]
        if len(state.recent_mentions) == 1:
            return state.recent_mentions[0]
        return None

    def _update_state_after_resolution(
        self,
        segment: TextSegment,
        segment_order: int,
        speaker_id: str | None,
        dialogue_had_explicit_clue: bool,
        state: ResolveState,
    ) -> None:
        # Centralized write-back keeps state mutations consistent regardless of
        # which resolution path produced the speaker.
        if speaker_id and speaker_id in self.config.characters:
            self._apply_resolved_speaker_state(segment, speaker_id, state)
        elif segment.kind == SegmentKind.DIALOGUE:
            state.last_addressed_character_id = None

        if segment.kind == SegmentKind.DIALOGUE:
            if speaker_id:
                state.last_dialogue_segment_order = segment_order
                state.last_dialogue_had_explicit_clue = dialogue_had_explicit_clue
            else:
                state.last_dialogue_had_explicit_clue = False

    def _apply_resolved_speaker_state(
        self,
        segment: TextSegment,
        speaker_id: str,
        state: ResolveState,
    ) -> None:
        # Dialogue updates both "who is currently talking" and "who is talking
        # to whom", which powers later reply and alternation inference.
        previous_speaker_id = state.last_speaker_id
        if speaker_id not in state.active_characters:
            state.active_characters.append(speaker_id)
        state.last_speaker_id = speaker_id
        if segment.kind != SegmentKind.DIALOGUE:
            return
        dialogue_mentions_with_positions = self.find_character_mentions_with_positions(segment.text)
        dialogue_mentions = [character_id for _position, _alias, character_id in dialogue_mentions_with_positions]
        target_ids = [cid for cid in dialogue_mentions if cid != speaker_id]
        addressed_targets = [
            cid
            for cid in (state.conversation_pair or state.active_characters)
            if cid != speaker_id and self._dialogue_addresses_character(segment.text, cid)
        ]
        if not addressed_targets and self._opens_with_address(dialogue_mentions_with_positions):
            addressed_targets = [cid for cid in target_ids[:1] if cid != speaker_id]
        if addressed_targets:
            state.conversation_pair = [speaker_id, addressed_targets[0]]
        elif previous_speaker_id and previous_speaker_id != speaker_id:
            state.conversation_pair = [previous_speaker_id, speaker_id]
        elif state.conversation_pair and speaker_id in state.conversation_pair:
            pass
        elif not previous_speaker_id and len(state.active_characters) == 2:
            other_candidates = [cid for cid in state.active_characters if cid != speaker_id]
            if len(other_candidates) == 1:
                state.conversation_pair = [other_candidates[0], speaker_id]
        if addressed_targets:
            state.last_addressed_character_id = addressed_targets[0]
        elif target_ids and self._opens_with_address(dialogue_mentions_with_positions):
            state.last_addressed_character_id = target_ids[0]
        else:
            state.last_addressed_character_id = None
        state.last_action_speaker_id = None

    def _resolve_override(self, override: str) -> tuple[str | None, str | None]:
        if override.startswith(CUSTOM_SPEAKER_PREFIX):
            custom_name = override[len(CUSTOM_SPEAKER_PREFIX) :].strip()
            if custom_name:
                return None, custom_name
            return None, None
        if override.startswith(CHARACTER_OVERRIDE_PREFIX):
            character_id = override[len(CHARACTER_OVERRIDE_PREFIX) :].strip()
            if character_id in self.config.characters:
                return character_id, None
            return None, None
        if override in self.config.characters:
            return override, None
        return None, override.strip() or None

    def _is_valid_alias_match(self, text: str, position: int, alias: str) -> bool:
        if len(alias) > 1:
            return True
        previous = text[position - 1] if position > 0 else ""
        next_index = position + len(alias)
        following = text[next_index] if next_index < len(text) else ""
        if self._is_boundary(previous) and self._is_boundary(following):
            return True
        if not self._is_boundary(previous):
            return False
        upcoming = text[next_index : next_index + 4]
        return any(upcoming.startswith(prefix) for prefix in SINGLE_CHAR_ACTION_PREFIXES)

    def _is_boundary(self, ch: str) -> bool:
        if not ch:
            return True
        if ch in BOUNDARY_CHARS:
            return True
        return not ("\u4e00" <= ch <= "\u9fff" or ch.isalnum())

    def _next_stage_mentions(
        self,
        stage_mentions_by_segment: list[list[str]],
        action_speakers_by_segment: list[str | None],
        current_index: int,
    ) -> list[str]:
        for lookahead_index, mentions in enumerate(stage_mentions_by_segment[current_index + 1 : current_index + 3], start=current_index + 1):
            if lookahead_index < len(action_speakers_by_segment):
                next_segment_speaker = action_speakers_by_segment[lookahead_index]
                if next_segment_speaker:
                    return [next_segment_speaker]
            if mentions:
                return mentions
        return []

    def _next_dialogue_addresses(
        self,
        segments: list[TextSegment],
        current_index: int,
        candidate_ids: list[str],
    ) -> list[str]:
        for segment in segments[current_index + 1 : current_index + 4]:
            if segment.kind != SegmentKind.DIALOGUE:
                continue
            targets = [cid for cid in candidate_ids if self._dialogue_addresses_character(segment.text, cid)]
            if targets:
                return targets
            if segment.speaker_hint:
                return []
        return []

    def _immediate_response_target(
        self,
        segments: list[TextSegment],
        current_index: int,
    ) -> str | None:
        for segment in segments[current_index + 1 : current_index + 5]:
            if segment.kind == SegmentKind.NARRATION:
                if self.find_character_mentions(segment.text) or self._infer_action_speaker(segment.text):
                    break
                continue
            if segment.kind != SegmentKind.DIALOGUE:
                continue
            if not self._looks_like_addressed_followup(segment.text):
                return None
            targets = [
                character_id
                for character_id in self.config.characters
                if self._dialogue_addresses_character(segment.text, character_id)
            ]
            targets = list(dict.fromkeys(targets))
            if len(targets) == 1:
                return targets[0]
            return None
        return None

    def _looks_like_addressed_followup(self, text: str) -> bool:
        normalized = text.strip().strip("“”「」")
        if not normalized:
            return False
        if not any(marker in normalized for marker in ("你", "？", "?", "吗", "吧", "呢", "——")) and len(normalized) > 12:
            return False
        mentions = self.find_character_mentions_with_positions(normalized)
        if mentions and mentions[0][0] <= 4:
            return True
        return False

    def _infer_stage_mentions(self, text: str) -> list[str]:
        mentions = self.find_character_mentions_with_positions(text)
        if not mentions:
            return []
        action_markers = (
            "走进",
            "进来",
            "来到",
            "走到",
            "推开",
            "抱着",
            "凑近",
            "凑了上来",
            "凑上来",
            "倒进",
            "坐在",
            "站在",
            "抬头",
            "跑过来",
            "走了过来",
            "冒了出来",
            "扶住",
        )
        stage_mentions: list[str] = []
        for position, _alias, character_id in mentions:
            next_text = text[position : position + 18]
            if any(marker in next_text for marker in action_markers) and character_id not in stage_mentions:
                stage_mentions.append(character_id)
        return stage_mentions

    def _infer_action_speaker(self, text: str) -> str | None:
        mentions = self.find_character_mentions_with_positions(text)
        if not mentions:
            return None
        action_markers = (
            "凑",
            "拉",
            "赶忙",
            "救场",
            "挠",
            "看",
            "想着",
            "叹",
            "接受",
            "乖乖",
            "走",
            "来到",
            "开口",
            "抬头",
            "皱",
            "眯",
            "摆摆手",
            "接话",
            "拍板",
            "发言",
            "低头",
            "笑",
            "看着",
            "祝福",
            "嘀咕",
            "咳",
            "翻",
            "拿起",
            "摇",
            "耸",
            "抱",
            "扑",
            "扶",
            "举",
            "提醒",
            "附和",
            "冒",
            "蹲",
            "凑到",
            "宣布",
            "欠身",
            "跑",
            "伸出手",
            "扶住",
            "紧紧贴着",
            "语气轻快",
        )
        for position, _alias, character_id in mentions:
            next_text = text[position : position + 16]
            if any(marker in next_text for marker in action_markers):
                return character_id
        if len(mentions) == 1:
            return mentions[0][2]
        return None

    def _dialogue_addresses_character(self, text: str, character_id: str) -> bool:
        character = self.config.characters.get(character_id)
        if not character:
            return False
        candidates = set()
        display = character.display_name.strip()
        if display:
            candidates.add(display)
            if len(display) >= 2:
                candidates.add(display[:2])
                candidates.add(display[-2:])
        full_name = character.full_name.strip()
        if full_name:
            candidates.add(full_name)
            if len(full_name) >= 2:
                candidates.add(full_name[:2])
                candidates.add(full_name[-2:])
        for alias, alias_character_id in self.config.aliases.items():
            if alias_character_id == character_id and len(alias) <= 4:
                candidates.add(alias.strip())
        for base in candidates:
            if not base:
                continue
            if any(f"{base}{suffix}" in text for suffix in ADDRESS_SUFFIXES):
                return True
            position = text.find(base)
            if 0 <= position <= 3:
                tail = text[position + len(base) : position + len(base) + 2]
                if not tail or any(ch in "，,。！？!?~～—-…:" for ch in tail):
                    return True
        return False

    def _opens_with_address(self, mentions: list[tuple[int, str, str]]) -> bool:
        if not mentions:
            return False
        first_position, _alias, _character_id = mentions[0]
        return first_position <= 2

    def _match_character_style(self, text: str, candidate_ids: list[str]) -> str | None:
        matched_ids: list[str] = []
        for character_id in candidate_ids:
            markers = CHARACTER_STYLE_HINTS.get(character_id)
            if not markers:
                continue
            if any(marker in text for marker in markers):
                return character_id
        for character_id, markers in CHARACTER_STYLE_HINTS.items():
            if any(marker in text for marker in markers):
                matched_ids.append(character_id)
        unique_ids = list(dict.fromkeys(matched_ids))
        if len(unique_ids) == 1:
            return unique_ids[0]
        return None

    def _is_brief_reaction_dialogue(self, text: str) -> bool:
        normalized = text.strip().strip("“”「」")
        if not normalized:
            return False
        if len(normalized) <= 6:
            return True
        reaction_markers = (
            "……？",
            "……",
            "咳",
            "欸",
            "诶",
            "啊？",
            "什么？",
            "这什么东西？",
            "花瓣……？",
            "等等。",
        )
        return len(normalized) <= 12 and any(marker in normalized for marker in reaction_markers)

    def _looks_like_calling_out_dialogue(
        self,
        text: str,
        mentions: list[tuple[int, str, str]],
    ) -> bool:
        normalized = text.strip().strip("“”「」")
        if len(mentions) != 1:
            return False
        first_position, alias, _character_id = mentions[0]
        if first_position > 1:
            return False
        tail = normalized[first_position + len(alias) :]
        if not tail:
            return False
        return any(marker in tail for marker in ("~", "～", "！", "!", "——"))

    def _is_first_person_dialogue(self, text: str) -> bool:
        normalized = text.strip().strip("“”「」")
        if normalized.startswith("恕我直言"):
            return False
        return any(marker in normalized for marker in ("我", "我们", "咱", "咱们"))

    def _looks_like_direct_reply_dialogue(self, text: str) -> bool:
        normalized = text.strip().strip("“”「」")
        if not normalized:
            return False
        reply_prefixes = ("没", "不是", "那个", "嗯", "啊", "咳", "抱歉", "其实")
        if any(normalized.startswith(prefix) for prefix in reply_prefixes):
            return True
        return any(marker in normalized for marker in ("没事", "有点", "只是", "咳"))

    def _looks_like_same_speaker_continuation(self, text: str) -> bool:
        normalized = text.strip().strip("“”「」")
        return normalized.startswith(("结果", "而且", "另外", "再说", "不过", "只是", "顺便"))

    def _is_passive_reaction_dialogue(self, text: str) -> bool:
        normalized = text.strip().strip("“”「」")
        if normalized in {"……", "嗯？", "哦？", "欸——？！", "欸——？", "咳、咳——"}:
            return True
        return len(normalized) <= 8 and any(marker in normalized for marker in ("……", "咳", "哦？", "嗯？", "什么？"))

    def _looks_like_imperative_followup(self, text: str) -> bool:
        normalized = text.strip().strip("“”「」")
        return normalized.startswith(("快", "先", "来", "别")) and "！" in normalized

    def _looks_like_protest_interruption(self, text: str) -> bool:
        normalized = text.strip().strip("“”「」")
        return normalized.startswith(("等等", "花音学姐你怎么也", "这逻辑", "怎么也"))

    def _should_prefer_recent_actor(
        self,
        text: str,
        segment_order: int,
        last_dialogue_segment_order: int | None,
    ) -> bool:
        normalized = text.strip().strip("“”「」")
        if last_dialogue_segment_order is None:
            if self._is_first_person_dialogue(normalized) or self._is_brief_reaction_dialogue(normalized):
                return True
            return len(normalized) <= 12
        if segment_order - last_dialogue_segment_order > 4:
            return False
        if self._is_first_person_dialogue(normalized):
            return True
        if len(normalized) <= 30:
            return True
        return False
