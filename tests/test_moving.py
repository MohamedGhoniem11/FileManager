"""
Step 7 wrap-up — moving mechanics under test (roadmap 7.x + observer flow).

Covered here:
- collision strategies: skip, overwrite, rename (unique-path numbering)
- move_to_misc / delete_file helpers
- move_file journaling  (every mutation recorded before executing)
- full observer _process_file flow: gate auto-move, gate ask/hold, rules scoping
Matches hermetic style of tests/test_services.py: all watch dirs under tmp_path.
"""
import time
from pathlib import Path

import pytest

from src.core.organizer import Organizer
from src.core.classifier import Classification
from src.services.observer import DownloadHandler
from src.services.config_service import config_service
from src.services.db_service import db_service


@pytest.fixture
def organizer():
    return Organizer()


def _wait_for(predicate, timeout: float = 3.0, interval: float = 0.05) -> bool:
    """Polls predicate() until it returns truthy or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------------------------------------------------------------------------
# collision strategies
# ---------------------------------------------------------------------------

def test_collision_default_renames_with_counter(tmp_path, organizer):
    target = tmp_path / "Documents"
    target.mkdir()
    (target / "a.txt").write_text("existing")
    src = tmp_path / "a.txt"
    src.write_text("new")

    dest = organizer.move_file(src, target)

    assert dest.name == "a (1).txt"
    assert dest.exists()
    assert not src.exists()
    assert (target / "a.txt").read_text() == "existing"


def test_collision_skip_leaves_file_in_place(tmp_path, mocker, organizer):
    mocker.patch("src.core.organizer.config_service.get", return_value="skip")
    target = tmp_path / "Documents"
    target.mkdir()
    (target / "a.txt").write_text("existing")
    src = tmp_path / "a.txt"
    src.write_text("new")

    dest = organizer.move_file(src, target)

    assert dest is None
    assert src.exists()                     # source untouched
    assert (target / "a.txt").read_text() == "existing"


def test_collision_overwrite_journaled_non_reversible(tmp_path, mocker, organizer):
    mocker.patch("src.core.organizer.config_service.get", return_value="overwrite")
    target = tmp_path / "Documents"
    target.mkdir()
    (target / "a.txt").write_text("precious")
    src = tmp_path / "a.txt"
    src.write_text("new")

    dest = organizer.move_file(src, target)

    assert dest == target / "a.txt"
    assert (target / "a.txt").read_text() == "new"
    entry = db_service.journal_query(status="committed")[0]
    assert entry["reversible"] == 0           # overwrite must never be undone


def test_collision_rename_chain_keeps_numbering(tmp_path, organizer):
    target = tmp_path / "Documents"
    target.mkdir()
    for name in ("a.txt", "a (1).txt", "a (2).txt"):
        (target / name).write_text("occupied")
    src = tmp_path / "a.txt"
    src.write_text("fresh")

    dest = organizer.move_file(src, target)

    assert dest.name == "a (3).txt"


# ---------------------------------------------------------------------------
# delete / misc helpers
# ---------------------------------------------------------------------------

def test_delete_file_removes_when_present(tmp_path, organizer):
    f = tmp_path / "junk.tmp"
    f.write_text("x")

    organizer.delete_file(f)

    assert not f.exists()


def test_delete_file_missing_is_noop(tmp_path, organizer):
    missing = tmp_path / "nope.tmp"
    organizer.delete_file(missing)   # must not raise
    assert not missing.exists()


def test_move_to_misc_uses_relative_misc_folder(tmp_path, organizer):
    src = tmp_path / "orphan.xyz"
    src.write_text("data")

    dest = organizer.move_to_misc(src)

    assert dest == tmp_path / "Misc" / "orphan.xyz"
    assert dest.exists() and not src.exists()


# ---------------------------------------------------------------------------
# move_file journaling (ADR-013: record before executing)
# ---------------------------------------------------------------------------

def test_move_records_journal_before_executing(tmp_path, organizer):
    src = tmp_path / "a.txt"
    src.write_text("data")
    target = tmp_path / "Documents"
    target.mkdir()

    dest = organizer.move_file(src, target)

    entry = db_service.journal_query(status="committed")[0]
    assert entry["op_type"] == "rename"
    assert entry["source_path"] == str(src)
    assert entry["dest_path"] == str(dest)
    assert entry["reversible"] == 1
    assert entry["size"] == 4


def test_move_missing_source_returns_none_without_journal(tmp_path, organizer):
    missing = tmp_path / "ghost.txt"
    target = tmp_path / "Documents"
    target.mkdir()

    dest = organizer.move_file(missing, target)

    assert dest is None
    assert db_service.journal_query() == []


# ---------------------------------------------------------------------------
# observer _process_file flow (gate auto vs ask/hold)
# ---------------------------------------------------------------------------

def test_process_file_auto_moves_high_confidence(tmp_path, mocker):
    config_service.config["watch_directory"] = str(tmp_path)
    watch = tmp_path
    f = watch / "invoice.pdf"
    f.write_text("sample pdf content")
    mocker.patch(
        "src.core.classifier.classifier.classify_with_confidence",
        return_value=Classification("Documents", 0.95, None, {}),
    )

    DownloadHandler()._process_file(f)

    assert _wait_for(lambda: (watch / "Documents").exists())
    assert (watch / "Documents" / "invoice.pdf").exists()
    # indexed at destination
    hits = db_service.query_files({"filename": "invoice.pdf"})
    assert any(h["path"] == str(watch / "Documents" / "invoice.pdf") for h in hits)


def test_process_file_ask_hold_keeps_file_in_place(tmp_path, mocker):
    config_service.config["watch_directory"] = str(tmp_path)
    config_service.config["confidence_thresholds"] = {
        "auto": 0.95, "ask": 0.7, "hold": 0.5,
    }
    watch = tmp_path
    f = watch / "invoice.pdf"
    f.write_text("sample pdf content")
    mocker.patch(
        "src.core.classifier.classifier.classify_with_confidence",
        return_value=Classification("Documents", 0.45, None, {}),
    )

    handler = DownloadHandler()
    handler._process_file(f)

    # synthetic wait: processing is synchronous; assert immediate state
    assert f.exists()                       # not auto-moved
    assert not (watch / "Documents").exists()
    hits = db_service.query_files({"filename": "invoice.pdf"})
    assert any(h["path"] == str(f) for h in hits)   # indexed in place


def test_process_file_scoped_rules_move_to_redirect(tmp_path, mocker):
    config_service.config["watch_directory"] = str(tmp_path)
    watch = tmp_path
    f = watch / "report.pdf"
    f.write_text("pdf body")
    mocker.patch(
        "src.core.classifier.classifier.classify_with_confidence",
        return_value=Classification("Documents", 0.95, None, {}),
    )

    scoped = [
        {"name": "pdfs-to-papers", "when": {"extensions": [".pdf"]},
         "then": {"target_category": "Papers"}}
    ]
    DownloadHandler(rules=scoped)._process_file(f)

    assert _wait_for(lambda: (watch / "Papers" / "report.pdf").exists())


def test_process_file_skips_temp_suffix(tmp_path, mocker):
    config_service.config["watch_directory"] = str(tmp_path)
    mocker.patch("src.services.observer.time.sleep")   # fast retries
    watch = tmp_path
    f = watch / "big-file.download"
    f.write_text("partial data")

    DownloadHandler()._process_file(f)

    # temp suffix never becomes ready -> skipped, nothing moved, not indexed
    assert f.exists()
    assert not (watch / "Documents").exists()
    assert db_service.query_files({"filename": "big-file.download"}) == []