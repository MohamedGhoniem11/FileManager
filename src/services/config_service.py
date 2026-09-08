import json
"""
Configuration Service
---------------------
Singleton service managing application settings, persistence, and hot-reloading.

H4 (roadmap 2.3): canonical config home resolves via platformdirs (ADR-014),
with a one-time migration of the legacy CWD-relative config/config.json.
F9 (roadmap 2.4): config file carries a schema_version; a MIGRATIONS map
upgrades older files in place. Newer-than-supported versions are loaded
without downgrade.
"""
import shutil
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

import platformdirs

from .logger import logger

SCHEMA_VERSION = 1

DEFAULT_CONFIG = {
    "schema_version": SCHEMA_VERSION,
    "watch_directory": str(Path.home() / "Downloads"),
    "monitor_enabled": True,
    "categories": {
        "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"],
        "PDFs": [".pdf"],
        "Documents": [".docx", ".txt", ".md", ".pptx", ".odt"],
        "Setups": [".exe", ".msi", ".dmg", ".pkg"],
        "Sheets": [".xlsx", ".xls", ".ods", ".csv"],
        "Videos": [".mp4", ".mkv", ".avi", ".mov"],
        "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
        "Audio": [".mp3", ".wav", ".flac", ".aac"]
    },
    "collision_strategy": "rename",
    "cleanup": {
        "dry_run": True,
        "remove_empty_folders": True,
        "remove_zero_byte_files": True,
        "handle_orphans": "move_to_misc",  # options: delete, move_to_misc, ignore
        "deduplicate": True,
        "backup_enabled": False,
        "backup_dir": str(Path.home() / "FileManager_Backups")
    },
    "automation": {
        "run_on_startup": False,
        "auto_scan_interval_min": 60,
        "enable_auto_scan": False
    },
    "gui_preferences": {
        "theme": "dark",
        "show_logs": True,
        "window_size": "1000x600"
    },
    "max_folder_files": 1000,
    "log_level": "INFO"
}

MIGRATIONS: Dict[int, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

class ConfigService:
    _instance = None
    _DEFAULT_CONFIG_PATH = Path(platformdirs.user_config_dir("FileManager")) / "config.json"
    _callbacks: List[Callable] = []
    SCHEMA_VERSION = SCHEMA_VERSION
    MIGRATIONS = MIGRATIONS

    def __new__(cls):
        if cls._instance is None:
            inst = super(ConfigService, cls).__new__(cls)
            inst._config_path = cls._DEFAULT_CONFIG_PATH
            inst._config: Optional[Dict[str, Any]] = None
            inst._last_mtime = 0.0
            cls._instance = inst
        return cls._instance

    # -- lazy config access ----------------------------------------------------

    @property
    def config(self) -> Dict[str, Any]:
        config = self._config
        if config is None:
            config = self._load_config()
            self._config = config
            self._last_mtime = self._get_mtime()
        return config

    @config.setter
    def config(self, value: Dict[str, Any]):
        self._config = value

    def _get_mtime(self) -> float:
        try:
            return self._config_path.stat().st_mtime
        except OSError:
            return 0.0

    # -- loading, migration, validation ------------------------------------------

    def _load_config(self) -> Dict[str, Any]:
        """Loads config from JSON file, validates it, and merges with defaults."""
        if not self._config_path.exists():
            self._migrate_legacy_config()
        if not self._config_path.exists():
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            config = DEFAULT_CONFIG.copy()
            self.save_config(config)
            return config

        try:
            with open(self._config_path, "r") as f:
                loaded = json.load(f)
                loaded = self._apply_schema_migrations(loaded)
                return self._validate_and_merge(loaded)
        except Exception as e:
            logger.error(f"Failed to load config: {e}. Using defaults.")
            return DEFAULT_CONFIG.copy()

    def _migrate_legacy_config(self):
        """Copies the pre-platformdirs relative config/config.json once (ADR-014)."""
        if self._config_path != self._DEFAULT_CONFIG_PATH:
            return
        legacy = Path("config/config.json")
        if legacy.exists():
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(legacy, self._config_path)
                logger.info(
                    f"Migrated legacy config {legacy} -> {self._config_path}"
                )
            except OSError as e:
                logger.error(f"Failed to migrate legacy config: {e}")

    def _apply_schema_migrations(self, loaded: Dict[str, Any]) -> Dict[str, Any]:
        current = loaded.get("schema_version", 0)
        if current > self.SCHEMA_VERSION:
            logger.warning(
                f"Config schema version {current} is newer than supported "
                f"version {self.SCHEMA_VERSION}. Loading without downgrade."
            )
            return loaded
        for version in range(current + 1, self.SCHEMA_VERSION + 1):
            migration = self.MIGRATIONS.get(version)
            if migration:
                loaded = migration(loaded)
        loaded["schema_version"] = self.SCHEMA_VERSION
        return loaded

    def _validate_and_merge(self, loaded: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures all required keys exist and types are correct."""
        merged = DEFAULT_CONFIG.copy()

        # Shallow merge for top-level keys
        for key, value in loaded.items():
            if key in DEFAULT_CONFIG:
                # Basic type validation
                if isinstance(value, type(DEFAULT_CONFIG[key])):
                    merged[key] = value

        # Deep merge for nested dicts (categories, gui_preferences)
        if "categories" in loaded and isinstance(loaded["categories"], dict):
            merged["categories"] = loaded["categories"]

        if "gui_preferences" in loaded and isinstance(loaded["gui_preferences"], dict):
            for k, v in loaded["gui_preferences"].items():
                if k in DEFAULT_CONFIG["gui_preferences"]:
                    merged["gui_preferences"][k] = v

        return merged

    def save_config(self, new_config: Dict[str, Any]):
        """Persists config to JSON file."""
        try:
            with open(self._config_path, "w") as f:
                json.dump(new_config, f, indent=4)
            self.config = new_config
            self._last_mtime = self._get_mtime()
            logger.info("Configuration saved and updated.")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def check_for_updates(self):
        """Checks if the config file was modified externally and reloads if so."""
        current_mtime = self._get_mtime()
        if current_mtime > self._last_mtime:
            logger.info("External config change detected. Reloading...")
            self.config = self._load_config()
            self._last_mtime = current_mtime
            self._trigger_callbacks()

    def register_callback(self, callback: Callable):
        """Registers a function to be called when config is reloaded."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def _trigger_callbacks(self):
        for cb in self._callbacks:
            try:
                cb(self.config)
            except Exception as e:
                logger.error(f"Error in config callback: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def get_categories(self) -> Dict[str, List[str]]:
        return self.config.get("categories", DEFAULT_CONFIG["categories"])

config_service = ConfigService()