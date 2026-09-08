"""Config Agent — branch-complete coverage (was 43%).

Every validate_and_propose path must return a truthful (valid, description,
patch) triple, and apply_patch must persist the exact proposed keys.
"""
from pathlib import Path

from src.core.config_agent import config_agent
from src.services.config_service import config_service


def test_no_action_rejected():
    valid, desc, patch = config_agent.validate_and_propose({})
    assert valid is False
    assert "No clear configuration action" in desc
    assert patch == {}


def test_update_mapping_requires_target():
    valid, desc, patch = config_agent.validate_and_propose(
        {"action": "update_mapping", "extensions": [".png"]}
    )
    assert valid is False
    assert "category or folder" in desc
    assert patch == {}


def test_update_mapping_merges_and_dedupes():
    config_service.config["categories"] = {"Screenshots": [".jpg"]}
    valid, desc, patch = config_agent.validate_and_propose(
        {"action": "update_mapping", "target": "Screenshots",
         "extensions": [".png", ".png", ".jpg"]}
    )
    assert valid is True
    assert sorted(patch["categories"]["Screenshots"]) == [".jpg", ".png"]


def test_update_mapping_creates_new_category():
    config_service.config["categories"] = {}
    valid, desc, patch = config_agent.validate_and_propose(
        {"action": "update_mapping", "target": "Archives",
         "extensions": [".zip"]}
    )
    assert valid is True
    assert patch["categories"]["Archives"] == [".zip"]


def test_toggle_monitor_defaults_to_enable():
    valid, desc, patch = config_agent.validate_and_propose(
        {"action": "toggle_monitor"}
    )
    assert valid is True
    assert patch == {"monitor_enabled": True}
    assert "Enable" in desc


def test_toggle_monitor_disable():
    valid, _, patch = config_agent.validate_and_propose(
        {"action": "toggle_monitor", "value": False}
    )
    assert valid is True
    assert patch == {"monitor_enabled": False}


def test_set_interval_valid_bounds():
    valid, desc, patch = config_agent.validate_and_propose(
        {"action": "set_interval", "value": 30}
    )
    assert valid is True
    assert patch["automation"]["auto_scan_interval_min"] == 30
    assert patch["automation"]["enable_auto_scan"] is True


def test_set_interval_too_large_rejected():
    valid, desc, patch = config_agent.validate_and_propose(
        {"action": "set_interval", "value": 99999}
    )
    assert valid is False
    assert "1440" in desc
    assert patch == {}


def test_set_interval_zero_rejected():
    valid, _, patch = config_agent.validate_and_propose(
        {"action": "set_interval", "value": 0}
    )
    assert valid is False
    assert patch == {}


def test_set_cleanup_dry_run_true_shows_safe_mode():
    config_service.config["cleanup"] = {"dry_run": False}
    valid, desc, patch = config_agent.validate_and_propose(
        {"action": "set_cleanup_mode", "value": True}
    )
    assert valid is True
    assert patch["cleanup"]["dry_run"] is True
    assert "DRY RUN" in desc


def test_set_cleanup_live_mode_flag():
    valid, desc, patch = config_agent.validate_and_propose(
        {"action": "set_cleanup_mode", "value": False}
    )
    assert valid is True
    assert patch["cleanup"]["dry_run"] is False
    assert "LIVE MODE" in desc


def test_unknown_action_rejected():
    valid, desc, patch = config_agent.validate_and_propose(
        {"action": "frobnicate"}
    )
    assert valid is False
    assert "Unknown configuration action" in desc
    assert patch == {}


def test_apply_patch_writes_only_patch_keys(tmp_path):
    config_service.config = {"monitor_enabled": True, "categories": {}}
    config_agent.apply_patch({"monitor_enabled": False})
    assert config_service.config["monitor_enabled"] is False
    # Unrelated keys survive
    assert config_service.config["categories"] == {}


def test_apply_patch_reloads_from_disk(tmp_path):
    config_service.config["monitor_enabled"] = True
    config_agent.apply_patch({"monitor_enabled": False})
    config_service._config = None  # force reload
    assert config_service.config["monitor_enabled"] is False