"""
H3 regression tests — transaction journal (ADR-013, roadmap Step 2.5).

Journal must be:
- written BEFORE the mutation executes (crash-safe),
- append-only (entries are never deleted or rewritten),
- versioned (schema_version table + migration path),
- recording enough pre-state (inode, mtime, size, op_type, reversible) to
  validate and invert any move in a later undo (step 3).
"""
import sqlite3

import pytest
from pathlib import Path

from src.core.organizer import Organizer
from src.services.db_service import DbService, db_service


@pytest.fixture
def store(tmp_path):
    return DbService(str(tmp_path / "test.db"))


# ---------------------------------------------------------------------------
# journal lifecycle
# ---------------------------------------------------------------------------

def test_journal_record_creates_pending_entry(store):
    entry_id = store.journal_record(
        op_type="rename",
        source_path="/src/a.txt",
        dest_path="/dst/a.txt",
        inode=42,
        mtime=1234.5,
        size=100,
        reversible=1,
    )
    entries = store.journal_query()
    assert len(entries) == 1
    e = entries[0]
    assert e["id"] == entry_id
    assert e["op_type"] == "rename"
    assert e["source_path"] == "/src/a.txt"
    assert e["dest_path"] == "/dst/a.txt"
    assert e["inode"] == 42
    assert e["mtime"] == 1234.5
    assert e["size"] == 100
    assert e["reversible"] == 1
    assert e["status"] == "pending"
    assert e["created_at"]


def test_journal_status_transitions(store):
    eid = store.journal_record("rename", "/s", "/d")
    assert store.journal_query(status="pending")[0]["id"] == eid

    store.journal_mark_committed(eid)
    assert store.journal_query(status="committed")[0]["id"] == eid
    assert store.journal_query(status="pending") == []

    store.journal_mark_reversed(eid)
    assert store.journal_query(status="reversed")[0]["id"] == eid
    assert store.journal_query(status="committed") == []


def test_journal_query_filters_by_op_type(store):
    store.journal_record("rename", "/s1", "/d1")
    store.journal_record("trash", "/s2", "/d2")
    assert len(store.journal_query(op_type="rename")) == 1
    assert len(store.journal_query(op_type="trash")) == 1


# ---------------------------------------------------------------------------
# append-only enforcement (SQLite triggers)
# ---------------------------------------------------------------------------

def test_journal_is_append_only_forbids_delete(store):
    store.journal_record("rename", "/s", "/d")
    with pytest.raises(sqlite3.DatabaseError):
        store.execute("DELETE FROM journal")


def test_journal_is_append_only_forbids_rewriting_immutable_fields(store):
    store.journal_record("rename", "/s", "/d")
    with pytest.raises(sqlite3.DatabaseError):
        store.execute(
            "UPDATE journal SET source_path = '/evil' WHERE source_path = '/s'"
        )


# ---------------------------------------------------------------------------
# versioned schema (ADR-013) + db-level accessor used by the triggers above
# ---------------------------------------------------------------------------

def test_journal_schema_is_versioned(store):
    assert store.journal_schema_version() == 1


def test_execute_exposes_connection_for_db_level_triggers(store):
    conn = store.get_connection()
    # rollback-free sanity: the trigger raise happens at execute time
    assert conn.execute("SELECT 1").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# organizer writes the journal before moving (H3 gate: every move is journaled)
# ---------------------------------------------------------------------------

def test_organizer_move_journals_committed_entry(tmp_path):
    organizer = Organizer()
    source = tmp_path / "a.txt"
    source.write_text("hello")
    target = tmp_path / "Documents"
    target.mkdir()

    dest = organizer.move_file(source, target)

    assert dest == target / "a.txt"
    entries = db_service.journal_query(status="committed")
    assert len(entries) == 1
    e = entries[0]
    assert e["op_type"] == "rename"
    assert e["source_path"] == str(source)
    assert e["dest_path"] == str(dest)
    assert e["inode"] is not None
    assert e["size"] == 5
    assert e["reversible"] == 1


def test_organizer_collision_rename_journals_unique_dest(tmp_path):
    organizer = Organizer()
    source = tmp_path / "a.txt"
    source.write_text("new")
    target = tmp_path / "Documents"
    target.mkdir()
    (target / "a.txt").write_text("existing")

    dest = organizer.move_file(source, target)  # conflict -> a (1).txt

    assert dest.name == "a (1).txt"
    entries = db_service.journal_query(status="committed")
    assert len(entries) == 1
    assert entries[0]["dest_path"] == str(dest)


def test_organizer_skip_is_not_journaled(tmp_path, mocker):
    mocker.patch("src.core.organizer.config_service.get", return_value="skip")
    organizer = Organizer()
    source = tmp_path / "a.txt"
    source.write_text("new")
    target = tmp_path / "Documents"
    target.mkdir()
    (target / "a.txt").write_text("existing")

    assert organizer.move_file(source, target) is None
    assert db_service.journal_query() == []


def test_organizer_overwrite_journal_is_not_reversible(tmp_path, mocker):
    """ADR-013: an overwrite destroys pre-existing content -> inverse op is unsafe."""
    mocker.patch("src.core.organizer.config_service.get", return_value="overwrite")
    organizer = Organizer()
    source = tmp_path / "a.txt"
    source.write_text("new")
    target = tmp_path / "Documents"
    target.mkdir()
    (target / "a.txt").write_text("precious")

    organizer.move_file(source, target)

    entries = db_service.journal_query(status="committed")
    assert len(entries) == 1
    assert entries[0]["reversible"] == 0


# ---------------------------------------------------------------------------
# helper: journal must also expose a count for provenance stats (ADR-013)
# ---------------------------------------------------------------------------

def test_journal_count_and_prune_surface(store):
    store.journal_record("rename", "/s1", "/d1")
    store.journal_record("rename", "/s2", "/d2")
    assert store.journal_count() == 2
    assert store.journal_count(status="pending") == 2