"""Step 9 — Health Audit 2.0 proposals (roadmap 9.1/9.2).

propose_actions is a pure preview: everything cleanup would do, nothing
executed. Only journaled undoable moves auto-apply in execute_cleanup;
true deletions (orphan delete, empty folder rmdir) always require explicit
confirmation.
"""
from pathlib import Path

from src.services.health_service import health_service, ProposedAction
from src.services.config_service import config_service


def test_duplicates_propose_move_not_delete(tmp_path):
    config_service.config["cleanup"] = {"dry_run": True, "deduplicate": True}
    keeper = tmp_path / "keep.txt"
    dup = tmp_path / "dup.txt"
    keeper.write_text("same")
    dup.write_text("same")
    # Oldest by mtime is the keeper; backdate it deterministically
    old = 1000000000
    import os
    os.utime(keeper, (old, old))

    report = {"duplicates": {"h": [keeper, dup]}, "zero_byte_files": [],
              "orphans": [], "empty_folders": []}
    actions = health_service.propose_actions(report)

    assert len(actions) == 1
    action = actions[0]
    assert action.kind == "deduplicate_move"
    assert action.source == dup
    assert action.target == tmp_path / "Misc"
    assert action.undoable is True
    assert action.requires_confirmation is False


def test_zero_byte_proposes_quarantine_not_delete(tmp_path):
    config_service.config["cleanup"] = {"dry_run": True}
    config_service.config["watch_directory"] = str(tmp_path)
    zero = tmp_path / "empty.txt"
    zero.write_text("")

    report = {"duplicates": {}, "zero_byte_files": [zero],
              "orphans": [], "empty_folders": []}
    actions = health_service.propose_actions(report)

    assert len(actions) == 1
    action = actions[0]
    assert action.kind == "zero_byte_quarantine"
    assert action.target == tmp_path / ".Trash" / "FileManager-proposed" / "empty.txt"
    assert action.undoable is True


def test_orphan_delete_strategy_requires_confirmation(tmp_path):
    config_service.config["cleanup"] = {"dry_run": True, "handle_orphans": "delete"}
    orphan = tmp_path / "mystery.xyz"
    orphan.write_text("data")

    report = {"duplicates": {}, "zero_byte_files": [],
              "orphans": [orphan], "empty_folders": []}
    actions = health_service.propose_actions(report)

    assert len(actions) == 1
    action = actions[0]
    assert action.kind == "orphan_delete"
    assert action.undoable is False
    assert action.requires_confirmation is True
    assert action.target is None


def test_orphan_move_is_undoable_without_confirmation(tmp_path):
    config_service.config["cleanup"] = {"dry_run": True, "handle_orphans": "move_to_misc"}
    orphan = tmp_path / "mystery.xyz"
    orphan.write_text("data")

    report = {"duplicates": {}, "zero_byte_files": [],
              "orphans": [orphan], "empty_folders": []}
    actions = health_service.propose_actions(report)

    assert len(actions) == 1
    action = actions[0]
    assert action.kind == "orphan_move"
    assert action.target == tmp_path / "Misc"
    assert action.undoable is True
    assert action.requires_confirmation is False


def test_empty_folder_removal_requires_confirmation(tmp_path):
    config_service.config["cleanup"] = {"dry_run": True}
    empty = tmp_path / "emptydir"
    empty.mkdir()

    report = {"duplicates": {}, "zero_byte_files": [],
              "orphans": [], "empty_folders": [empty]}
    actions = health_service.propose_actions(report)

    assert len(actions) == 1
    action = actions[0]
    assert action.kind == "empty_folder_remove"
    assert action.undoable is False
    assert action.requires_confirmation is True


def test_execute_cleanup_dry_run_never_moves(tmp_path, mocker):
    config_service.config["cleanup"] = {"dry_run": True, "deduplicate": True}
    mock_move = mocker.patch("src.core.organizer.organizer.move_file")
    keeper = tmp_path / "keep.txt"
    dup = tmp_path / "dup.txt"
    keeper.write_text("same")
    dup.write_text("same")

    report = {"duplicates": {"h": [keeper, dup]}, "zero_byte_files": [],
              "orphans": [], "empty_folders": []}
    stats = health_service.execute_cleanup(report)

    mock_move.assert_not_called()
    assert stats == {"deleted": 0, "moved": 0, "saved_bytes": 0}


def test_execute_cleanup_applies_only_undoable_moves(tmp_path, mocker):
    config_service.config["cleanup"] = {"dry_run": False, "deduplicate": True}
    mock_move = mocker.patch("src.core.organizer.organizer.move_file",
                             side_effect=lambda src, dst: dst / src.name)
    keeper = tmp_path / "keep.txt"
    dup = tmp_path / "dup.txt"
    keeper.write_text("same")
    dup.write_text("same")
    import os
    old = 1000000000
    os.utime(keeper, (old, old))

    report = {"duplicates": {"h": [keeper, dup]}, "zero_byte_files": [],
              "orphans": [], "empty_folders": []}
    stats = health_service.execute_cleanup(report)

    mock_move.assert_called_once()
    assert stats["moved"] == 1
    assert stats["deleted"] == 0
    assert stats["saved_bytes"] == keeper.stat().st_size


def test_execute_cleanup_skips_confirmation_gated_deletes(tmp_path, mocker):
    config_service.config["cleanup"] = {"dry_run": False, "handle_orphans": "delete"}
    mock_move = mocker.patch("src.core.organizer.organizer.move_file")
    orphan = tmp_path / "mystery.xyz"
    orphan.write_text("data")

    report = {"duplicates": {}, "zero_byte_files": [],
              "orphans": [orphan], "empty_folders": []}
    stats = health_service.execute_cleanup(report)

    mock_move.assert_not_called()
    assert orphan.exists()  # nothing destructive happened without confirmation
    assert stats == {"deleted": 0, "moved": 0, "saved_bytes": 0}