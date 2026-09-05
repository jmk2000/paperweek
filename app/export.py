"""Lossless PNG writer for the actual LVGL framebuffer; standard library only."""
from __future__ import annotations
from pathlib import Path
import struct
import zlib
from .storage import atomic_write


def ppm_to_png(source: Path, destination: Path) -> None:
    with source.open("rb") as f:
        if f.readline().strip() != b"P6":
            raise ValueError("Expected an RGB PPM framebuffer.")
        width, height = map(int, f.readline().split())
        if (width, height) != (1600, 1200) or f.readline().strip() != b"255":
            raise ValueError("Expected a 1600 x 1200, 8-bit RGB framebuffer.")
        pixels = f.read()
    if len(pixels) != width * height * 3:
        raise ValueError("Incomplete framebuffer export.")
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    stride = width * 3
    scanlines = b"".join(b"\x00" + pixels[y * stride:(y + 1) * stride] for y in range(height))
    result = b"\x89PNG\r\n\x1a\n"
    result += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    # Physical target: 1600 pixels across 270.4 mm (about 150 ppi, NOT 200 ppi).
    # pHYs is advisory; verify actual print size on paper.
    result += chunk(b"pHYs", struct.pack(">IIB", round(1600 / .2704), round(1200 / .2028), 1))
    result += chunk(b"IDAT", zlib.compress(scanlines, 6)) + chunk(b"IEND", b"")
    atomic_write(destination, result)
