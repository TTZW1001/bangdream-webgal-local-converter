from __future__ import annotations

import re

from .models import SegmentKind, TextSegment


SPEAKER_COLON_RE = re.compile(r"^\s*([^:：]{1,24})\s*[:：]\s*(.+?)\s*$")
SPEAKER_VERB_QUOTE_RE = re.compile(
    r"^\s*([^“”「」:：]{1,24}?)(?:说|问|喊|叫|道|轻声道|低声说|小声说|回答|开口)\s*[：:]?\s*[“「](.+)[”」]\s*$"
)
QUOTE_ONLY_RE = re.compile(r"^\s*[“「]([^“”「」]+)[”」]\s*$")
UNCLOSED_QUOTE_ONLY_RE = re.compile(r"^\s*[“「]([^“”「」]+)\s*$")
INLINE_QUOTE_RE = re.compile(r"[“「](.+?)[”」]")
SPEAKER_VERB_PREFIX_RE = re.compile(
    r"^\s*[^“”「」:：]{1,24}?(?:说|问|喊|叫|道|轻声道|低声说|小声说|回答|开口)\s*[：:]?\s*$"
)
POST_QUOTE_ATTR_RE = re.compile(
    r"^\s*(?:[^“”「」:：]{0,24}?)(?:说|问|喊|叫|道|轻声道|低声说|小声说|回答|开口|嘀咕|嘟囔|咕哝|解释|补充)"
)
EMBEDDED_QUOTE_SUFFIXES = ("的", "地", "得", "设定", "程度", "计划", "名字", "症", "词", "说法", "关系")
EXPOSITORY_QUOTE_MARKERS = ("据说", "患者会", "若两周内", "最终可能", "产生的怪病", "所倾慕之人", "两周内可能会死")
EMBEDDED_MOOD_PREFIXES = ("装出一副", "摆出一副", "做出一副", "露出一副")
EMBEDDED_MOOD_SUFFIXES = ("的样子", "的模样", "的表情")
ACTION_HINT_MARKERS = (
    "摆摆手",
    "摆了摆手",
    "叹了口气",
    "苦笑",
    "摇了摇头",
    "摇晃",
    "抬头",
    "低头",
    "眯着眼",
    "皱了皱眉",
    "凑近",
    "解释",
    "补充",
    "嘀咕",
    "咳",
    "抱着",
    "赶紧",
    "连忙",
    "举起手",
    "接话",
    "提醒",
    "欠身",
    "附和",
    "冒了出来",
    "蹲下来",
    "凑到",
    "宣布",
    "露出笑容",
    "跑过来",
    "走了过来",
    "伸出手",
    "扶住",
    "看着",
    "拉起",
    "眨着眼",
    "笑着祝福",
    "眼睛瞬间亮了",
    "眼睛一亮",
    "紧紧贴着",
    "语气轻快",
    "下意识摆手",
    "清了清嗓子",
    "立刻拍板",
    "秒跟",
    "弱弱发言",
    "挥了挥手",
    "调侃道",
    "顿了一下",
    "挑起眉毛",
    "笑眯眯地接话",
    "回头笑",
    "想了想",
    "歪着头想了想",
    "被吓了一跳",
    "放到桌上",
)
PRONOUN_ATTR_PREFIXES = ("她", "他", "她们", "他们")
NON_SUBJECT_PREFIXES = ("有点", "声音", "语气", "反而", "刚", "忽然", "突然", "又", "还", "就", "便")
QUOTE_EXAMPLE_PREFIX_MARKERS = ("总不能", "肯定只会说", "只会说", "比如说", "例如")
NON_DIALOGUE_QUOTE_SUFFIX_MARKERS = ("还在", "进行着", "计划", "而已", "这种", "这问不出", "太社死", "没意义")


