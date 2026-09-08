"""
Roadmap 4.2 tests — confidence-scoring classifier (ADR-011).

The classifier must go beyond extension→folder:
- a receipt and a book (both .pdf) classify differently, WITH confidence
- strong content signals raise confidence; weak/absent signals lower it
- unknown extensions degrade to "Others" at low confidence
- priors recorded via record_correction() influence later classifications
  (corrector loop groundwork — roadmap 5.2 wires the UI drag into this)
"""
import struct
import zlib
from pathlib import Path

import pytest

from src.core.classifier import classifier
from src.core.priors import priors_store


# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------

def _pdf_with_text(lines: list) -> bytes:
    content = "\n".join(
        f"BT /F1 12 Tf 72 {y} Td ({line}) Tj ET" for y, line in zip(range(720, 120, -20), lines)
    )
    out = bytearray(b"%PDF-1.4\n")
    out += f"1 0 obj\n<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream\nendobj\n".encode()
    out += b"trailer\n<< /Size 1 /Root 1 0 R >>\n%%EOF\n"
    return bytes(out)


@pytest.fixture(autouse=True)
def clean_priors(tmp_path):
    """Each test gets an isolated priors store (mirrors conftest hermetics)."""
    priors_store.reset_path(tmp_path / "priors.json")
    priors_store.clear()
    yield
    priors_store.clear()


# ---------------------------------------------------------------------------
# receipt vs book — the Step 4 gate
# ---------------------------------------------------------------------------

def test_receipt_pdf_classifies_distinct_from_book(tmp_path):
    receipt = tmp_path / "invoice_amazon_march.pdf"
    receipt.write_bytes(_pdf_with_text(["INVOICE - Amazon", "Total: 42.00", "Item: Subscription"]))
    book = tmp_path / "novel.pdf"
    book.write_bytes(_pdf_with_text(["Chapter One", "It was a dark and stormy night"]))

    r = classifier.classify_with_confidence(receipt)
    b = classifier.classify_with_confidence(book)

    # both are PDFs by extension
    assert r.category == "PDFs" and b.category == "PDFs"
    # but the Analyzer separates "receipt" from "report/book" in subcategory
    assert r.subcategory == "receipt"
    assert b.subcategory != "receipt"
    # and the receipt carries a materially higher confidence
    assert r.confidence > b.confidence


def test_strong_content_raises_confidence_above_extension_prior(tmp_path):
    """A clean invoice PDF should exceed the plain extension prior."""
    plain = tmp_path / "plain.pdf"
    plain.write_bytes(_pdf_with_text(["Some PDF"]))
    invoice = tmp_path / "invoice.pdf"
    invoice.write_bytes(_pdf_with_text(["INVOICE", "Total: 12.99", "Receipt"]))

    base = classifier.classify_with_confidence(plain).confidence
    boosted = classifier.classify_with_confidence(invoice).confidence

    assert boosted > base


# ---------------------------------------------------------------------------
# confidence semantics
# ---------------------------------------------------------------------------

def test_confidence_is_bounded_01(tmp_path):
    blob = tmp_path / "blob.pdf"
    blob.write_bytes(_pdf_with_text(["gibberish xxx yyy zzz"]))

    result = classifier.classify_with_confidence(blob)

    assert 0.0 <= result.confidence <= 1.0


def test_unknown_extension_low_confidence(tmp_path):
    blob = tmp_path / "data.zzz"
    blob.write_bytes(b"\x00\xff" * 32)

    result = classifier.classify_with_confidence(blob)

    assert result.category == "Others"
    assert result.confidence < 0.5


def test_obvious_image_hits_high_confidence(tmp_path):
    # minimal valid PNG
    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x42\x2a\x66" * 8 for _ in range(8))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

    result = classifier.classify_with_confidence(img)

    assert result.category == "Images"
    assert result.confidence >= 0.8


# ---------------------------------------------------------------------------
# signals explainability (needed for the "file council" story)
# ---------------------------------------------------------------------------

def test_result_carries_visible_signals(tmp_path):
    receipt = tmp_path / "invoice.pdf"
    receipt.write_bytes(_pdf_with_text(["INVOICE", "Total: 9.99"]))

    result = classifier.classify_with_confidence(receipt)

    assert "signals" in result._asdict() or hasattr(result, "signals")
    # the score must be explainable: category + subcategory + confidence
    assert result.category and 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# priors / corrector loop (groundwork for 5.2)
# ---------------------------------------------------------------------------

def test_correction_updates_priors_and_influences_next_classification(tmp_path):
    # First sight: an ambiguous PDF lands without a receipt subcategory
    ambiguous = tmp_path / "monthly_statement.pdf"
    ambiguous.write_bytes(_pdf_with_text(["Monthly statement for account"]))

    before = classifier.classify_with_confidence(ambiguous)
    assert before.subcategory != "receipt"

    # User (or Rules Agent / drag) corrects it to 'receipt'
    classifier.record_correction(ambiguous, "receipt")

    # A similar file (same filename family) now inherits the corrected priors
    similar = tmp_path / "monthly_statement_customer.pdf"
    similar.write_bytes(_pdf_with_text(["Monthly statement for account"]))

    after = classifier.classify_with_confidence(similar)

    assert after.subcategory == "receipt"
    assert after.confidence > before.confidence