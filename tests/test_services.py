import pytest
import time
from pathlib import Path
from src.services.observer import observer_service, DownloadHandler
from src.services.config_service import config_service

def test_observer_start_stop(mocker):
    # Mock observer to not actually start threads
    mocker.patch("watchdog.observers.Observer.start")
    mocker.patch("watchdog.observers.Observer.stop")
    mocker.patch("watchdog.observers.Observer.join")
    # Mock the background sync so the test never touches the real watch directory
    mocker.patch.object(observer_service, "sync_existing_files")
    
    observer_service.start()
    assert observer_service.is_running is True
    
    observer_service.stop()
    assert observer_service.is_running is False

def test_handler_process_file(tmp_path, mocker):
    # Mock organizer and classifier
    mock_move = mocker.patch("src.core.organizer.organizer.move_file")
    mocker.patch("src.core.classifier.classifier.classify", return_value="Documents")
    
    handler = DownloadHandler()
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    handler._process_file(test_file)
    
    # Verify move_file was called with correct target
    mock_move.assert_called_once()
    args, _ = mock_move.call_args
    assert args[0] == test_file
    assert args[1] == tmp_path / "Documents"

def test_handler_skips_temp_suffix_files(tmp_path, mocker):
    """C4: partial download files (.crdownload) must never be moved."""
    handler = DownloadHandler()
    partial_file = tmp_path / "movie.mkv.crdownload"
    partial_file.write_text("partial content")
    
    # Short retries so the test is fast; the temp suffix should block readiness
    assert handler._is_ready(partial_file, retries=1, delay=0.01) is False

def test_handler_waits_for_stable_size(tmp_path, mocker):
    """C4: a file whose size is still changing is not ready."""
    handler = DownloadHandler()
    growing_file = tmp_path / "growing.bin"
    growing_file.write_bytes(b"x" * 10)

    # Simulate an in-progress write: each pair of size samples differs (10, 100, 10, 100...)
    sizes = iter([10, 100, 10, 100])
    from types import SimpleNamespace
    mocker.patch("pathlib.Path.stat", side_effect=lambda: SimpleNamespace(st_size=next(sizes)))
    mocker.patch("src.services.observer.time.sleep")

    assert handler._is_ready(growing_file, retries=2, delay=0.01) is False

def test_observer_restart_on_config(mocker):
    mocker.patch("src.services.observer.ObserverService.start")
    mocker.patch("src.services.observer.ObserverService.stop")
    
    observer_service.is_running = True
    observer_service.restart_if_needed({"monitor_enabled": True})
    
    # Should call stop and then start
    observer_service.stop.assert_called()
    observer_service.start.assert_called()
