import shutil
import time
"""
File System Organizer
---------------------
Responsible for the physical movement, renaming, and management of files.
Also handles collision resolution strategies and directory creation.

H3 (roadmap 3.1): journal-backed undo. Every move is journaled BEFORE it
executes (ADR-013); undo_last() reverse-replays the newest committed moves
(ADR-016).
"""
import os
from pathlib import Path
from typing import Dict, List, Optional
from src.utils.path_utils import sanitize_filename
from src.services.logger import logger
from src.services.config_service import config_service
from src.services.db_service import db_service

class Organizer:
    """Provides high-level file system operations with safety and collision management."""

    def move_file(self, source_path: Path, target_dir: Path) -> Optional[Path]:
        """
        Moves a file to the target directory.
        Handles collisions by renaming if configured.
        Every mutation is journaled BEFORE it executes (ADR-013).
        """
        if not source_path.exists():
            logger.warning(f"Source file {source_path} does not exist. Skipping.")
            return None

        entry_id = None
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            dest_path = target_dir / source_path.name
            reversible = 1

            # Collision handling
            if dest_path.exists():
                strategy = config_service.get("collision_strategy", "rename")

                if strategy == "skip":
                    logger.info(f"File {source_path.name} already exists in {target_dir}. Skipping.")
                    return None
                elif strategy == "overwrite":
                    logger.info(f"Overwriting {dest_path}")
                    reversible = 0
                else: # Default: rename
                    dest_path = self._get_unique_path(dest_path)

            # Journal the mutation before it executes (ADR-013 write-before-action)
            stats = source_path.stat()
            entry_id = db_service.journal_record(
                op_type="rename",
                source_path=str(source_path),
                dest_path=str(dest_path),
                inode=stats.st_ino,
                mtime=stats.st_mtime,
                size=stats.st_size,
                reversible=reversible,
            )

            # Move operation
            shutil.move(str(source_path), str(dest_path))
            db_service.journal_mark_committed(entry_id)
            logger.info(f"Moved: {source_path.name} -> {dest_path.parent.name}/{dest_path.name}")
            return dest_path

        except PermissionError:
            logger.error(f"Permission denied when moving {source_path.name}. File might be in use.")
        except Exception as e:
            logger.error(f"Error moving {source_path.name}: {e}")

        if entry_id is not None:
            db_service.journal_mark_reversed(entry_id)
        return None

    def undo_last(self, count: int = 1) -> int:
        """
        Reverse-replays the newest committed moves (ADR-016, roadmap 3.1).

        LIFO order: the most recent move is undone first. Only entries that
        are committed, reversible, op_type='rename', whose dest still exists,
        whose source is free, and whose inode matches the journal are reversed.
        Every successful undo marks the entry 'reversed'.
        Returns the number of moves successfully undone.
        """
        if count < 1:
            return 0

        candidates = [
            e for e in db_service.journal_query(status="committed")
            if e["reversible"] == 1 and e["op_type"] == "rename"
        ][-count:]  # newest committed reversible renames

        undone = 0
        for entry in reversed(candidates):
            if self._try_reverse(entry):
                db_service.journal_mark_reversed(entry["id"])
                undone += 1
        return undone

    def _try_reverse(self, entry: Dict) -> bool:
        """Tries to inverse one journaled move; safe only when all checks pass."""
        source = Path(entry["source_path"])
        dest = Path(entry["dest_path"])

        if not dest.exists():
            logger.warning(
                f"Undo skipped: dest {dest} no longer exists "
                f"(entry {entry['id']})."
            )
            return False
        if source.exists():
            logger.warning(
                f"Undo skipped: source {source} is occupied "
                f"(entry {entry['id']}). Refusing to clobber."
            )
            return False
        try:
            stats = dest.stat()
        except OSError as e:
            logger.error(f"Undo failed: cannot stat {dest}: {e}")
            return False
        if entry["inode"] is not None and stats.st_ino != entry["inode"]:
            logger.warning(
                f"Undo skipped: dest {dest} is a different file than journaled "
                f"(entry {entry['id']})."
            )
            return False

        try:
            shutil.move(str(dest), str(source))
            logger.info(
                f"Undo: restored {source.name} from "
                f"{dest.parent.name}/{dest.name}"
            )
            return True
        except Exception as e:
            logger.error(f"Undo failed to move {dest} -> {source}: {e}")
            return False

    def delete_file(self, file_path: Path):
        """Safely deletes a file if it exists."""
        try:
            if file_path.exists():
                os.remove(file_path)
                logger.info(f"Deleted: {file_path}")
        except Exception as e:
            logger.error(f"Failed to delete {file_path}: {e}")

    def move_to_misc(self, file_path: Path):
        """Moves a file to a 'Misc' relative folder."""
        misc_dir = file_path.parent / "Misc"
        return self.move_file(file_path, misc_dir)

    def backup_file(self, source_path: Path, backup_dir: Path):
        """Copies a file to a backup directory before destructive actions."""
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            dest = backup_dir / source_path.name
            shutil.copy2(source_path, dest)
            return dest
        except Exception as e:
            logger.error(f"Backup failed for {source_path}: {e}")
            return None

    def _get_unique_path(self, path: Path) -> Path:
        """Appends a counter to the filename to ensure uniqueness."""
        counter = 1
        name = path.stem
        suffix = path.suffix
        parent = path.parent
        
        while path.exists():
            path = parent / f"{name} ({counter}){suffix}"
            counter += 1
        return path

organizer = Organizer()
