"""
Health Service
--------------
Orchestrates directory audits and automated cleanup operations.
Provides thread-safe access to the Health Engine and Organizer for GUI integration.
"""
import threading
import time
from pathlib import Path
from typing import Dict, List, Callable, Optional, NamedTuple
from src.services.logger import logger
from src.services.config_service import config_service
from src.core.health_engine import health_engine
from src.core.organizer import organizer
from src.services.db_service import db_service


class ProposedAction(NamedTuple):
    """One surfaced mutation from Health Audit 2.0 (roadmap 9.1/9.2).

    ``requires_confirmation`` gates every destructive or non-undoable step:
    the auto-cleanup only ever performs journaled, undoable moves; anything
    else is previewed and left for the user to confirm explicitly.
    """
    kind: str
    source: Path
    target: Optional[Path]
    reason: str
    undoable: bool
    requires_confirmation: bool


class HealthService:
    """Service layer for coordinating directory health checks and maintenance tasks."""

    def __init__(self):
        self.last_report = {}
        self.is_scanning = False

    def run_audit(self) -> Dict:
        """Runs a scan and returns the results without taking action."""
        self.is_scanning = True
        try:
            path_str = config_service.get("watch_directory")
            if not path_str:
                logger.error("Watch directory is not configured.")
                return {"error": "Watch directory not configured"}

            watch_dir = Path(path_str)
            logger.info(f"Starting health audit for {watch_dir}...")
            self.last_report = health_engine.scan_directory(watch_dir)
            logger.info(f"Audit complete. Formatted report generated.")
            return self.last_report
        finally:
            self.is_scanning = False

    def propose_actions(self, report: Dict) -> List[ProposedAction]:
        """Pure preview: every mutation cleanup would take, none executed.

        Step 9 (ADR-016 spirit): deletes are never auto-suggested as safe —
        duplicates/orphans propose journaled moves (undoable), zero-byte
        files move to a quarantine trash folder, and true deletions
        (orphan delete strategy, empty folder rmdir) require confirmation.
        """
        cleanup_cfg = config_service.get("cleanup", {})
        actions: List[ProposedAction] = []

        # 1. Duplicates: keep oldest (by mtime), move the rest to Misc
        if cleanup_cfg.get("deduplicate", True):
            for paths in report.get("duplicates", {}).values():
                if len(paths) < 2:
                    continue
                ordered = sorted(paths, key=lambda p: p.stat().st_mtime if p.exists() else 0)
                keeper = ordered[0]
                for dup in ordered[1:]:
                    actions.append(ProposedAction(
                        kind="deduplicate_move",
                        source=dup,
                        target=dup.parent / "Misc",
                        reason=f"duplicate of {keeper.name}",
                        undoable=True,
                        requires_confirmation=False,
                    ))

        # 2. Zero-byte: quarantine in watch/.Trash/FileManager-proposed
        if cleanup_cfg.get("remove_zero_byte_files", True):
            for path in report.get("zero_byte_files", []):
                watch = Path(config_service.get("watch_directory") or path.parent)
                actions.append(ProposedAction(
                    kind="zero_byte_quarantine",
                    source=path,
                    target=watch / ".Trash" / "FileManager-proposed" / path.name,
                    reason="zero-byte file quarantined, not deleted",
                    undoable=True,
                    requires_confirmation=False,
                ))

        # 3. Orphans: move_to_misc by default; real delete only on explicit strategy
        strategy = cleanup_cfg.get("handle_orphans", "ignore")
        if strategy != "ignore":
            for path in report.get("orphans", []):
                if strategy == "delete":
                    actions.append(ProposedAction(
                        kind="orphan_delete",
                        source=path,
                        target=None,
                        reason="orphan deletion (explicitly requested)",
                        undoable=False,
                        requires_confirmation=True,
                    ))
                elif strategy == "move_to_misc":
                    actions.append(ProposedAction(
                        kind="orphan_move",
                        source=path,
                        target=path.parent / "Misc",
                        reason="orphan moved to Misc",
                        undoable=True,
                        requires_confirmation=False,
                    ))

        # 4. Empty folders: rmdir is not journaled -> always confirm
        if cleanup_cfg.get("remove_empty_folders", True):
            folders = sorted(
                report.get("empty_folders", []),
                key=lambda x: len(x.parts),
                reverse=True,
            )
            for folder in folders:
                actions.append(ProposedAction(
                    kind="empty_folder_remove",
                    source=folder,
                    target=None,
                    reason="empty folder removal (not journaled)",
                    undoable=False,
                    requires_confirmation=True,
                ))

        return actions

    def execute_cleanup(self, report: Dict) -> Dict:
        """
        Applies the propose->confirm flow: only undoable, non-confirmation
        actions run automatically (journaled moves). Default is dry-run.
        """
        cleanup_cfg = config_service.get("cleanup", {})
        dry_run = cleanup_cfg.get("dry_run", True)
        actions = self.propose_actions(report)

        stat_summary = {
            "deleted": 0,
            "moved": 0,
            "saved_bytes": 0
        }

        if dry_run:
            logger.info("DRY-RUN MODE: No real changes will be made.")

        for action in actions:
            if action.requires_confirmation:
                logger.info(
                    f"[PREVIEW] {action.kind}: {action.source} requires confirmation; skipped."
                )
                continue
            if dry_run:
                logger.info(
                    f"[DRY-RUN] Would {action.kind}: {action.source} -> {action.target}"
                )
                continue
            if action.target is None:
                continue
            try:
                size = action.source.stat().st_size
            except OSError:
                size = 0
            final = organizer.move_file(action.source, action.target)
            if final:
                stat_summary["moved"] += 1
                stat_summary["saved_bytes"] += size

        return stat_summary

    def run_auto_maintenance(self):
        """Threaded function for scheduled maintenance."""
        while True:
            auto_cfg = config_service.get("automation", {})
            if auto_cfg.get("enable_auto_scan", False):
                interval = auto_cfg.get("auto_scan_interval_min", 60) * 60
                time.sleep(interval)
                logger.info("Scheduled maintenance starting...")
                report = self.run_audit()
                self.execute_cleanup(report)
            else:
                time.sleep(300) # Check config every 5 mins

    def scan_and_index(self, directory: Path) -> Dict[str, int]:
        """
        Manually scans a directory and adds all files to the DB index.
        Does NOT move or organize files.
        """
        logger.info(f"Manual scan started for: {directory}")
        if not directory.exists():
            return {"error": "Directory not found"}
            
        stats = {"indexed": 0, "errors": 0}
        
        try:
            # Recursive scan
            for item in directory.rglob("*"):
                if item.is_file():
                    try:
                        db_service.upsert_file(item)
                        stats["indexed"] += 1
                    except Exception as e:
                        stats["errors"] += 1
                        
            logger.info(f"Manual scan complete. Stats: {stats}")
            return stats
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return {"error": str(e)}

health_service = HealthService()
