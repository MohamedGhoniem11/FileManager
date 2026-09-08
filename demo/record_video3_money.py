#!/usr/bin/env python3
"""
record_video3_money.py — Video 3 "Agentic Upgrade" money-shot driver.

Replays the File Council sequence with REAL app state, printing every beat:
  reset  -> make samples -> drop receipt -> journal row -> confidence + gate
         -> low-confidence asks -> correct once -> similar file lands right.

Run from repo root (see recording.txt) *after* demo/reset_state.py and
demo/make_samples.py; the script re-resets state itself for safety, then
builds a fresh scratch watch folder so the take never touches real Downloads.

Usage:
  .venv/bin/python demo/record_video3_money.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Beat 0 -- fresh state BEFORE importing app singletons (they load on import)
from demo import reset_state as rs

rs.reset(["config", "data", "logs"])
print("== Beat 0: state reset (config + DB + journal + priors) ==")

# Now import the live app with a clean slate
from demo import make_samples
from src.services.config_service import config_service
from src.services.observer import DownloadHandler
from src.services.db_service import db_service
from src.core.classifier import classifier
from src.core.gate import decide as gate_decide

WATCH = REPO / "demo" / "scratch-watch"


def clear_watch():
    """Wipes the scratch watch folder for a clean take."""
    if WATCH.exists():
        for child in WATCH.iterdir():
            if child.is_dir():
                import shutil
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        WATCH.mkdir(parents=True)


def show(category_label, classification, decision):
    """Prints one beat's evidence: classification + gate verdict."""
    print(f"  category={classification.category!r} "
          f"confidence={classification.confidence} "
          f"subcategory={classification.subcategory}")
    print(f"  signals: ext_prior={classification.signals['ext_prior']} "
          f"keywords={classification.signals['matched_keywords']}")
    print(f"  gate: {decision.action} "
          f"(effective {decision.effective_confidence}, "
          f"band {decision.band})  -- {decision.reason}")


def last_journal_row():
    """Most recent committed journal entry."""
    entries = db_service.journal_query(status="committed")
    return entries[-1] if entries else None


def main():
    clear_watch()
    print(f"== Beat 1: samples into {WATCH.name}/ ==")

    # Receipt PDF (high confidence, auto path)
    receipt = WATCH / "invoice_amazon_march.pdf"
    receipt.write_bytes(
        make_samples.make_pdf(
            make_samples.receipt_pdf_lines("Amazon", "March 2026", "$129.99"),
            "invoice",
        )
    )

    # Low-confidence PDF (generic text, no receipt keywords)
    low_conf = WATCH / "meeting_notes_march.pdf"
    low_conf.write_bytes(
        make_samples.make_pdf(
            [
                "Quarterly review",
                "Attendance: team",
                "Action items discussed",
                "Next steps agreed",
            ],
            "notes",
        )
    )

    # Opaque unknown file (hold band)
    opaque = WATCH / "archive_opaque.xyz"
    opaque.write_bytes(make_samples.opaque_blob())

    print("  invoice_amazon_march.pdf  (receipt text inside)")
    print("  meeting_notes_march.pdf   (generic text)")
    print("  archive_opaque.xyz        (unknown extension/content)")

    print("\n== Beat 2: drop the receipt -- analyzer reads INSIDE the PDF ==")
    classification = classifier.classify_with_confidence(receipt)
    decision = gate_decide(
        classification.category,
        classification.confidence,
        config_service.get("confidence_thresholds") or None,
    )
    show("receipt", classification, decision)
    assert decision.action == "auto", "receipt must auto-move for the demo"

    print("\n== Beat 3: File Council moves it -- journal row ==")
    DownloadHandler()._process_file(receipt)
    row = last_journal_row()
    print(f"  op_type={row['op_type']} reversible={row['reversible']}")
    print(f"  {row['source_path']} -> {row['dest_path']}  (committed)")
    moved_dest = Path(row["dest_path"])
    assert moved_dest.exists(), "receipt should have moved"

    print("\n== Beat 4: low-confidence file -- gate ASKS, nothing moves ==")
    low_class = classifier.classify_with_confidence(low_conf)
    low_decision = gate_decide(
        low_class.category,
        low_class.confidence,
        config_service.get("confidence_thresholds") or None,
    )
    show("low-conf", low_class, low_decision)
    assert low_decision.action != "auto", "generic file must not auto-move"
    DownloadHandler()._process_file(low_conf)
    assert low_conf.exists(), "ask/hold file stays in place"
    print(f"  {low_conf.name} still in watch (indexed in place, not moved)")

    print("\n== Beat 5: opaque file -- gate HOLDS ==")
    opq_class = classifier.classify_with_confidence(opaque)
    opq_decision = gate_decide(
        opq_class.category,
        opq_class.confidence,
        config_service.get("confidence_thresholds") or None,
    )
    show("opaque", opq_class, opq_decision)
    DownloadHandler()._process_file(opaque)
    assert opaque.exists()
    print(f"  {opaque.name} still in watch (hold band)")

    print("\n== Beat 6: correct once (priors learn) ==")
    before = classifier.classify_with_confidence(low_conf)
    print(f"  before: subcategory={before.subcategory} "
          f"confidence={before.confidence}")
    classifier.record_correction(low_conf, "receipt")
    sample = classifier.classify_with_confidence(low_conf)
    print(f"  after : subcategory={sample.subcategory} "
          f"confidence={sample.confidence}")
    print(f"  priors evidence: {dict(sample.signals['priors'])}")

    print("\n== Beat 7: a SIMILAR file lands right ==")
    similar = WATCH / "meeting_notes_april.pdf"
    similar.write_bytes(
        make_samples.make_pdf(
            [
                "Quarterly review",
                "Attendance: team",
                "Action items discussed",
                "Next steps agreed",
            ],
            "notes",
        )
    )
    sim_class = classifier.classify_with_confidence(similar)
    sim_decision = gate_decide(
        sim_class.category,
        sim_class.confidence,
        config_service.get("confidence_thresholds") or None,
    )
    show("similar", sim_class, sim_decision)
    DownloadHandler()._process_file(similar)
    if sim_decision.action == "auto":
        print(f"  {similar.name} moved (priors lifted it over auto threshold)")
    else:
        print(f"  {similar.name} asked again -- correction-shaped, honest")

    print("\n== Done. Quotes you can narrate over this take ==")
    print('  "Inside the PDF -- not the extension."')
    print('  "Above 0.80 it moves and journals itself. One click = undo."')
    print('  "Too unsure? It asks. Unknown? It holds. It never guesses destructively."')
    print('  "I corrected it once -- the priors remember."')


if __name__ == "__main__":
    main()