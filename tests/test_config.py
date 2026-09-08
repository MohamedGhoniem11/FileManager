import pytest
import json
from pathlib import Path
from src.services.config_service import ConfigService, config_service

@pytest.fixture
def mock_config(tmp_path, mocker):
    """Fixture to reset config_service and use a temp path."""
    cfg_file = tmp_path / "config.json"
    # Patch the instance variable
    mocker.patch.object(config_service, "_config_path", cfg_file)
    # Reset instance state to force reload
    config_service.config = {}
    return cfg_file

def test_config_default_fallback(mock_config):
    # Reload config to trigger fallback
    config_service.config = config_service._load_config()
    assert config_service.get("monitor_enabled") is True
    assert "Images" in config_service.get("categories")

def test_config_save_and_reload(mock_config):
    new_cfg = config_service.config.copy()
    new_cfg["monitor_enabled"] = False
    
    config_service.save_config(new_cfg)
    
    # Verify file content
    with open(mock_config, "r") as f:
        data = json.load(f)
        assert data["monitor_enabled"] is False

    # Verify internal state
    assert config_service.get("monitor_enabled") is False

def test_config_validation(mock_config):
    # Write invalid config (wrong type for monitor_enabled)
    with open(mock_config, "w") as f:
        json.dump({"monitor_enabled": "not_a_boolean"}, f)
        
    # Reload should trigger validation
    config_service.config = config_service._load_config()
    # Should fallback to default True
    assert config_service.get("monitor_enabled") is True


# ---------------------------------------------------------------------------
# 2.4/F9 — schema_version + migration path
# ---------------------------------------------------------------------------

def test_config_default_carries_schema_version(mock_config):
    cfg = config_service._load_config()
    assert cfg["schema_version"] == ConfigService.SCHEMA_VERSION


def test_legacy_config_without_schema_version_is_migrated(mock_config):
    with open(mock_config, "w") as f:
        json.dump({"monitor_enabled": False, "watch_directory": "/tmp/x"}, f)

    cfg = config_service._load_config()

    assert cfg["schema_version"] == ConfigService.SCHEMA_VERSION
    assert cfg["monitor_enabled"] is False
    assert cfg["watch_directory"] == "/tmp/x"


def test_old_schema_version_is_migrated_and_values_preserved(mock_config):
    with open(mock_config, "w") as f:
        json.dump({"schema_version": 0, "monitor_enabled": False}, f)

    cfg = config_service._load_config()

    assert cfg["schema_version"] == ConfigService.SCHEMA_VERSION
    assert cfg["monitor_enabled"] is False


def test_newer_schema_version_is_kept_not_downgraded(mock_config, caplog):
    with open(mock_config, "w") as f:
        json.dump({"schema_version": 999, "monitor_enabled": False}, f)

    with caplog.at_level("WARNING"):
        cfg = config_service._load_config()

    assert cfg["schema_version"] == 999
    assert cfg["monitor_enabled"] is False
    assert any("newer" in r.getMessage().lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# H4 part 2 — one-time legacy relative-config migration (ADR-014)
# ---------------------------------------------------------------------------

def test_legacy_relative_config_migrated_to_canonical_home(tmp_path, mocker, monkeypatch):
    legacy_dir = tmp_path / "config"
    legacy_dir.mkdir()
    legacy = legacy_dir / "config.json"
    legacy.write_text(json.dumps({"monitor_enabled": False}))
    monkeypatch.chdir(tmp_path)

    canonical = tmp_path / "canonical" / "config.json"
    mocker.patch.object(ConfigService, "_DEFAULT_CONFIG_PATH", canonical)
    mocker.patch.object(config_service, "_config_path", canonical)
    config_service._config = None

    cfg = config_service._load_config()

    assert canonical.exists()
    assert cfg["monitor_enabled"] is False
    assert config_service._config_path == canonical


def test_canonical_home_is_preferred_over_legacy_when_both_exist(tmp_path, mocker, monkeypatch):
    legacy_dir = tmp_path / "config"
    legacy_dir.mkdir()
    (legacy_dir / "config.json").write_text(json.dumps({"watch_directory": "/tmp/legacy"}))
    monkeypatch.chdir(tmp_path)

    canonical = tmp_path / "canonical" / "config.json"
    canonical.parent.mkdir()
    canonical.write_text(json.dumps({"watch_directory": "/tmp/canonical"}))
    mocker.patch.object(ConfigService, "_DEFAULT_CONFIG_PATH", canonical)
    mocker.patch.object(config_service, "_config_path", canonical)
    config_service._config = None

    cfg = config_service._load_config()

    assert cfg["watch_directory"] == "/tmp/canonical"
