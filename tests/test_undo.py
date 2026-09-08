"""
H3 regression tests — journal-backed undo (ADR-016, roadmap Step 3).

Undo semantics under test:
- only *committed* entries are undoable; pending entries are never touched
- reverse replay is LIFO: undo_last(1) reverses the most recent action
- only reversible entries (reversible=1, op_type='rename') are candidates
- a move is safely reversible only when:
    * dest still exists
    * source is free (never clobber a newer file at the source path)
    * the file at dest is the same file we moved (inode matches the journal)
- every successful undo marks the entry 'reversed'
- provenance queries answer "where did X go?" for any known path
"""
import pytest
from pathlib import Path

from src.core.organizer import Organizer
from src.services.db_service import db_service


@pytest.fixture
def organizer():
    return Organizer()


def _make_file(parent: Path, name: str, content: str = "data") -> Path:
    p = parent / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# single undo
# ---------------------------------------------------------------------------

def test_undo_restores_single_move(tmp_path, organizer):
    src = _make_file(tmp_path, "a.txt")
    target = tmp_path / "Documents"
    target.mkdir()

    dest = organizer.move_file(src, target)
    assert dest.exists() and not src.exists()

    undone = organizer.undo_last(1)

    assert undone == 1
    assert src.exists()
    assert not dest.exists()
    entries = db_service.journal_query(status="reversed")
    assert len(entries) == 1
    assert entries[0]["source_path"] == str(src)
    assert entries[0]["dest_path"] == str(dest)


def test_undo_reverse_replay_is_lifo(tmp_path, organizer):
    # file chained through two moves: a.txt -> Documents -> Papers
    src = _make_file(tmp_path, "a.txt")
    docs = tmp_path / "Documents"
    papers = tmp_path / "Papers"
    docs.mkdir()
    papers.mkdir()

    first = organizer.move_file(src, docs)       # move 1 recorded
    second = organizer.move_file(first, papers)  # move 2 recorded

    undone = organizer.undo_last(1)              # must reverse move 2 first

    assert undone == 1
    assert first.exists() and not second.exists()  # back at Documents
    assert not src.exists()                        # not at origin yet
    entries = db_service.journal_query()
    assert entries[0]["status"] == "committed"     # move 1 untouched
    assert entries[1]["status"] == "reversed"      # move 2 reversed


# ---------------------------------------------------------------------------
# batched undo
# ---------------------------------------------------------------------------

def test_undo_batch_reverses_multiple_moves(tmp_path, organizer):
    target = tmp_path / "Documents"
    target.mkdir()
    files = [_make_file(tmp_path, f"f{i}.txt", f"v{i}") for i in range(3)]
    dests = [organizer.move_file(f, target) for f in files]
    assert all(d.exists() for d in dests)

    undone = organizer.undo_last(3)

    assert undone == 3
    assert all(not d.exists() for d in dests)
    assert all(f.read_text() == f"v{i}" for i, f in enumerate(files))
    assert db_service.journal_count(status="reversed") == 3
    assert db_service.journal_count(status="committed") == 0


def test_undo_batch_stops_at_count(tmp_path, organizer):
    target = tmp_path / "Documents"
    target.mkdir()
    a = _make_file(tmp_path, "a.txt")
    b = _make_file(tmp_path, "b.txt")
    dest_a = organizer.move_file(a, target)
    dest_b = organizer.move_file(b, target)

    undone = organizer.undo_last(1)   # only the newest move (b)

    assert undone == 1
    assert b.exists() and not dest_b.exists()
    assert dest_a.exists()            # a stays in Documents
    assert db_service.journal_count(status="reversed") == 1
    assert db_service.journal_count(status="committed") == 1


# ---------------------------------------------------------------------------
# safety: what undo must NEVER do
# ---------------------------------------------------------------------------

def test_undo_never_reverses_non_reversible_overwrite(tmp_path, mocker, organizer):
    mocker.patch("src.core.organizer.config_service.get", return_value="overwrite")
    target = tmp_path / "Documents"
    target.mkdir()
    (target / "a.txt").write_text("precious")
    src = _make_file(tmp_path, "a.txt", "new")

    organizer.move_file(src, target)   # reversible=0 (overwrite)

    undone = organizer.undo_last(1)

    assert undone == 0
    assert not src.exists()            # nothing resurrected at source
    assert (target / "a.txt").exists()
    assert db_service.journal_count(status="committed") == 1


