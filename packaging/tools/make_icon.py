#!/usr/bin/env python3
"""Generate packaging/pyinstaller/app.ico.

Kept as a script so the icon is reproducible and reviewable rather than an
opaque committed binary. Writes a multi-resolution Windows icon with no
third-party dependencies: each image is a 32-bit BGRA bitmap in the
classic ICO/BMP layout.

Run from the repository root::

    python packaging/tools/make_icon.py
"""

from __future__ import annotations

import struct
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUTPUT = Path(__file__).resolve().parents[1] / "pyinstaller" / "app.ico"

# Brand-neutral palette: a deep indigo folder with a lighter teal arrow.
FOLDER_BODY = (0x3D, 0x2B, 0x6B)  # BGR
FOLDER_TAB = (0x4B, 0x37, 0x7D)
ARROW = (0x2D, 0xC6, 0xB5)  # BGR of #B5C62D-ish teal
CLEAR = (0, 0, 0, 0)


def _rounded(x: float, y: float, size: int) -> bool:
    """True when (x, y) is inside a rounded square of the given size."""
    radius = size * 0.18
    for cx, cy in ((radius, radius), (size - radius, radius),
                   (radius, size - radius), (size - radius, size - radius)):
        if (x < radius or x > size - radius) and (y < radius or y > size - radius):
            if abs(x - cx) <= radius and abs(y - cy) <= radius:
                return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2
    return True


def _pixels(size: int) -> bytearray:
    """Render one size as raw BGRA rows, bottom-up as ICO requires."""
    rows = []
    unit = size / 16.0
    for row in range(size):
        y = size - 1 - row  # ICO bitmaps are bottom-up
        line = bytearray()
        for col in range(size):
            r, g, b, a = CLEAR

            if _rounded(col, y, size):
                # Folder body occupies the lower two thirds.
                top = size * 0.34
                tab_left, tab_right = size * 0.16, size * 0.52
                is_tab = top - unit * 2 <= y < top and tab_left <= col < tab_right
                if is_tab or (top <= y < size * 0.88 and size * 0.12 <= col < size * 0.88):
                    body = FOLDER_TAB if is_tab else FOLDER_BODY
                    b, g, r = body
                    a = 255

                    # Downward arrow over the folder front.
                    ax = size * 0.5
                    stem_half = unit * 0.9
                    head_half = unit * 2.4
                    ay0, ay1 = size * 0.44, size * 0.66
                    in_stem = abs(col - ax) <= stem_half and ay0 <= y < ay1
                    in_head = ay1 <= y < ay1 + unit * 2.2 and abs(col - ax) <= head_half * (
                        (ay1 + unit * 2.2 - y) / (unit * 2.2)
                    )
                    if in_stem or in_head:
                        b, g, r = ARROW

            line += bytes((b, g, r, a))
        rows.append(bytes(line))
    return b"".join(rows)


def _bmp_info(size: int) -> bytes:
    """BITMAPINFOHEADER: height is doubled to cover the XOR+AND masks."""
    return struct.pack(
        "<IiiHHIIiiII",
        40,          # header size
        size,        # width
        size * 2,    # height (XOR image + AND mask)
        1,           # planes
        32,          # bit depth
        0,           # compression
        0,           # image size (0 for uncompressed)
        0, 0, 0, 0,
    )


def _and_mask(size: int) -> bytes:
    """Fully opaque AND mask. Row-padded to a 4-byte boundary."""
    row_bytes = ((size + 31) // 32) * 4
    return b"\x00" * (row_bytes * size)


def build() -> bytes:
    images = []
    for size in SIZES:
        # An ICO image is a BITMAPINFOHEADER, the bottom-up pixel data, and
        # the AND mask. The header is part of the image, not just metadata.
        payload = _bmp_info(size) + _pixels(size) + _and_mask(size)
        images.append((size, payload))

    header = struct.pack(
        "<HHH",
        0,              # reserved
        1,              # type: icon
        len(images),
    )

    directory = b""
    body = b""
    offset = 6 + 16 * len(images)
    for size, payload in images:
        # Dimension 0 encodes 256, since the field is a single byte.
        dimension = size if size < 256 else 0
        directory += struct.pack(
            "<BBBBHHII",
            dimension,   # width
            dimension,   # height
            0,           # palette size (0 for >8bpp)
            0,           # reserved
            1,           # colour planes
            32,          # bits per pixel
            len(payload),  # image size
            offset,      # offset of image data
        )
        body += payload
        offset += len(payload)

    return header + directory + body


def main() -> int:
    data = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(data)
    print(f"wrote {OUTPUT} ({len(data)} bytes, sizes={SIZES})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
