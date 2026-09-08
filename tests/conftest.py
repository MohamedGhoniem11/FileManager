import os
import tempfile
from pathlib import Path

# Redirect every platformdirs home to a pytest-owned temp root BEFORE any src
# import, so module-level singletons (db_service, config_service, logger) never
# touch real user dirs or the repo CWD (ADR-014 / H4 hermeticity).
_XDG_ROOT = Path(tempfile.mkdtemp(prefix="filemanager-pytest-"))
os.environ["XDG_CONFIG_HOME"] = str(_XDG_ROOT / "config")
os.environ["XDG_DATA_HOME"] = str(_XDG_ROOT / "data")
os.environ["XDG_STATE_HOME"] = str(_XDG_ROOT / "state")

import pytest

from src.services.config_service import config_service
from src.services.db_service import db_service


@pytest.fixture(autouse=True)
def isolated_app_state(tmp_path):
    """Every test gets a fresh db + config file; never touches real homes."""
    db_service.reset(str(tmp_path / "metadata.db"))
    config_service._config_path = tmp_path / "config.json"
    config_service._config = None
    config_service._last_mtime = 0.0
    yield
    db_service.reset()