def test_undo_skips_newest_when_not_reversible(tmp_path, mocker, organizer):
    # first move is normal (reversible); newest move is an overwrite
    a = _make_file(tmp_path, "a.txt")
    target = tmp_path / "Documents"
    target.mkdir()
    dest_a = organizer.move_file(a, target)         # entry #1, reversible

    mocker.patch("src.core.organizer.config_service.get", return_value="overwrite")
    (target / "b.txt").write_text("precious")
    b = _make_file(tmp_path, "b.txt", "new")
    organizer.move_file(b, target)                 # entry #2, NOT reversible

    undone = organizer.undo_last(1)   # scans newest -> oldest

    assert undone == 1                # skipped #2, reversed #1
    assert a.exists() and not dest_a.exists()
    assert (target / "b.txt").exists()  # overwritten file untouched
    entries = db_service.journal_query()
    assert entries[0]["status"] == "reversed"
    assert entries[1]["status"] == "committed"


def test_undo_skips_when_dest_file_gone(tmp_path, organizer):
    src = _make_file(tmp_path, "a.txt")
    target = tmp_path / "Documents"
    target.mkdir()
    dest = organizer.move_file(src, target)
    dest.unlink()                      # user deleted it afterwards

    undone = organizer.undo_last(1)

    assert undone == 0
    assert not src.exists()
    assert db_service.journal_count(status="committed") == 1


def test_undo_does_not_clobber_new_source_file(tmp_path, organizer):
    src = _make_file(tmp_path, "a.txt")
    target = tmp_path / "Documents"
    target.mkdir()
    organizer.move_file(src, target)
    replacement = _make_file(tmp_path, "a.txt", "brand new file")

    undone = organizer.undo_last(1)

    assert undone == 0
    assert replacement.read_text() == "brand new file"  # untouched
    assert (target / "a.txt").exists()                 # moved file stays put
    assert db_service.journal_count(status="committed") == 1


def test_undo_skips_when_dest_replaced_by_different_file(tmp_path, organizer):
    src = _make_file(tmp_path, "a.txt", "original")
    target = tmp_path / "Documents"
    target.mkdir()
    dest = organizer.move_file(src, target)

    dest.unlink()                       # different inode now
    dest.write_text("replacement")

    undone = organizer.undo_last(1)

    assert undone == 0
    assert dest.read_text() == "replacement"
    assert not src.exists()
    assert db_service.journal_count(status="committed") == 1


def test_undo_only_reverses_committed_entries(tmp_path, organizer):
    src = _make_file(tmp_path, "a.txt")
    target = tmp_path / "Documents"
    target.mkdir()
    organizer.move_file(src, target)                    # committed entry

    pending_id = db_service.journal_record(            # crash-left pending
        "rename", "/src/x.txt", "/dst/x.txt"
    )

    undone = organizer.undo_last(1)

    assert undone == 1
    assert src.exists()
    pending = db_service.journal_query(status="pending")
    assert len(pending) == 1 and pending[0]["id"] == pending_id


# ---------------------------------------------------------------------------
# provenance queries ("where did X go?")
# ---------------------------------------------------------------------------

def test_provenance_finds_where_file_went(tmp_path, organizer):
    src = _make_file(tmp_path, "a.txt")
    target = tmp_path / "Documents"
    target.mkdir()
    dest = organizer.move_file(src, target)

    by_src = db_service.journal_provenance(str(src))
    by_dest = db_service.journal_provenance(str(dest))

    assert len(by_src) == 1 and by_src[0]["dest_path"] == str(dest)
    assert len(by_dest) == 1 and by_dest[0]["source_path"] == str(src)


def test_provenance_returns_empty_for_unknown_path(tmp_path):
    assert db_service.journal_provenance("/nowhere/anything.txt") == []


def test_provenance_orders_by_id_and_includes_all_moves(tmp_path, organizer):
    # file chained through two moves: a.txt -> Documents -> Papers
    src = _make_file(tmp_path, "a.txt")
    docs = tmp_path / "Documents"
    papers = tmp_path / "Papers"
    docs.mkdir()
    papers.mkdir()
    first = organizer.move_file(src, docs)        # move 1
    second = organizer.move_file(first, papers)   # move 2

    # the intermediate path is dest of move 1 AND source of move 2
    hits = db_service.journal_provenance(str(first))
    assert len(hits) == 2
    assert [e["id"] for e in hits] == sorted(e["id"] for e in hits)

    # asking about the final path surfaces the move that produced it
    final_hits = db_service.journal_provenance(str(second))
    assert len(final_hits) == 1
    assert final_hits[0]["dest_path"] == str(second)