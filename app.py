from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.converter import convert_text


def get_runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


PROJECT_ROOT = get_runtime_root()
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert Chinese fanfic text to a WebGAL draft script.")
    parser.add_argument("input", nargs="?", help="Input txt file. If omitted, launches the Tkinter GUI.")
    parser.add_argument("-o", "--output", help="Output WebGAL scene txt file.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_DIR), help="Config directory.")
    parser.add_argument("--mode", choices=["auto", "generic", "31"], default="auto", help="Figure resource mode.")
    parser.add_argument("--school", choices=["auto", "花咲川", "羽丘", "月之森"], default="auto", help="Default school context for generic school scenes.")
    parser.add_argument("--scene-lock", default=None, help="Lock background by keyword or direct background path.")
    return parser


def run_cli(args: argparse.Namespace) -> int:
    # CLI stays intentionally minimal: read input, run the shared conversion
    # pipeline, then emit script plus any manual follow-up hints.
    input_path = Path(args.input)
    text = input_path.read_text(encoding="utf-8-sig")
    result = convert_text(
        text,
        args.config,
        resource_mode=args.mode,
        scene_school=args.school,
        scene_lock=args.scene_lock,
    )

    if args.output:
        Path(args.output).write_text(result.script, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(result.script)

    if result.pending_items:
        sys.stderr.write("\nPending items:\n")
        for item in result.pending_items:
            sys.stderr.write(f"- #{item.index} {item.issue_type}: {item.raw}\n  {item.suggestion}\n")
    return 0


def run_gui() -> int:
    from src.tk_main_window import main

    return main(DEFAULT_CONFIG_DIR)


def main() -> int:
    # The app has two entry modes:
    # with an input path it behaves like a batch converter,
    # otherwise it launches the Tkinter workbench.
    parser = build_parser()
    args = parser.parse_args()
    if args.input:
        return run_cli(args)
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
