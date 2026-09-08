import time
"""
Observer Service
----------------
Manages real-time filesystem monitoring using the watchdog library.
Coordinates initial synchronization and event-driven file organization.
"""
import os
import threading
from pathlib import Path
from typing import Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from src.services.logger import logger
from src.services.config_service import config_service
from src.core.classifier import classifier
from src.core.gate import decide as gate_decide
from src.core.rules_agent import rules_agent
from src.core.organizer import organizer
from src.services.db_service import db_service

class DownloadHandler(FileSystemEventHandler):
    """Event handler for processing new or moved files in the watched directory."""

    def on_created(self, event):
        if event.is_directory:
            return
        self._process_file(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        # Remove old path from index, add new path
        db_service.remove_file(Path(event.src_path))
        self._process_file(Path(event.dest_path))

    def on_deleted(self, event):
        if event.is_directory:
            return
        db_service.remove_file(Path(event.src_path))

    def _is_ready(self, file_path: Path, retries: int = 5, delay: float = 0.2) -> bool:
        """True when the file is completely written: permission-released and size-stable."""
        temp_suffixes = {".crdownload", ".part", ".partial", ".download", ".tmp", ".temp"}
        for _ in range(retries):
            if not file_path.exists():
                return False
            if file_path.suffix.lower() in temp_suffixes:
                time.sleep(delay)
                continue
            try:
                with file_path.open("rb"):
                    pass
                size_1 = file_path.stat().st_size
                time.sleep(delay)
                size_2 = file_path.stat().st_size
                if size_1 == size_2:
                    return True
            except (PermissionError, OSError):
                time.sleep(delay)
        return False

    def _process_file(self, file_path: Path):
        """Classifies, gates, and possibly moves a fully written file.

        Flow per Step 6 (trust): classify with confidence -> evaluate rules
        (dry-run) -> gate decides auto/ask/hold. Only "auto" moves; a
        below-threshold or risky file is indexed in place and left for the
        user to confirm (ask/hold), never auto-moved.
        """
        if not self._is_ready(file_path):
            logger.warning(f"File never became ready; skipping: {file_path}")
            return

        if not file_path.exists():
            return

        classification = classifier.classify_with_confidence(file_path)
        category = classification.category

        matches = rules_agent.evaluate(file_path)
        risk_flagged = any(m.risky for m in matches)
        caps = [m.cap_confidence for m in matches if m.cap_confidence is not None]
        effective = min([classification.confidence] + caps)

        decision = gate_decide(
            category, effective,
            config_service.get("confidence_thresholds") or None,
            risk_flagged=risk_flagged,
        )

        if decision.action != "auto":
            logger.info(
                f"Gate {decision.action} for {file_path.name}: {decision.reason}"
            )
            db_service.upsert_file(file_path)
            return

        # Rule redirect wins over the classifier's own category.
        target_dir = file_path.parent / category
        for m in matches:
            if m.move_to:
                target_dir = Path(m.move_to).expanduser()
                if not target_dir.is_absolute():
                    target_dir = file_path.parent / m.move_to
                break
            if m.target_category:
                target_dir = file_path.parent / m.target_category
                break

        if file_path.parent == target_dir:
            db_service.upsert_file(file_path)
            return

        final_path = organizer.move_file(file_path, target_dir)
        if final_path:
            db_service.upsert_file(final_path)

class ObserverService:
    """Manages the lifecycle of the watchdog Observer."""

    def __init__(self):
        self.observer = None
        self.is_running = False

    def start(self):
        enabled = config_service.get("monitor_enabled", True)
        if not enabled:
            logger.info("Monitoring is disabled in config. Not starting.")
            return

        watch_path = config_service.get("watch_directory")
        if not watch_path:
            logger.error("No watch directory configured.")
            return

        path = Path(watch_path)
        if not path.exists():
            logger.error(f"Watch directory {path} does not exist.")
            return

        logger.info(f"Starting observer on: {path}")
        
        event_handler = DownloadHandler()
        self.observer = Observer()
        self.observer.schedule(event_handler, str(path), recursive=False)
        self.observer.start()
        self.is_running = True
        
        # Proactively organize existing files
        threading.Thread(target=self.sync_existing_files, daemon=True).start()

    def sync_existing_files(self):
        """Iterates through existing files in the directory and organizes them."""
        watch_path = config_service.get("watch_directory")
        if not watch_path:
            return
            
        path = Path(watch_path)
        if not path.exists():
            return
            
        logger.info(f"Performing initial sync for: {path}")
        handler = DownloadHandler()
        
        for item in path.iterdir():
            if item.is_file():
                handler._process_file(item)
        
        logger.info("Initial sync complete.")

    def restart_if_needed(self, new_config: Dict[str, Any]):
        """Restarts the observer if monitoring was toggled or path changed."""
        logger.info("Re-evaluating observer status due to config change...")
        should_be_enabled = new_config.get("monitor_enabled", True)
        current_path = config_service.get("watch_directory")
        
        if self.is_running:
            self.stop()
        
        if should_be_enabled:
            # Small delay to ensure OS released old file handles
            time.sleep(0.5)
            self.start()

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.is_running = False
            logger.info("Observer stopped.")

observer_service = ObserverService()
