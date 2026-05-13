from __future__ import annotations

from pathlib import Path

from .config_loader import load_config
from .models import ConversionResult, FigureResourceIndex
from .parser import parse_text
from .speaker_resolver import SpeakerResolver
from .webgal_generator import WebGALGenerator


def convert_text(
    text: str,
    config_dir: str | Path,
    resource_mode: str = "auto",
    model_overrides: dict[str, str] | None = None,
    scene_school: str = "auto",
    speaker_overrides: dict[int, str] | None = None,
    scene_lock: str | None = None,
    segment_scene_locks: dict[int, str] | None = None,
    figure_controls: dict[str, dict[str, str]] | None = None,
    figure_event_overrides: dict[int, dict[str, str]] | None = None,
    figure_resource_index: FigureResourceIndex | None = None,
) -> ConversionResult:
    # The conversion pipeline is intentionally linear:
    # raw text -> parsed segments -> resolved speakers -> generated script.
    # Keeping the orchestration here thin makes it easier to evolve each
    # stage independently without hiding cross-stage options in the UI layer.
    config = load_config(config_dir)
    parsed = parse_text(text)
    resolver = SpeakerResolver(config)
    resolved, pending = resolver.resolve(parsed, speaker_overrides=speaker_overrides)
    generator = WebGALGenerator(
        config,
        resource_mode=resource_mode,
        model_overrides=model_overrides,
        scene_school=scene_school,
        scene_lock=scene_lock,
        segment_scene_locks=segment_scene_locks,
        figure_controls=figure_controls,
        figure_event_overrides=figure_event_overrides,
        figure_resource_index=figure_resource_index,
    )
    script, pending_items = generator.generate(resolved, pending)
    return ConversionResult(script=script, pending_items=pending_items, segments=resolved)