def split_paragraphs(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks = re.split(r"\n+", normalized)
    paragraphs: list[str] = []
    for chunk in chunks:
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        if lines:
            paragraphs.append("\n".join(lines))
    return paragraphs


def _clean_narration_fragment(fragment: str) -> str:
    cleaned = fragment.strip()
    cleaned = re.sub(r"[，,]+\。$", "", cleaned)
    return cleaned.rstrip(":：，,；;").strip()


def _strip_leading_inline_quote(fragment: str) -> str:
    return re.sub(r'^\s*[“「][^“”「」]+[”」]\s*', "", fragment).strip()


def _normalize_fragment_for_attribution(fragment: str) -> str:
    normalized = re.sub(r'[“「][^“”「」]{1,8}[”」]', "", fragment)
    return re.sub(r"\s+", "", normalized).strip()


def _should_treat_inline_quote_as_dialogue(prefix: str, suffix: str, quoted: str) -> bool:
    # Inline quotes are ambiguous in prose. This gate tries to keep real
    # dialogue (speaker prefix / attribution / stand-alone quote) while
    # rejecting concept quotes like “花吐症” or tone-decorating quotes.
    prefix_clean = prefix.strip()
    suffix_clean = suffix.strip()
    if any(marker in prefix_clean for marker in QUOTE_EXAMPLE_PREFIX_MARKERS):
        return False
    if not prefix_clean and not suffix_clean:
        return True
    if prefix_clean.endswith(("：", ":")):
        return True
    if SPEAKER_VERB_PREFIX_RE.match(prefix_clean):
        return True
    if not prefix_clean and POST_QUOTE_ATTR_RE.match(suffix_clean):
        return True
    if not prefix_clean and _looks_like_quote_attribution(suffix_clean):
        return True
    if not prefix_clean and _speaker_hint_from_fragment(suffix_clean):
        return True
    if not prefix_clean and suffix_clean and not (_looks_like_quote_attribution(suffix_clean) or POST_QUOTE_ATTR_RE.match(suffix_clean)):
        if any(suffix_clean.startswith(marker) or marker in suffix_clean for marker in NON_DIALOGUE_QUOTE_SUFFIX_MARKERS):
            return False
    if prefix_clean and not suffix_clean:
        return True
    if suffix_clean.startswith(EMBEDDED_QUOTE_SUFFIXES):
        return False
    if prefix_clean.endswith(("什么", "所谓", "这种", "这个", "那个")):
        return False
    if any(marker in prefix_clean for marker in EMBEDDED_MOOD_PREFIXES) and suffix_clean.startswith(EMBEDDED_MOOD_SUFFIXES):
        return False
    if len(quoted.strip()) <= 6 and prefix_clean and suffix_clean:
        return False
    return False


def _is_expository_quote(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) >= 18 and any(marker in stripped for marker in EXPOSITORY_QUOTE_MARKERS)


def _is_action_hint(fragment: str) -> bool:
    cleaned = _normalize_fragment_for_attribution(_strip_leading_inline_quote(_clean_narration_fragment(fragment)))
    return bool(cleaned) and any(marker in cleaned for marker in ACTION_HINT_MARKERS)


def _looks_like_quote_attribution(fragment: str) -> bool:
    cleaned = _strip_leading_inline_quote(_clean_narration_fragment(fragment))
    if not cleaned:
        return False
    if POST_QUOTE_ATTR_RE.match(cleaned):
        return True
    if any(cleaned.startswith(prefix) for prefix in PRONOUN_ATTR_PREFIXES) and _is_action_hint(cleaned):
        return True
    return _is_action_hint(cleaned)


def _speaker_hint_from_fragment(fragment: str) -> str | None:
    # When a quote sits next to an action fragment, prefer the most speaker-
    # looking clause near the quote instead of returning the whole fragment.
    cleaned = _strip_leading_inline_quote(_clean_narration_fragment(fragment))
    if not cleaned:
        return None
    if POST_QUOTE_ATTR_RE.search(cleaned) and not any(cleaned.startswith(prefix) for prefix in PRONOUN_ATTR_PREFIXES):
        return cleaned
    clauses = [part.strip() for part in re.split(r"[，,。；;]", cleaned) if part.strip()]
    for clause in reversed(clauses):
        if any(clause.startswith(prefix) for prefix in PRONOUN_ATTR_PREFIXES):
            continue
        if any(clause.startswith(prefix) for prefix in NON_SUBJECT_PREFIXES):
            continue
        if _looks_like_quote_attribution(clause) or POST_QUOTE_ATTR_RE.match(clause):
            if clause != cleaned and not POST_QUOTE_ATTR_RE.match(clause):
                return cleaned
            return clause
    if any(cleaned.startswith(prefix) for prefix in PRONOUN_ATTR_PREFIXES):
        return None
    return None


def _append_unclosed_quote_segment(line: str, index: int, segments: list[TextSegment]) -> bool:
    # Real source text is often messy. Treat a dangling opening quote as a
    # dialogue line so the converter can stay usable on imperfect drafts.
    quote_only = UNCLOSED_QUOTE_ONLY_RE.match(line)
    if not quote_only:
        return False
    text = quote_only.group(1).strip()
    if not text:
        return False
    segments.append(
        TextSegment(
            kind=SegmentKind.DIALOGUE,
            text=text,
            raw=line,
            index=index,
        )
    )
    return True


def _append_multi_quote_segments(line: str, index: int, segments: list[TextSegment]) -> bool:
    # Handles patterns like:
    # “A。”美咲摆摆手，“B。”
    # If the gaps between quotes look like attribution/action, split them into
    # dialogue / narration / dialogue rather than flattening the whole line.
    matches = list(INLINE_QUOTE_RE.finditer(line))
    if len(matches) < 2 or not line.lstrip().startswith(("“", "「")):
        return False

    gaps = []
    for match_index in range(len(matches) - 1):
        gap = _clean_narration_fragment(line[matches[match_index].end() : matches[match_index + 1].start()])
        if gap:
            gaps.append(gap)
    if gaps and not all(_looks_like_quote_attribution(gap) for gap in gaps):
        return False

    cursor = 0
    pending_narration = ""
    for match_index, match in enumerate(matches):
        prefix = line[cursor : match.start()]
        suffix = line[match.end() :].strip()
        quoted = match.group(1).strip()

        previous_action_hint = _speaker_hint_from_fragment(prefix) if _looks_like_quote_attribution(prefix) else None
        next_fragment = line[match.end() : matches[match_index + 1].start()] if match_index + 1 < len(matches) else line[match.end() :]
        next_action_hint = _speaker_hint_from_fragment(next_fragment) if _looks_like_quote_attribution(next_fragment) else None
        speaker_hint = previous_action_hint or next_action_hint or None

        narration_prefix = _clean_narration_fragment(prefix)
        if narration_prefix and not _looks_like_quote_attribution(prefix):
            pending_narration += narration_prefix
        if pending_narration:
            segments.append(TextSegment(kind=SegmentKind.NARRATION, text=pending_narration, raw=pending_narration, index=index))
            pending_narration = ""

        if _is_expository_quote(quoted):
            quoted_text = f"“{quoted}”"
            segments.append(TextSegment(kind=SegmentKind.NARRATION, text=quoted_text, raw=quoted_text, index=index))
        else:
            segments.append(
                TextSegment(
                    kind=SegmentKind.DIALOGUE,
                    text=quoted,
                    raw=f"{prefix.strip()}“{quoted}”".strip(),
                    index=index,
                    speaker_hint=speaker_hint,
                )
            )

        middle_fragment = _clean_narration_fragment(next_fragment) if match_index + 1 < len(matches) else ""
        if middle_fragment:
            segments.append(TextSegment(kind=SegmentKind.NARRATION, text=middle_fragment, raw=middle_fragment, index=index))
        cursor = match.end()

    suffix_text = _clean_narration_fragment(line[cursor:])
    if suffix_text:
        segments.append(TextSegment(kind=SegmentKind.NARRATION, text=suffix_text, raw=suffix_text, index=index))
    return True


def _append_quote_with_trailing_action(line: str, index: int, segments: list[TextSegment]) -> bool:
    # Handles one-quote lines like:
    # “没事没事。”美咲下意识摆手
    # “还有！”育美眼睛一亮
    match = re.match(r'^\s*[“「]([^“”「」]+)[”」]\s*(.+?)\s*$', line)
    if not match:
        return False
    dialogue_text = match.group(1).strip()
    trailing = _clean_narration_fragment(match.group(2))
    if not trailing or not _looks_like_quote_attribution(trailing):
        return False
    speaker_hint = _speaker_hint_from_fragment(trailing)
    segments.append(
        TextSegment(
            kind=SegmentKind.DIALOGUE,
            text=dialogue_text,
            raw=f'“{dialogue_text}”',
            index=index,
            speaker_hint=speaker_hint,
        )
    )
    segments.append(TextSegment(kind=SegmentKind.NARRATION, text=trailing, raw=trailing, index=index))
    return True


def _quote_only_should_be_narration(line: str, segments: list[TextSegment]) -> bool:
    match = QUOTE_ONLY_RE.match(line)
    if not match:
        return False
    quoted = match.group(1).strip()
    if _is_expository_quote(quoted):
        return True
    if segments:
        previous = segments[-1]
        if previous.kind == SegmentKind.NARRATION:
            previous_text = previous.text.strip()
            if any(marker in previous_text for marker in QUOTE_EXAMPLE_PREFIX_MARKERS):
                return True
            if previous_text.endswith(("说", "说：", "说:", "问", "问：", "问:", "想", "想：", "想:")):
                return True
    return False


def _append_line_segments(line: str, index: int, segments: list[TextSegment]) -> None:
    # Resolution order here is intentional: explicit forms first, then more
    # ambiguous inline-quote heuristics, and only then plain narration.
    speaker_quote = SPEAKER_VERB_QUOTE_RE.match(line)
    if speaker_quote:
        segments.append(
            TextSegment(
                kind=SegmentKind.DIALOGUE,
                text=speaker_quote.group(2).strip(),
                raw=line,
                index=index,
                speaker_hint=speaker_quote.group(1).strip(),
            )
        )
        return

    quote_only = QUOTE_ONLY_RE.match(line)
    if quote_only:
        if _quote_only_should_be_narration(line, segments):
            segments.append(
                TextSegment(
                    kind=SegmentKind.NARRATION,
                    text=line,
                    raw=line,
                    index=index,
                )
            )
            return
        segments.append(
            TextSegment(
                kind=SegmentKind.DIALOGUE,
                text=quote_only.group(1).strip(),
                raw=line,
                index=index,
            )
        )
        return

    if _append_unclosed_quote_segment(line, index, segments):
        return

    if _append_multi_quote_segments(line, index, segments):
        return

    if _append_quote_with_trailing_action(line, index, segments):
        return

    if INLINE_QUOTE_RE.search(line):
        found_dialogue = False
        cursor = 0
        for match in INLINE_QUOTE_RE.finditer(line):
            prefix = line[cursor : match.start()]
            following = line[match.end() :].strip()
            if not _should_treat_inline_quote_as_dialogue(prefix, following, match.group(1)):
                continue
            found_dialogue = True
            prefix_hint = _speaker_hint_from_fragment(prefix) if prefix.strip() else None
            suffix_hint = _speaker_hint_from_fragment(following) if following else None
            speaker_hint = prefix_hint or suffix_hint or (prefix.strip() or following or None)
            cleaned_prefix = _clean_narration_fragment(prefix)
            if cleaned_prefix and not SPEAKER_VERB_PREFIX_RE.match(prefix):
                segments.append(
                    TextSegment(
                        kind=SegmentKind.NARRATION,
                        text=cleaned_prefix,
                        raw=cleaned_prefix,
                        index=index,
                    )
                )
            segments.append(
                TextSegment(
                    kind=SegmentKind.DIALOGUE,
                    text=match.group(1).strip(),
                    raw=f"{prefix.strip()}“{match.group(1).strip()}”".strip(),
                    index=index,
                    speaker_hint=speaker_hint,
                )
            )
            cursor = match.end()

        if not found_dialogue:
            segments.append(TextSegment(kind=SegmentKind.NARRATION, text=line, raw=line, index=index))
            return

        suffix = _clean_narration_fragment(line[cursor:])
        if suffix:
            segments.append(TextSegment(kind=SegmentKind.NARRATION, text=suffix, raw=suffix, index=index))
        return

    speaker_colon = SPEAKER_COLON_RE.match(line)
    if speaker_colon:
        segments.append(
            TextSegment(
                kind=SegmentKind.DIALOGUE,
                text=speaker_colon.group(2).strip(),
                raw=line,
                index=index,
                speaker_hint=speaker_colon.group(1).strip(),
            )
        )
        return

    cursor = 0
    found_quote = False
    for match in INLINE_QUOTE_RE.finditer(line):
        prefix = line[cursor : match.start()]
        following = line[match.end() :].strip()
        if not _should_treat_inline_quote_as_dialogue(prefix, following, match.group(1)):
            continue
        found_quote = True
        prefix_hint = _speaker_hint_from_fragment(prefix) if prefix.strip() else None
        suffix_hint = _speaker_hint_from_fragment(following) if following else None
        speaker_hint = prefix_hint or suffix_hint or (prefix.strip() or following or None)
        cleaned_prefix = _clean_narration_fragment(prefix)
        if cleaned_prefix and not SPEAKER_VERB_PREFIX_RE.match(prefix):
            segments.append(
                TextSegment(
                    kind=SegmentKind.NARRATION,
                    text=cleaned_prefix,
                    raw=cleaned_prefix,
                    index=index,
                )
            )
        segments.append(
            TextSegment(
                kind=SegmentKind.DIALOGUE,
                text=match.group(1).strip(),
                raw=f"{prefix.strip()}“{match.group(1).strip()}”".strip(),
                index=index,
                speaker_hint=speaker_hint,
            )
        )
        cursor = match.end()

    suffix = _clean_narration_fragment(line[cursor:])
    if suffix:
        segments.append(TextSegment(kind=SegmentKind.NARRATION, text=suffix, raw=suffix, index=index))
    elif not found_quote:
        segments.append(TextSegment(kind=SegmentKind.NARRATION, text=line, raw=line, index=index))


def parse_text(text: str) -> list[TextSegment]:
    # Paragraph-based splitting keeps the parser simple while still allowing
    # per-line heuristics to emit multiple segments from one prose sentence.
    segments: list[TextSegment] = []
    for index, paragraph in enumerate(split_paragraphs(text)):
        _append_line_segments(paragraph, index, segments)
    return segments
