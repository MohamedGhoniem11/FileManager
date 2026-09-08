"""
Roadmap 5.1 tests — near-duplicate clustering + fingerprint cache guard.

- renamed/re-saved copies of the same text cluster together
- near-identical PNGs (one pixel apart) cluster together; unrelated images don't
- the DB fingerprint cache only recomputes when size or mtime changes
"""
import os
import struct
import zlib
from pathlib import Path

from src.core.health_engine import HealthEngine
from src.core.fingerprint import fingerprint_file
from src.services.db_service import db_service


def _make_png(width: int, height: int, pixels: bytes) -> bytes:
    """Minimal RGB 8-bit PNG (mirrors demo/make_samples.py, filter 0 rows)."""
    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def test_renamed_text_copies_cluster_together(tmp_path):
    original = tmp_path / "quarterly-report.txt"
    renamed = tmp_path / "quarterly-report-final.txt"
    original.write_text("Quarterly report\nTotal: 100\n", encoding="utf-8")
    renamed.write_text("Quarterly report\nTotal: 100\n", encoding="utf-8")

    clusters = HealthEngine().scan_directory(tmp_path)["fingerprint_clusters"]

    assert len(clusters) == 1
    cluster = clusters[0]
    assert {p.name for p in cluster["files"]} == {
        "quarterly-report.txt",
        "quarterly-report-final.txt",
    }
    assert cluster["summary"] == "2 files ≈ 1 real versions"


def test_one_pixel_apart_pngs_cluster_together(tmp_path):
    base_bytes = b"\x42\x2a\x66" * (16 * 16)
    edited_bytes = bytearray(base_bytes)
    edited_bytes[0] = 0xFF  # exactly one pixel differs

    base = tmp_path / "photo-a.png"
    edited = tmp_path / "photo-b.png"
    unrelated = tmp_path / "three-band.png"
    base.write_bytes(_make_png(16, 16, base_bytes))
    edited.write_bytes(_make_png(16, 16, bytes(edited_bytes)))
    # black | white | black bands: structurally distinct from a solid image
    bands = b"".join(bytes([0]) * 16 + bytes([255]) * 16 + bytes([0]) * 16 for _ in range(16))
    unrelated.write_bytes(_make_png(16, 16, bands))

    clusters = HealthEngine().scan_directory(tmp_path)["fingerprint_clusters"]

    # base and edited land in the SAME cluster; the banded image does not
    photo_cluster = next(c for c in clusters if base in c["files"])
    assert {p.name for p in photo_cluster["files"]} == {"photo-a.png", "photo-b.png"}
    assert unrelated not in photo_cluster["files"]

    # the scan cached fingerprints for later reuse (guard path exercised)
    assert db_service.get_cached_fingerprint(base) is not None


def test_cache_guard_recomputes_on_size_or_mtime_change(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello world", encoding="utf-8")
    stored_stat = f.stat()

    kind, value = fingerprint_file(f)["kind"], fingerprint_file(f)["value"]
    db_service.store_fingerprint(f, kind, value)

    # unchanged file -> cache hit
    assert db_service.get_cached_fingerprint(f) == (kind, value)

    # same size but bumped mtime -> cache miss (recompute trigger)
    f.write_text("hello worle", encoding="utf-8")  # same length, new mtime
    assert db_service.get_cached_fingerprint(f) is None

    # size change alone triggers recompute even with the old mtime restored
    f.write_text("hello world extra", encoding="utf-8")
    os.utime(f, (stored_stat.st_atime, stored_stat.st_mtime))
    assert db_service.get_cached_fingerprint(f) is None


def test_different_texts_do_not_cluster(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("totally unrelated words", encoding="utf-8")
    b.write_text("completely different topic", encoding="utf-8")

    clusters = HealthEngine().scan_directory(tmp_path)["fingerprint_clusters"]

    assert clusters == []