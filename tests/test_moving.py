"""
Step 7 wrap-up — moving mechanics under test (roadmap 7.x + observer flow).

Covered here:
- collision strategies: skip, overwrite, rename (unique-path numbering)
- move_to_misc / delete_file helpers
- move_file journaling  (every mutation recorded before executing)
- full observer _process_file flow: gate auto-move, gate ask/hold, rules scoping
Matches hermetic style of tests/test_services.py: all watch dirs under tmp_path.
"""
import os
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
# move_file edge cases (deep pass: failures, unicode, symlinks, EXDEV)
# ---------------------------------------------------------------------------

def test_move_permission_error_reverses_journal(tmp_path, mocker, organizer):
    mocker.patch("shutil.move", side_effect=PermissionError(13, "denied"))
    src = tmp_path / "locked.txt"
    src.write_text("data")
    target = tmp_path / "Documents"
    target.mkdir()

    dest = organizer.move_file(src, target)

    assert dest is None
    assert src.exists()                              # file untouched
    assert db_service.journal_query(status="reversed")
    assert db_service.journal_query(status="committed") == []


def test_move_oserror_exdev_reverses_journal(tmp_path, mocker, organizer):
    import errno
    mocker.patch("shutil.move", side_effect=OSError(errno.EXDEV, "cross-device"))
    src = tmp_path / "otherdev.txt"
    src.write_text("data")
    target = tmp_path / "Misc"
    target.mkdir()

    dest = organizer.move_file(src, target)

    assert dest is None
    assert src.exists()
    assert db_service.journal_query(status="reversed")


def test_move_unicode_filename_no_collision(tmp_path, organizer):
    src = tmp_path / "ملف جديد ١٢٣.txt"
    src.write_text("unicode")
    target = tmp_path / "Documents"
    target.mkdir()

    dest = organizer.move_file(src, target)

    assert dest == target / "ملف جديد ١٢٣.txt"
    assert dest.exists() and not src.exists()


def test_move_case_different_name_is_distinct_on_posix(tmp_path, organizer):
    # Probe real FS case-sensitivity (macOS APFS is case-insensitive by default).
    probe = tmp_path / "_case_probe.txt"
    probe.write_text("a")
    (tmp_path / "_CASE_PROBE.TXT").write_text("b")
    case_sensitive = probe.read_text() == "a"

    src = tmp_path / "Readme.txt"
    src.write_text("lower")
    target = tmp_path / "Docs"
    target.mkdir()
    (target / "README.txt").write_text("upper")

    dest = organizer.move_file(src, target)

    if not case_sensitive:
        assert dest == target / "Readme (1).txt"
    else:
        assert dest == target / "Readme.txt"  # case-sensitive: distinct


def test_move_symlink_source_moves_link_itself(tmp_path, organizer):
    real = tmp_path / "real.txt"
    real.write_text("content")
    link = tmp_path / "alias.txt"
    link.symlink_to(real)
    target = tmp_path / "Links"
    target.mkdir()

    dest = organizer.move_file(link, target)

    assert dest == target / "alias.txt"
    assert not link.exists()                         # link moved, target stays
    assert real.exists()
    assert dest.is_symlink()


def test_move_to_misc_creates_misc_dir_when_missing(tmp_path, organizer):
    src = tmp_path / "stray.bin"
    src.write_text("bytes")
    misc = tmp_path / "Misc"

    dest = organizer.move_to_misc(src)

    assert misc.is_dir()                             # dir auto-created
    assert dest == misc / "stray.bin" and dest.exists()


# ---------------------------------------------------------------------------
# undo_last guards (ADR-016: refuse to clobber or reverse foreign files)
# ---------------------------------------------------------------------------

def test_undo_skips_when_dest_vanished(tmp_path, organizer):
    src = tmp_path / "a.txt"
    src.write_text("data")
    target = tmp_path / "Documents"
    target.mkdir()
    dest = organizer.move_file(src, target)
    dest.unlink()                                    # file gone after move

    assert organizer.undo_last() == 0
    assert db_service.journal_query(status="committed")


def test_undo_skips_when_source_occupied(tmp_path, organizer):
    src = tmp_path / "a.txt"
    src.write_text("data")
    target = tmp_path / "Documents"
    target.mkdir()
    organizer.move_file(src, target)
    (tmp_path / "a.txt").write_text("intruder")      # new file at source spot

    assert organizer.undo_last() == 0
    assert (tmp_path / "a.txt").read_text() == "intruder"


def test_undo_skips_when_dest_inode_changed(tmp_path, organizer):
    src = tmp_path / "a.txt"
    src.write_text("data")
    target = tmp_path / "Documents"
    target.mkdir()
    dest = organizer.move_file(src, target)

    holder = tmp_path / "_holder.tmp"
    holder.write_text("replacement")
    dest.unlink()
    os.replace(holder, dest)  # rename preserves holder's distinct inode

    assert organizer.undo_last() == 0
    assert (target / "a.txt").read_text() == "replacement"


def test_undo_success_restores_and_marks_reversed(tmp_path, organizer):
    src = tmp_path / "report.txt"
    src.write_text("original")
    target = tmp_path / "Documents"
    target.mkdir()
    organizer.move_file(src, target)

    assert organizer.undo_last() == 1
    assert src.exists() and src.read_text() == "original"
    assert db_service.journal_query(status="reversed")


def test_undo_count_zero_and_negative_are_noops(tmp_path, organizer):
    src = tmp_path / "a.txt"
    src.write_text("data")
    target = tmp_path / "Documents"
    target.mkdir()
    organizer.move_file(src, target)

    assert organizer.undo_last(0) == 0
    assert organizer.undo_last(-3) == 0
    assert db_service.journal_query(status="committed")


def test_undo_reverse_only_real_moves(tmp_path, organizer):
    src = tmp_path / "b.txt"
    src.write_text("data")
    target = tmp_path / "Docs"
    target.mkdir()
    organizer.move_file(src, target)
    # inject a fake committed entry that looks reversible
    db_service.journal_record(
        op_type="rename",
        source_path=str(tmp_path / "never-existed.txt"),
        dest_path=str(tmp_path / "Docs" / "never-existed.txt"),
        inode=None, mtime=0.0, size=0, reversible=1,
    )

    assert organizer.undo_last() == 1               # only the real one reverses
    assert src.exists()

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