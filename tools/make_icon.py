#!/usr/bin/env python3
"""Generate ``assets/winx.ico`` from scratch (no image libraries needed).

The icon is a rounded dark tile with a bright "spark/X" glyph — the same mark
the app uses in its window title.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "assets" / "winx.ico"
BG = (16, 21, 29, 255)        # #10151d
ACCENT = (76, 194, 255, 255)  # #4cc2ff
SIZES = (16, 24, 32, 48, 64, 128)


def rounded_alpha(x: int, y: int, size: int, radius: float) -> float:
    """Coverage (0..1) of a rounded-rect mask at pixel (x, y)."""
    fx, fy = x + 0.5, y + 0.5
    cx = min(max(fx, radius), size - radius)
    cy = min(max(fy, radius), size - radius)
    dist = math.hypot(fx - cx, fy - cy)
    if dist <= radius:
        return 1.0
    return max(0.0, 1.0 - (dist - radius))


def glyph(x: int, y: int, size: int) -> float:
    """A four-pointed spark, evaluated as a signed distance field."""
    u = (x + 0.5) / size * 2.0 - 1.0
    v = (y + 0.5) / size * 2.0 - 1.0
    ax, ay = abs(u), abs(v)
    # |x| + |y| <= r makes a diamond; subtract a lobe to pull in the waist
    diamond = ax + ay
    waist = 0.62 + 0.42 * (1.0 - min(1.0, math.hypot(u, v)))
    if diamond >= waist:
        return 0.0
    edge = waist - diamond
    return min(1.0, edge * size * 0.45)


def render(size: int) -> bytes:
    """BGRA pixel rows, bottom-up, as expected by the ICO/BMP container."""
    radius = size * 0.22
    rows: list[bytes] = []
    for y in range(size):
        row = bytearray()
        pixel_y = size - 1 - y  # BMP rows are stored bottom-up
        for x in range(size):
            cover = rounded_alpha(x, pixel_y, size, radius)
            glow = glyph(x, pixel_y, size)
            r, g, b, _a = BG
            if glow > 0:
                r = int(BG[0] + (ACCENT[0] - BG[0]) * glow)
                g = int(BG[1] + (ACCENT[1] - BG[1]) * glow)
                b = int(BG[2] + (ACCENT[2] - BG[2]) * glow)
            alpha = int(255 * cover)
            # premultiply against a transparent background so edges look clean
            row += bytes((int(b * cover), int(g * cover), int(r * cover), alpha))
        rows.append(bytes(row))
    return b"".join(rows)


def build_ico(path: Path) -> None:
    images = [(size, render(size)) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    directory = b""
    payload = b""
    for size, pixels in images:
        # BITMAPINFOHEADER: height is doubled for the (empty) AND mask
        dib = struct.pack(
            "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0
        )
        mask_row = ((size + 31) // 32) * 4
        mask = b"\x00" * (mask_row * size)
        blob = dib + pixels + mask
        directory += struct.pack(
            "<BBBBHHII",
            size % 256,
            size % 256,
            0,
            0,
            1,
            32,
            len(blob),
            offset + len(payload),
        )
        payload += blob
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + directory + payload)


if __name__ == "__main__":
    build_ico(OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
