"""Step 7.1 — lifecycle age/size/category policies.

Policies declare when a file leaves the active folder for an archive.
``run_policies`` is the scheduled-run entry point; dry_run previews,
dry_run=False executes journaled moves.
"""
import os
import time
from pathlib import Path

from src.core.lifecycle import evaluate_policy, run_policies, PolicyAction
from src.services.config_service import config_service


def _aged_file(tmp_path, name="old-report.pdf", age_days=40, size=500):
    """Creates a .pdf (classifies to "PDFs") with a backdated mtime."""
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    old = time.time() - age_days * 86400
    os.utime(path, (old, old))
    return path


def test_age_policy_matches_old_file(tmp_path):
    policy = {
        "name": "archive-old",
        "when": {"age_days_gte": 30},
        "then": {"move_to": str(tmp_path / "Archive")},
    }
    file = _aged_file(tmp_path)
    action = evaluate_policy(file, policy)
    assert action is not None
    assert action.policy_name == "archive-old"
    assert action.target == tmp_path / "Archive"
    assert action.source == file


def test_age_policy_skips_fresh_file(tmp_path):
    policy = {
        "name": "archive-old",
        "when": {"age_days_gte": 30},
        "then": {"move_to": str(tmp_path / "Archive")},
    }
    fresh = tmp_path / "fresh.pdf"
    fresh.write_bytes(b"x" * 10)
    assert evaluate_policy(fresh, policy) is None


def test_size_policy_matches_large_file(tmp_path):
    policy = {
        "name": "big-only",
        "when": {"size_gte": 1000},
        "then": {"move_to": str(tmp_path / "Archive")},
    }
    big = _aged_file(tmp_path, name="big.pdf", size=2000)
    small = _aged_file(tmp_path, name="small.pdf", size=10)
    assert evaluate_policy(big, policy) is not None
    assert evaluate_policy(small, policy) is None


def test_category_policy_filters_by_classifier(tmp_path):
    policy = {
        "name": "pdfs-only",
        "when": {"category_is": "PDFs"},
        "then": {"move_to": str(tmp_path / "Archive")},
    }
    pdf = _aged_file(tmp_path, name="doc.pdf")
    txt = _aged_file(tmp_path, name="notes.txt")
    assert evaluate_policy(pdf, policy) is not None
    assert evaluate_policy(txt, policy) is None


def test_policy_without_move_to_yields_no_action(tmp_path):
    policy = {"name": "no-op", "when": {"age_days_gte": 30}, "then": {}}
    file = _aged_file(tmp_path)
    assert evaluate_policy(file, policy) is None


def test_policy_ignores_missing_file(tmp_path):
    policy = {
        "name": "archive-old",
        "when": {"age_days_gte": 30},
        "then": {"move_to": str(tmp_path / "Archive")},
    }
    ghost = tmp_path / "ghost.pdf"
    assert evaluate_policy(ghost, policy) is None


def test_run_policies_dry_run_previews_without_moving(tmp_path):
    policy = {
        "name": "archive-old",
        "when": {"age_days_gte": 30},
        "then": {"move_to": str(tmp_path / "Archive")},
    }
    file = _aged_file(tmp_path)
    actions = run_policies([file], [policy], dry_run=True)
    assert len(actions) == 1
    assert isinstance(actions[0], PolicyAction)
    assert file.exists()  # preview must not touch the file


def test_run_policies_executes_journaled_move(tmp_path, mocker):
    mock_move = mocker.patch(
        "src.core.organizer.organizer.move_file",
        return_value=tmp_path / "Archive" / "old-report.pdf",
    )
    policy = {
        "name": "archive-old",
        "when": {"age_days_gte": 30},
        "then": {"move_to": str(tmp_path / "Archive")},
    }
    file = _aged_file(tmp_path)
    actions = run_policies([file], [policy], dry_run=False)
    assert len(actions) == 1
    mock_move.assert_called_once_with(file, tmp_path / "Archive")
    assert actions[0].target == tmp_path / "Archive" / "old-report.pdf"


def test_run_policies_reads_config_when_policies_none(tmp_path):
    config_service.config["lifecycle_policies"] = [
        {
            "name": "archive-old",
            "when": {"age_days_gte": 30},
            "then": {"move_to": str(tmp_path / "Archive")},
        }
    ]
    file = _aged_file(tmp_path)
    actions = run_policies([file], policies=None, dry_run=True)
    assert len(actions) == 1
    assert actions[0].policy_name == "archive-old"


def test_run_policies_skips_failed_moves(tmp_path, mocker):
    """A failed move must not be reported as an executed action."""
    mock_move = mocker.patch(
        "src.core.organizer.organizer.move_file",
        return_value=None,
    )
    policy = {
        "name": "archive-old",
        "when": {"age_days_gte": 30},
        "then": {"move_to": str(tmp_path / "Archive")},
    }
    file = _aged_file(tmp_path)
    actions = run_policies([file], [policy], dry_run=False)
    assert actions == []
    mock_move.assert_called_once_with(file, tmp_path / "Archive")


def test_run_policies_refreshes_db_index_after_move(tmp_path, mocker):
    """A successful move must refresh the DB index with the final path."""
    target = tmp_path / "Archive" / "old-report.pdf"
    target.parent.mkdir()
    target.write_bytes(b"x" * 500)
    mock_move = mocker.patch(
        "src.core.organizer.organizer.move_file",
        return_value=target,
    )
    mock_upsert = mocker.patch("src.services.db_service.db_service.upsert_file")
    policy = {
        "name": "archive-old",
        "when": {"age_days_gte": 30},
        "then": {"move_to": str(tmp_path / "Archive")},
    }
    file = _aged_file(tmp_path)
    actions = run_policies([file], [policy], dry_run=False)
    assert len(actions) == 1
    mock_upsert.assert_called_once_with(target)


def test_run_policies_first_match_wins_per_file(tmp_path, mocker):
    """Policy order is priority: the first matching policy claims the file.

    Dry-run previews must show exactly what a real run would do — one
    action per file, no duplicates.
    """
    policy_a = {
        "name": "a",
        "when": {"age_days_gte": 30},
        "then": {"move_to": str(tmp_path / "A")},
    }
    policy_b = {
        "name": "b",
        "when": {"age_days_gte": 30},
        "then": {"move_to": str(tmp_path / "B")},
    }
    file = _aged_file(tmp_path)

    dry_actions = run_policies([file], [policy_a, policy_b], dry_run=True)
    assert [a.policy_name for a in dry_actions] == ["a"]

    mock_move = mocker.patch(
        "src.core.organizer.organizer.move_file",
        return_value=tmp_path / "A" / "old-report.pdf",
    )
    real_actions = run_policies([file], [policy_a, policy_b], dry_run=False)
    assert [a.policy_name for a in real_actions] == ["a"]
    mock_move.assert_called_once()  # the file is never double-moved