"""Step 7.2 — multi-location monitoring with per-location rules.

One ObserverService now owns several watch locations; each location gets
its own DownloadHandler scoped to that location's rule set. Legacy
``watch_directory`` still seeds the list when ``watch_locations`` is empty.
"""
from pathlib import Path

from src.services.observer import observer_service, DownloadHandler
from src.services.config_service import config_service
from src.core.classifier import Classification
from src.core.rules_agent import RulesAgent, rules_agent


def test_watch_directory_seeds_locations(tmp_path):
    """Legacy single-path key is the fallback location list."""
    config_service.config["watch_locations"] = []
    config_service.config["watch_directory"] = str(tmp_path)
    assert observer_service._resolve_locations() == [{"path": str(tmp_path)}]


def test_watch_locations_override_legacy_key(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    config_service.config["watch_locations"] = [
        {"path": str(a)},
        {"path": str(b), "rules": []},
    ]
    config_service.config["watch_directory"] = str(tmp_path / "legacy")
    locations = observer_service._resolve_locations()
    assert [loc["path"] for loc in locations] == [str(a), str(b)]


def test_observer_schedules_one_handler_per_location(tmp_path, mocker):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    config_service.config["watch_locations"] = [
        {"path": str(a)},
        {"path": str(b)},
    ]
    mocker.patch("watchdog.observers.Observer.start")
    mocker.patch("watchdog.observers.Observer.stop")
    mocker.patch("watchdog.observers.Observer.join")
    mocker.patch.object(observer_service, "sync_existing_files")
    mock_schedule = mocker.patch("watchdog.observers.Observer.schedule")

    observer_service.start()
    assert observer_service.is_running is True
    assert mock_schedule.call_count == 2
    scheduled_paths = [call.args[1] for call in mock_schedule.call_args_list]
    assert scheduled_paths == [str(a), str(b)]

    observer_service.stop()
    assert observer_service.is_running is False


def test_start_skips_missing_locations(tmp_path, mocker):
    real, ghost = tmp_path / "real", tmp_path / "ghost"
    real.mkdir()
    config_service.config["watch_locations"] = [
        {"path": str(real)},
        {"path": str(ghost)},
    ]
    mocker.patch("watchdog.observers.Observer.start")
    mocker.patch("watchdog.observers.Observer.stop")
    mocker.patch("watchdog.observers.Observer.join")
    mocker.patch.object(observer_service, "sync_existing_files")
    mock_schedule = mocker.patch("watchdog.observers.Observer.schedule")

    observer_service.start()
    assert mock_schedule.call_count == 1
    assert mock_schedule.call_args.args[1] == str(real)

    observer_service.stop()


def test_handler_uses_scoped_rules_not_global(tmp_path):
    rule_a = [
        {"name": "ra", "when": {"extensions": [".txt"]}, "then": {"move_to": "/tmp/x"}}
    ]
    handler = DownloadHandler(rules=rule_a)
    assert isinstance(handler.rules, RulesAgent)
    assert handler.rules is not rules_agent
    assert handler.rules._static_rules == rule_a
    # Default handler still binds the hot-reloadable global rules agent.
    assert DownloadHandler().rules is rules_agent


def test_scoped_rule_redirects_move_target(tmp_path, mocker):
    mock_move = mocker.patch("src.core.organizer.organizer.move_file")
    mocker.patch(
        "src.core.classifier.classifier.classify_with_confidence",
        return_value=Classification("Documents", 0.95, None, {}),
    )
    rules = [
        {
            "name": "work-files",
            "when": {"extensions": [".txt"]},
            "then": {"move_to": str(tmp_path / "Work")},
        }
    ]
    handler = DownloadHandler(rules=rules)
    file = tmp_path / "report.txt"
    file.write_text("content")

    handler._process_file(file)

    mock_move.assert_called_once()
    args, _ = mock_move.call_args
    assert args[1] == tmp_path / "Work"


def test_sync_existing_files_covers_all_locations(tmp_path, mocker):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "one.txt").write_text("1")
    (b / "two.pdf").write_text("2")
    config_service.config["watch_locations"] = [
        {"path": str(a), "rules": []},
        {"path": str(b), "rules": []},
    ]
    mock_process = mocker.patch(
        "src.services.observer.DownloadHandler._process_file"
    )

    observer_service.sync_existing_files()

    assert mock_process.call_count == 2
    processed = {call.args[0].parent for call in mock_process.call_args_list}
    assert processed == {a, b}