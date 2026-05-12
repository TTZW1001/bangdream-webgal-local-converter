from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image


ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def build_square_canvas(image: Image.Image) -> Image.Image:
    width, height = image.size
    side = max(width, height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    offset = ((side - width) // 2, (side - height) // 2)
    canvas.paste(image, offset, image)
    return canvas


def _dib_bytes_for_icon(frame: Image.Image) -> bytes:
    width, height = frame.size
    pixels = frame.convert("RGBA").load()

    xor_rows = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            xor_rows.extend((b, g, r, a))

    mask_row_size = ((width + 31) // 32) * 4
    and_mask = bytes(mask_row_size * height)

    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        width,
        height * 2,
        1,
        32,
        0,
        len(xor_rows) + len(and_mask),
        0,
        0,
        0,
        0,
    )
    return header + bytes(xor_rows) + and_mask


def write_ico(frames: list[tuple[int, bytes]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    data_blocks = bytearray()
    offset = 6 + len(frames) * 16

    for size, frame_bytes in frames:
        width_byte = 0 if size == 256 else size
        height_byte = 0 if size == 256 else size
        header.extend(
            struct.pack(
                "<BBBBHHII",
                width_byte,
                height_byte,
                0,
                0,
                1,
                32,
                len(frame_bytes),
                offset,
            )
        )
        data_blocks.extend(frame_bytes)
        offset += len(frame_bytes)

    output_path.write_bytes(bytes(header) + bytes(data_blocks))


def build_icon(source_path: Path, output_path: Path) -> None:
    image = Image.open(source_path).convert("RGBA")
    canvas = build_square_canvas(image)
    frames = []
    for size in ICON_SIZES:
        frame = canvas.resize((size, size), Image.Resampling.LANCZOS)
        frames.append((size, _dib_bytes_for_icon(frame)))
    write_ico(frames, output_path)


def main() -> int:
    project_root = Path(__file__).resolve().parent
    source_path = project_root / "icon.png"
    output_path = project_root / "icon.ico"

    if not source_path.exists():
        raise FileNotFoundError(f"Missing source PNG: {source_path}")

    build_icon(source_path, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
