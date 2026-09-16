import pytest
from pathlib import Path
from src.core.health_engine import HealthEngine
from src.services.health_service import HealthService
from src.services.config_service import config_service

def test_hashing_duplicates(tmp_path):
    engine = HealthEngine()
    
    # Create two identical files
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    content = "identical content"
    file1.write_text(content)
    file2.write_text(content)
    
    # Create a different file
    file3 = tmp_path / "file3.txt"
    file3.write_text("different content")
    
    report = engine.scan_directory(tmp_path)
    
    assert len(report["duplicates"]) == 1
    # Check that both duplicate paths are captured
    duplicate_paths = list(report["duplicates"].values())[0]
    assert file1 in duplicate_paths
    assert file2 in duplicate_paths
    assert file3 not in duplicate_paths

def test_empty_folders(tmp_path):
    engine = HealthEngine()
    
    empty_dir = tmp_path / "EmptyDir"
    empty_dir.mkdir()
    
    non_empty_dir = tmp_path / "FullDir"
    non_empty_dir.mkdir()
    (non_empty_dir / "file.txt").write_text("data")
    
    report = engine.scan_directory(tmp_path)
    
    assert empty_dir in report["empty_folders"]
    assert non_empty_dir not in report["empty_folders"]

def test_dry_run_safety(tmp_path, mocker):
    # Mock config to force dry_run ON
    mocker.patch("src.services.config_service.config_service.get", side_effect=lambda k, default=None: {"dry_run": True} if k == "cleanup" else default)
    
    # Mock deletion to verify it's NOT called
    mock_delete = mocker.patch("src.core.organizer.organizer.delete_file")
    
    service = HealthService()
    report = {
        "duplicates": {"hash1": [tmp_path / "keep", tmp_path / "delete"]},
        "zero_byte_files": [tmp_path / "empty"],
        "orphans": [],
        "empty_folders": []
    }
    
    service.execute_cleanup(report)
    
    # delete_file should NOT be called in dry-run
    mock_delete.assert_not_called()

def test_zero_byte_detection(tmp_path):
    engine = HealthEngine()
    
    zero_file = tmp_path / "zero.txt"
    zero_file.write_text("")
    
    real_file = tmp_path / "real.txt"
    real_file.write_text("content")
    
    report = engine.scan_directory(tmp_path)
    
    assert zero_file in report["zero_byte_files"]
    assert real_file not in report["zero_byte_files"]


def test_run_audit_success(tmp_path):
    service = HealthService()
    config_service.config["watch_directory"] = str(tmp_path)
    (tmp_path / "a.txt").write_text("data")

    report = service.run_audit()

    assert "duplicates" in report
    assert "zero_byte_files" in report
    assert service.last_report is report


def test_run_audit_missing_watch_dir():
    service = HealthService()
    config_service.config["watch_directory"] = None

    result = service.run_audit()

    assert result == {"error": "Watch directory not configured"}


def test_scan_and_index_success(tmp_path):
    service = HealthService()
    (tmp_path / "a.txt").write_text("data")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("more")

    stats = service.scan_and_index(tmp_path)

    assert stats == {"indexed": 2, "errors": 0}


def test_scan_and_index_missing_directory(tmp_path):
    service = HealthService()
    result = service.scan_and_index(tmp_path / "nope")
    assert result == {"error": "Directory not found"}


def test_scan_and_index_handles_unreadable_file(tmp_path, mocker):
    service = HealthService()
    (tmp_path / "a.txt").write_text("data")
    mocker.patch("src.services.db_service.db_service.upsert_file",
                 side_effect=OSError("permission"))

    stats = service.scan_and_index(tmp_path)

    assert stats == {"indexed": 0, "errors": 1}


def test_execute_cleanup_move_failure_counts_nothing(tmp_path, mocker):
    config_service.config["cleanup"] = {"dry_run": False, "deduplicate": True}
    mocker.patch("src.core.organizer.organizer.move_file", return_value=None)
    keeper = tmp_path / "keep.txt"
    dup = tmp_path / "dup.txt"
    keeper.write_text("same")
    dup.write_text("same")
    import os
    os.utime(keeper, (1000000000, 1000000000))

    report = {"duplicates": {"h": [keeper, dup]}, "zero_byte_files": [],
              "orphans": [], "empty_folders": []}
    stats = HealthService().execute_cleanup(report)

    assert stats == {"deleted": 0, "moved": 0, "saved_bytes": 0}


def test_execute_cleanup_stat_oserror_uses_zero(tmp_path, mocker):
    config_service.config["cleanup"] = {"dry_run": False, "deduplicate": True}
    mocker.patch("src.core.organizer.organizer.move_file",
                 side_effect=lambda src, dst: dst / src.name)
    keeper = tmp_path / "keep.txt"
    dup = tmp_path / "dup.txt"
    keeper.write_text("same")
    dup.write_text("same")
    import os
    os.utime(keeper, (1000000000, 1000000000))

    real_stat = Path.stat
    calls = {"dup": 0}
    def fake_stat(self, *args, **kwargs):
        # Count only explicit stat() calls (the sort key and the execute-phase
        # size read).  On Python 3.12 Path.exists() also calls self.stat but
        # passes follow_symlinks= as a keyword — so excluding kwarg calls keeps
        # the counter stable across Pythons and avoids tripping during sort.
        if self == dup and "follow_symlinks" not in kwargs:
            calls["dup"] += 1
            if calls["dup"] > 1:  # sort succeeded once; execute-phase call fails
                raise OSError("gone mid-move")
        return real_stat(self, *args, **kwargs)
    mocker.patch.object(Path, "stat", autospec=True, side_effect=fake_stat)

    report = {"duplicates": {"h": [keeper, dup]}, "zero_byte_files": [],
              "orphans": [], "empty_folders": []}
    stats = HealthService().execute_cleanup(report)

    assert stats["moved"] == 1
    assert stats["saved_bytes"] == 0  # stat failed → 0, no crash


def test_missing_duplicate_source_becomes_keeper(tmp_path, mocker):
    """Vanished duplicate (mtime fallback 0) is sorted as oldest → keeper."""
    config_service.config["cleanup"] = {"dry_run": False, "deduplicate": True}
    moved = []
    def fake_move(src, dst):
        moved.append((src, dst))
        return dst / src.name
    mocker.patch("src.core.organizer.organizer.move_file", side_effect=fake_move)
    keeper = tmp_path / "keep.txt"
    dup = tmp_path / "dup.txt"
    keeper.write_text("same")
    dup.write_text("same")
    dup.unlink()  # disappeared between scan and propose

    report = {"duplicates": {"h": [keeper, dup]}, "zero_byte_files": [],
              "orphans": [], "empty_folders": []}
    stats = HealthService().execute_cleanup(report)

    # Vanished file sorts first (mtime 0) → the real file is 'the duplicate'
    assert len(moved) == 1
    assert moved[0][0] == keeper
    assert stats["moved"] == 1
