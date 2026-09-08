"""
Tests for src/core/fingerprint.py — perceptual, text, and binary fingerprints.

The PNG builder mirrors demo/make_samples.py: a minimal RGB 8-bit PNG writer
(zlib + struct, one 0-filter byte per scanline) so the suite stays hermetic
and standard-library-only.
"""
import hashlib
import struct
import zlib
from pathlib import Path

from src.core.fingerprint import (
    fingerprint_file,
    hamming_distance,
    png_dhash,
    sha256_fingerprint,
    text_fingerprint,
)


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def make_png(width: int, height: int, pixels: bytes) -> bytes:
    """Builds a valid PNG from raw RGB rows (filter byte 0 per row)."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def make_filtered_png(width: int, height: int, pixels: bytes, row_filters: tuple) -> bytes:
    """Builds an RGB PNG where row y is encoded with row_filters[y % len(...)]."""
    bpp = 3
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = bytearray()
    prev = bytes(width * bpp)
    for y in range(height):
        row = pixels[y * width * bpp:(y + 1) * width * bpp]
        filt = row_filters[y % len(row_filters)]
        out = bytearray(width * bpp)
        for i in range(width * bpp):
            left = row[i - bpp] if i >= bpp else 0
            upper = prev[i]
            upper_left = prev[i - bpp] if i >= bpp else 0
            if filt == 1:
                out[i] = (row[i] - left) & 0xFF
            elif filt == 2:
                out[i] = (row[i] - upper) & 0xFF
            elif filt == 3:
                out[i] = (row[i] - ((left + upper) // 2)) & 0xFF
            elif filt == 4:
                out[i] = (row[i] - _paeth(left, upper, upper_left)) & 0xFF
            else:
                out[i] = row[i]
        rows += bytes([filt]) + bytes(out)
        prev = row
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(rows)))
        + _chunk(b"IEND", b"")
    )


def write_png(path: Path, pixels: bytes, width: int = 16, height: int = 16) -> Path:
    path.write_bytes(make_png(width, height, pixels))
    return path


# ---------------------------------------------------------------------------
# png_dhash
# ---------------------------------------------------------------------------

def test_png_dhash_on_generated_png(tmp_path):
    black = b"\x00" * (16 * 16 * 3)
    white = b"\xff" * (16 * 16 * 3)
    a = write_png(tmp_path / "black_a.png", black)
    b = write_png(tmp_path / "black_b.png", black)
    c = write_png(tmp_path / "white.png", white)
    h_a = png_dhash(a)
    h_b = png_dhash(b)
    h_c = png_dhash(c)
    assert isinstance(h_a, int)
    assert h_a == h_b
    assert h_a != h_c


def test_png_dhash_hamming_distance(tmp_path):
    base = bytearray(b"\x42\x2a\x66" * (16 * 16))
    edited = bytearray(base)
    edited[0] = 0xFF  # exactly one pixel differs
    h_a = png_dhash(write_png(tmp_path / "base.png", bytes(base)))
    h_b = png_dhash(write_png(tmp_path / "edited.png", bytes(edited)))
    assert h_a is not None and h_b is not None
    assert hamming_distance(h_a, h_b) <= 4


def test_png_dhash_returns_none_for_garbage(tmp_path):
    p = tmp_path / "garbage.png"
    p.write_bytes(b"not a png")
    assert png_dhash(p) is None


def test_png_dhash_handles_all_filter_types(tmp_path):
    vals = bytes(((x * 7 + y * 13) % 256) for y in range(16) for x in range(16))
    rgb = b"".join(bytes([v]) * 3 for v in vals)
    plain = tmp_path / "plain.png"
    plain.write_bytes(make_png(16, 16, rgb))
    filtered = tmp_path / "filtered.png"
    filtered.write_bytes(make_filtered_png(16, 16, rgb, (0, 1, 2, 3, 4)))
    assert png_dhash(plain) == png_dhash(filtered)


# ---------------------------------------------------------------------------
# text_fingerprint
# ---------------------------------------------------------------------------

def test_text_fingerprint_deterministic_and_normalized():
    a = text_fingerprint("Hello World")
    b = text_fingerprint("Hello World")
    c = text_fingerprint("hello  world")
    d = text_fingerprint("hello friends")
    assert a == b
    assert a == c
    assert a != d


# ---------------------------------------------------------------------------
# hamming_distance
# ---------------------------------------------------------------------------

def test_hamming_distance():
    assert hamming_distance(0, 0) == 0
    assert hamming_distance(0b1111, 0b0000) == 4
    assert hamming_distance(0b1010, 0b1111) == 2
    assert hamming_distance(0b1010, 0b1111) == hamming_distance(0b1111, 0b1010)


# ---------------------------------------------------------------------------
# fingerprint_file
# ---------------------------------------------------------------------------

def test_fingerprint_file_dispatches_kinds(tmp_path):
    image = write_png(tmp_path / "photo.png", b"\x00" * (16 * 16 * 3))
    text = tmp_path / "note.txt"
    text.write_text("Hello World", encoding="utf-8")
    binary = tmp_path / "blob.xyz"
    binary.write_bytes(b"\x00\x01\x02\x03")

    img_res = fingerprint_file(image)
    txt_res = fingerprint_file(text)
    bin_res = fingerprint_file(binary)

    assert img_res["kind"] == "image"
    assert isinstance(img_res["value"], int)
    assert txt_res["kind"] == "text"
    assert isinstance(txt_res["value"], int)
    assert bin_res["kind"] == "binary"
    assert isinstance(bin_res["value"], str)
    assert bin_res["value"] == hashlib.sha256(b"\x00\x01\x02\x03").hexdigest()


# ---------------------------------------------------------------------------
# sha256_fingerprint
# ---------------------------------------------------------------------------

def test_sha256_fingerprint_matches_hashlib(tmp_path):
    data = b"fingerprint test bytes\x00\x01\x02"
    p = tmp_path / "data.bin"
    p.write_bytes(data)
    assert sha256_fingerprint(p) == hashlib.sha256(data).hexdigest()