#!/usr/bin/env python3
"""
make_samples.py — generate the scratch Downloads folder for demo recordings.

Creates demo/scratch-downloads/ with:
  - invoice_amazon_march.pdf  (valid minimal PDF, receipt text)
  - receipt_uber_jan25.pdf    (valid minimal PDF, second receipt for undo demo)
  - photo_a.png / photo_a_edit.png (near-duplicate images - Step 5 dedup demo)
  - archive_opaque.xyz        (unknown extension - "Others" ghetto demo)

All files are generated from scratch with the standard library only —
no fake blobs, every file opens.

Usage:
  python demo/make_samples.py [--out demo/scratch-downloads]
"""
import argparse
import struct
import zlib
from pathlib import Path

# -- minimal PNG writer (RGB, 8-bit) -------------------------------------------

def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
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
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


# -- minimal PDF writer (1 page, Helvetica text) --------------------------------

def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines: list, title: str) -> bytes:
    """Builds a minimal valid 1-page PDF showing the given text lines."""
    content = "\n".join(
        f"BT /F1 12 Tf 72 {y} Td ({_pdf_escape(line)}) Tj ET" for y, line in zip(range(720, 120, -20), lines)
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


# -- sample content --------------------------------------------------------------

def receipt_pdf_lines(merchant: str, date: str, total: str) -> list:
    return [
        f"INVOICE - {merchant}",
        date,
        "Item: Premium Subscription",
        "Qty: 1",
        f"Total: {total}",
        "Thank you for your purchase.",
    ]


def near_dup_pngs(width: int = 16, height: int = 16):
    """Two 16x16 PNGs that are visually identical except one pixel."""
    base = bytearray(b"\x42\x2a\x66" * (width * height))  # uniform colour
    normal = bytes(base)
    edited = bytearray(base)
    edited[0] = 0xFF  # one pixel differs
    return make_png(width, height, normal), make_png(width, height, bytes(edited))


def opaque_blob() -> bytes:
    """Deterministic 'unknown format' bytes - demonstrates the Others ghetto."""
    import hashlib
    seed = hashlib.sha256(b"FileManager demo opaque file").digest()
    return bytes(b ^ 0xA5 for b in seed * 8)  # non-text, non-image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "scratch-downloads"),
        help="Output folder (default: demo/scratch-downloads)",
    )
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    (out / "invoice_amazon_march.pdf").write_bytes(
        make_pdf(receipt_pdf_lines("Amazon", "March 2026", "$129.99"), "invoice")
    )
    (out / "receipt_uber_jan25.pdf").write_bytes(
        make_pdf(receipt_pdf_lines("Uber", "January 2025", "$24.50"), "receipt")
    )
    photo_a, photo_a_edit = near_dup_pngs()
    (out / "photo_a.png").write_bytes(photo_a)
    (out / "photo_a_edit.png").write_bytes(photo_a_edit)
    (out / "archive_opaque.xyz").write_bytes(opaque_blob())

    print(f"Samples written to {out}/")
    for f in sorted(out.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()