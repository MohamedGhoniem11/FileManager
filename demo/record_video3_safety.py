#!/usr/bin/env python3
"""
record_video3_safety.py — Video 3 "safety layer groundwork" variant.

Replays the Steps 1-3 safety story (recordable even before the intelligence
layer): fresh state -> drop a receipt -> journaled move -> append-only
journal refuses DELETE -> undo_last() reverses it -> provenance answers
"where did X go?".

Run from repo root (see recording.txt):
  .venv/bin/python demo/record_video3_safety.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from demo import reset_state as rs

rs.reset(["config", "data", "logs"])
print("== Beat 0: state reset (config + DB + journal) ==")

from demo import make_samples
from src.core.organizer import Organizer
from src.services.db_service import db_service

WATCH = REPO / "demo" / "scratch-watch"


def clear_watch():
    """Wipes the scratch watch folder so a take never starts from leftovers."""
    if WATCH.exists():
        import shutil
        for child in WATCH.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        WATCH.mkdir(parents=True)


def main():
    clear_watch()

    # Beat 1 -- drop a receipt into the watch folder
    receipt = WATCH / "invoice_amazon_march.pdf"
    receipt.write_bytes(
        make_samples.make_pdf(
            make_samples.receipt_pdf_lines("Amazon", "March 2026", "$129.99"),
            "invoice",
        )
    )
    print("== Beat 1: dropped invoice_amazon_march.pdf into watch ==")

    # Beat 2 -- journaled move (write-before-action, ADR-013)
    organizer = Organizer()
    target = WATCH / "PDFs"
    dest = organizer.move_file(receipt, target)
    print("== Beat 2: organizer.move_file (journaled, write-before-action) ==")
    print(f"  {receipt.name} -> {dest.name} in {target.name}/")

    row = db_service.journal_query(status="committed")[-1]
    print("  journal row (committed):")
    print(f"    op_type={row['op_type']} reversible={row['reversible']} "
          f"source={row['source_path']}")
    print(f"    dest={row['dest_path']}")

    # Beat 3 -- append-only enforced by the DATABASE, not the app
    print("== Beat 3: DELETE FROM journal -- refused by DB trigger ==")
    try:
        db_service.get_connection().execute("DELETE FROM journal")
        print("  !! DELETE silently succeeded (this is a bug)")
    except Exception as e:
        print(f"  refused: {e}")

    # Beat 4 -- undo_last reverses the move, inode-guarded
    undone = organizer.undo_last(1)
    print("== Beat 4: undo_last(1) ==")
    print(f"  undone={undone}, receipt back at: {receipt.exists()}")
    reversed_row = db_service.journal_query(status="reversed")[-1]
    print(f"  journal row flipped to: {reversed_row['status']}")

    # Beat 5 -- provenance answers "where did X go?"
    hits = db_service.journal_provenance(str(receipt))
    print("== Beat 5: journal_provenance(original path) ==")
    for hit in hits:
        print(f"  {hit['source_path']} -> {hit['dest_path']} ({hit['status']})")

    print("\n== Done. Quotes you can narrate over this take ==")
    print('  "Every mutation is journaled before it executes."')
    print('  "Append-only is enforced by the database itself."')
    print('  "Undo is inode-guarded -- it never clobbers a newer file."')
    print('  "And the journal answers the question future me will ask: where did it go?"')


if __name__ == "__main__":
    main()