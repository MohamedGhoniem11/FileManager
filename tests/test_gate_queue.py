"""
Gate queue regression tests — needs-review persistence (Step 6.4).

The Needs Review queue is backed by gate_* columns on the files table:
- legacy DBs gain the columns via an idempotent migration,
- only ask/hold files appear in query_needs_review (auto never lists),
- resolve_review clears gate state but keeps the file indexed,
- a bare upsert (insert-or-replace without gate fields) clears the gate,
- the observer's gated path writes through to the live queue.
"""
import sqlite3
from pathlib import Path

import pytest

from src.core.classifier import Classification
from src.services.db_service import DbService
from src.services.observer import DownloadHandler

LEGACY_FILES_SCHEMA = """
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE,
    filename TEXT,
    extension TEXT,
    size INTEGER,
    category TEXT,
    created_at DATETIME,
    modified_at DATETIME
);
CREATE INDEX idx_filename ON files(filename);
CREATE INDEX idx_extension ON files(extension);
CREATE INDEX idx_category ON files(category);
"""


@pytest.fixture
def store(tmp_path):
    return DbService(str(tmp_path / "test.db"))


def _make_legacy_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.executescript(LEGACY_FILES_SCHEMA)
    conn.execute(
        "INSERT INTO files (path, filename, extension, size, category) "
        "VALUES ('/a/cv.pdf', 'cv.pdf', '.pdf', 100, 'PDFs')"
    )
    conn.commit()
    conn.close()


def test_legacy_db_migrates_gate_columns_in_place(tmp_path):
    _make_legacy_db(tmp_path / "legacy.db")
    store = DbService(str(tmp_path / "legacy.db"))

    store.get_connection()
    cols = {
        r["name"] for r in store.get_connection().execute("PRAGMA table_info(files)")
    }
    assert {"gate_status", "gate_confidence", "gate_reason", "gate_recorded_at"} <= cols

    row = store.get_connection().execute(
        "SELECT * FROM files WHERE path='/a/cv.pdf'"
    ).fetchone()
    assert row["filename"] == "cv.pdf" and row["category"] == "PDFs"
    assert row["gate_status"] is None
    assert store.count_needs_review() == 0


def test_migration_is_idempotent(tmp_path):
    _make_legacy_db(tmp_path / "legacy.db")
    store = DbService(str(tmp_path / "legacy.db"))
    store.get_connection()
    store.get_connection()
    assert store.count_needs_review() == 0


def test_gated_upsert_lands_in_queue(store, tmp_path):
    p = tmp_path / "invoice.pdf"
    p.write_text("total 100")
    store.upsert_file(
        p, "PDFs",
        gate_status="ask",
        gate_confidence=0.65,
        gate_reason="confidence 0.65 in ask band [0.50, 0.80)",
    )

    queue = store.query_needs_review()
    assert len(queue) == 1
    q = queue[0]
    assert q["filename"] == "invoice.pdf"
    assert q["gate_status"] == "ask"
    assert q["gate_confidence"] == 0.65
    assert q["gate_reason"].startswith("confidence 0.65")
    assert store.count_needs_review() == 1


def test_auto_upsert_never_lists_in_queue(store, tmp_path):
    p = tmp_path / "photo.png"
    p.write_text("img")
    store.upsert_file(p, "Images")

    assert store.count_needs_review() == 0
    assert store.query_needs_review() == []


def test_bare_upsert_clears_gate_state(store, tmp_path):
    p = tmp_path / "notes.md"
    p.write_text("hi")
    store.upsert_file(
        p, "Documents",
        gate_status="hold",
        gate_confidence=0.30,
        gate_reason="confidence 0.30 < ask 0.50",
    )
    assert store.count_needs_review() == 1

    store.upsert_file(p, "Documents")
    assert store.count_needs_review() == 0


def test_resolve_review_keeps_file_indexed(store, tmp_path):
    p = tmp_path / "report.docx"
    p.write_text("q4")
    store.upsert_file(p, "Documents", gate_status="hold", gate_confidence=0.4)

    assert store.resolve_review(p) is True
    assert store.count_needs_review() == 0

    row = store.get_connection().execute(
        "SELECT * FROM files WHERE path=?", (str(p),)
    ).fetchone()
    assert row["filename"] == "report.docx"
    assert row["category"] == "Documents"


def test_queue_orders_oldest_first(store, tmp_path):
    older = tmp_path / "older.pdf"
    newer = tmp_path / "newer.pdf"
    older.write_text("a")
    newer.write_text("b")
    store.upsert_file(older, "PDFs", gate_status="ask", gate_confidence=0.6)
    store.upsert_file(newer, "PDFs", gate_status="hold", gate_confidence=0.3)

    queue = store.query_needs_review()
    assert [q["filename"] for q in queue] == ["older.pdf", "newer.pdf"]


def test_observer_gated_file_appears_in_live_queue(tmp_path, mocker):
    mock_move = mocker.patch("src.core.organizer.organizer.move_file")
    mocker.patch(
        "src.core.classifier.classifier.classify_with_confidence",
        return_value=Classification("Documents", 0.45, None, {}),
    )
    handler = DownloadHandler()
    test_file = tmp_path / "lowconf.txt"
    test_file.write_text("content")

    handler._process_file(test_file)

    mock_move.assert_not_called()
    from src.services.db_service import db_service
    assert db_service.count_needs_review() == 1
    q = db_service.query_needs_review()
    assert q[0]["filename"] == "lowconf.txt"
    assert q[0]["gate_status"] == "hold"
    assert q[0]["gate_confidence"] == 0.45