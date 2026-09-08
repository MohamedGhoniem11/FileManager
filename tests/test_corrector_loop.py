"""
Roadmap 5.2 tests — corrector loop (learning survives restarts).

The happy-path reroute (ambiguous file -> record_correction -> similar file
lands right) lives in test_classifier_confidence.py. This file covers the
store itself:
- learned priors persist across a fresh PriorsStore instance (app restart)
- stopwords never pollute the token memory
- corrections to a non-receipt subcategory reroute the same way
- evidence aggregates across every shared filename token
"""
from pathlib import Path

from src.core.classifier import classifier
from src.core.priors import PriorsStore, priors_store


def _pdf_with_text(lines: list) -> bytes:
    content = "\n".join(
        f"BT /F1 12 Tf 72 {y} Td ({line}) Tj ET" for y, line in zip(range(720, 120, -20), lines)
    )
    out = bytearray(b"%PDF-1.4\n")
    out += f"1 0 obj\n<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream\nendobj\n".encode()
    out += b"trailer\n<< /Size 1 /Root 1 0 R >>\n%%EOF\n"
    return bytes(out)


def test_priors_survive_store_reload(tmp_path):
    """A fresh PriorsStore on the same persisted path sees the learned memory."""
    first = PriorsStore()
    first.clear()  # shared hermetic path must start empty
    first.record_path(Path("monthly_statement.pdf"), "receipt")

    reloaded = PriorsStore()  # new instance, loads from the same JSON

    assert reloaded.snapshot() == {"monthly": {"receipt": 1}, "statement": {"receipt": 1}}

    first.clear()  # leave the shared path clean for later tests


def test_stopwords_excluded_from_learning(tmp_path):
    store_path = tmp_path / "priors.json"
    store = PriorsStore()
    store.reset_path(store_path)

    store.record_path(Path("the_of_report.pdf"), "receipt")

    assert store.snapshot() == {"report": {"receipt": 1}}


def test_reroute_works_for_any_subcategory(tmp_path):
    """The corrector loop is not receipt-specific: fixing a miss re-routes."""
    store_path = tmp_path / "priors.json"
    priors_store.reset_path(store_path)
    priors_store.clear()

    sketch = tmp_path / "wireframe_mockup.pdf"
    sketch.write_bytes(_pdf_with_text(["Wireframe mockup for review"]))
    assert classifier.classify_with_confidence(sketch).subcategory != "code"

    classifier.record_correction(sketch, "code")

    next_sketch = tmp_path / "wireframe_v2.pdf"
    next_sketch.write_bytes(_pdf_with_text(["Wireframe mockup for review"]))

    result = classifier.classify_with_confidence(next_sketch)

    assert result.subcategory == "code"

    priors_store.clear()


def test_priors_evidence_aggregates_across_tokens(tmp_path):
    store_path = tmp_path / "priors.json"
    store = PriorsStore()
    store.reset_path(store_path)
    store.clear()

    store.record_path(Path("quarterly_invoice_2026.pdf"), "receipt")
    store.record_path(Path("quarterly_statement.pdf"), "receipt")

    evidence = store.influence("quarterly_invoice_final.pdf")

    # both "quarterly" and "invoice" tokens contributed
    assert evidence["receipt"] >= 2