"""
H1 / H2 / H4 regression tests — data integrity groundwork (roadmap Step 2).

- H1: db_service must not swallow failures silently (was `except Exception: pass`).
- H2: SQLite must run in WAL mode with a single shared connection (was connect-per-call).
- H4: config/log/DB homes must resolve via platformdirs, not CWD (was relative paths).
"""
import logging
import threading
from pathlib import Path

import platformdirs
import pytest

from src.services import logger as logger_mod
from src.services.config_service import ConfigService
from src.services.db_service import DbService


# ---------------------------------------------------------------------------
# H2 — WAL mode + single-connection discipline
# ---------------------------------------------------------------------------

def test_db_uses_wal_mode(tmp_path):
    db = DbService(str(tmp_path / "test.db"))
    conn = db.get_connection()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_db_uses_single_persistent_connection(tmp_path):
    db = DbService(str(tmp_path / "test.db"))
    first = db.get_connection()
    second = db.get_connection()
    assert first is second  # one connection for the whole service, not connect-per-call


def test_concurrent_upserts_no_locked_errors(tmp_path):
    db = DbService(str(tmp_path / "test.db"))
    n = 20
    files = []
    for i in range(n):
        p = tmp_path / f"file_{i}.txt"
        p.write_text("x")
        files.append(p)

    errors = []

    def upsert(p):
        try:
            db.upsert_file(p)
        except Exception as exc:  # noqa: BLE001 - collect anything that escapes
            errors.append(exc)

    threads = [threading.Thread(target=upsert, args=(p,)) for p in files]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert db.get_stats()["total_files"] == n


# ---------------------------------------------------------------------------
# H1 — no silent failures
# ---------------------------------------------------------------------------

def test_upsert_failure_is_logged_not_silent(tmp_path, caplog, mocker):
    """H1: a failing upsert must leave a trace (was swallowed by `except: pass`)."""
    db = DbService(str(tmp_path / "test.db"))
    mocker.patch("src.core.classifier.classifier.classify", side_effect=RuntimeError("boom"))
    target = tmp_path / "a.pdf"
    target.write_text("x")

    with caplog.at_level(logging.ERROR):
        result = db.upsert_file(target)

    assert result is False
    assert any("boom" in rec.getMessage() for rec in caplog.records)


# ---------------------------------------------------------------------------
# H4 — absolute platformdirs homes (ADR-014)
# ---------------------------------------------------------------------------

def test_db_default_home_is_platformdirs():
    assert str(DbService().db_path) == str(
        Path(platformdirs.user_data_dir("FileManager")) / "metadata.db"
    )


def test_config_default_home_is_platformdirs():
    assert str(ConfigService._DEFAULT_CONFIG_PATH) == str(
        Path(platformdirs.user_config_dir("FileManager")) / "config.json"
    )


def test_log_default_home_is_platformdirs():
    path = logger_mod.default_log_path("app.log")
    assert str(path).startswith(platformdirs.user_log_dir("FileManager"))
    assert path.name == "app.log"