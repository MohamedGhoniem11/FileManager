"""
Database Service
----------------
Handles persistent indexing of file metadata using SQLite.
Supports complex queries for the NLP-based search engine.

H2 (roadmap 2.1): one shared connection, WAL mode, busy timeout.
H1 (roadmap 2.2): structured logging — failures are logged, never silent.
H3 (roadmap 2.5): append-only, versioned transaction journal (ADR-013).
H4 (roadmap 2.3): database home resolves via platformdirs (ADR-014).
"""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import platformdirs

from src.services.logger import logger

JOURNAL_SCHEMA_VERSION = 1

class DbService:
    """Manages the SQLite database for file metadata indexing."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(
            Path(platformdirs.user_data_dir("FileManager")) / "metadata.db"
        )
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    # -- connection lifecycle -------------------------------------------------

    def get_connection(self) -> sqlite3.Connection:
        """Returns the service's single persistent connection (H2)."""
        with self._lock:
            if self._conn is None:
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                self._create_schema(conn)
                conn.commit()
                self._migrate_schema(conn)
                self._conn = conn
            return self._conn

    def reset(self, db_path: Optional[str] = None):
        """Closes the connection and optionally points the service elsewhere."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            if db_path is not None:
                self.db_path = db_path

    def execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        """Runs a statement on the shared connection, committing after writes."""
        with self._lock:
            conn = self.get_connection()
            try:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur
            except Exception:
                conn.rollback()
                raise

    def _create_schema(self, conn: sqlite3.Connection):
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE,
                filename TEXT,
                extension TEXT,
                size INTEGER,
                category TEXT,
                created_at DATETIME,
                modified_at DATETIME,
                gate_status TEXT,
                gate_confidence REAL,
                gate_reason TEXT,
                gate_recorded_at DATETIME
            );
            CREATE INDEX IF NOT EXISTS idx_filename ON files(filename);
            CREATE INDEX IF NOT EXISTS idx_extension ON files(extension);
            CREATE INDEX IF NOT EXISTS idx_category ON files(category);

            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                op_type TEXT NOT NULL CHECK (op_type IN ('rename', 'copy_delete', 'trash')),
                source_path TEXT NOT NULL,
                dest_path TEXT NOT NULL,
                inode INTEGER,
                mtime REAL,
                size INTEGER,
                reversible INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'committed', 'reversed')),
                created_at TEXT NOT NULL,
                committed_at TEXT,
                reversed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS journal_schema_version (
                version INTEGER PRIMARY KEY,
                migrated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT OR IGNORE INTO journal_schema_version (version) VALUES ({schema_version});

            CREATE TRIGGER IF NOT EXISTS journal_no_delete
            BEFORE DELETE ON journal
            BEGIN
                SELECT RAISE(ABORT, 'journal is append-only: DELETE forbidden');
            END;

            CREATE TRIGGER IF NOT EXISTS journal_no_immutable_update
            BEFORE UPDATE OF op_type, source_path, dest_path, inode, mtime, size, reversible, created_at
            ON journal
            BEGIN
                SELECT RAISE(ABORT, 'journal is append-only: immutable fields cannot change');
            END;

            CREATE TABLE IF NOT EXISTS fingerprints (
                path TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fingerprints_kind ON fingerprints(kind);
            """.format(schema_version=JOURNAL_SCHEMA_VERSION)
        )

    def _migrate_schema(self, conn: sqlite3.Connection):
        """Adds columns introduced after the original schema shipped.

        ``CREATE TABLE IF NOT EXISTS`` never touches an existing table, so
        new columns land here as idempotent ALTERs. Each addition is guarded
        by a ``PRAGMA table_info`` check so re-running is a no-op.
        """
        with self._lock:
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(files)")}
            additions = {
                "gate_status": "TEXT",
                "gate_confidence": "REAL",
                "gate_reason": "TEXT",
                "gate_recorded_at": "DATETIME",
            }
            for column, decl in additions.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE files ADD COLUMN {column} {decl}")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_gate_status ON files(gate_status)"
            )
            conn.commit()

    # -- files index -----------------------------------------------------------

    def upsert_file(
        self,
        file_path: Path,
        category: Optional[str] = None,
        *,
        gate_status: Optional[str] = None,
        gate_confidence: Optional[float] = None,
        gate_reason: Optional[str] = None,
    ) -> bool:
        """Adds or updates a file's metadata in the index.

        ``category`` is normally re-derived from the classifier; pass it to
        avoid a redundant classification (the caller already knows it).
        ``gate_status``/``gate_confidence``/``gate_reason`` persist an
        ask/hold decision so the file appears in the Needs Review queue.
        Omitted gate fields (None) clear any previous gate state.
        """
        try:
            stats = file_path.stat()
            if category is None:
                from src.core.classifier import classifier
                category = classifier.classify(file_path)

            gate_recorded_at = datetime.now().isoformat() if gate_status else None

            with self._lock:
                conn = self.get_connection()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO files
                        (path, filename, extension, size, category, created_at,
                         modified_at, gate_status, gate_confidence, gate_reason,
                         gate_recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(file_path),
                        file_path.name,
                        file_path.suffix.lower(),
                        stats.st_size,
                        category,
                        datetime.fromtimestamp(stats.st_ctime).isoformat(),
                        datetime.fromtimestamp(stats.st_mtime).isoformat(),
                        gate_status,
                        gate_confidence,
                        gate_reason,
                        gate_recorded_at,
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to index {file_path}: {e}")
            return False

    def remove_file(self, file_path: Path):
        """Removes a file from the index."""
        try:
            with self._lock:
                conn = self.get_connection()
                conn.execute("DELETE FROM files WHERE path = ?", (str(file_path),))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to remove file from index: {e}")

    def query_files(self, filters: Dict[str, Any]) -> List[Dict]:
        """
        Executes a search query based on filtered criteria.
        Expects keys like: filename, extension, category, min_size, max_size, date_after.
        """
        query = "SELECT path, filename, category, size FROM files WHERE 1=1"
        params: List[Any] = []

        if "filename" in filters:
            query += " AND filename LIKE ?"
            params.append(f"%{filters['filename']}%")

        if "extension" in filters:
            query += " AND extension = ?"
            params.append(filters["extension"].lower())

        if "category" in filters:
            query += " AND category = ?"
            params.append(filters["category"])

        if "min_size" in filters:
            query += " AND size >= ?"
            params.append(filters["min_size"])

        if "max_size" in filters:
            query += " AND size <= ?"
            params.append(filters["max_size"])

        if "date_after" in filters:
            query += " AND created_at >= ?"
            params.append(filters["date_after"])

        try:
            with self._lock:
                conn = self.get_connection()
                rows = conn.execute(query, params).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Search query failed: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Returns statistics about the indexed files."""
        try:
            with self._lock:
                conn = self.get_connection()
                count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
                rows = conn.execute(
                    "SELECT category, COUNT(*) FROM files GROUP BY category"
                ).fetchall()
                categories = {row["category"]: row[1] for row in rows}
                return {
                    "total_files": count,
                    "categories": categories,
                    "db_path": self.db_path,
                }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}

    # -- needs-review queue (gate ask/hold) ------------------------------------

    def query_needs_review(self) -> List[Dict]:
        """Returns files currently gated ``ask`` or ``hold``, oldest first.

        These are the files the human-in-the-loop gate left in place for the
        user to review. Auto-moved files are never listed here; resolved
        files drop out the moment their gate state is cleared.
        """
        try:
            with self._lock:
                conn = self.get_connection()
                rows = conn.execute(
                    """
                    SELECT path, filename, category, size, gate_status,
                           gate_confidence, gate_reason, gate_recorded_at
                    FROM files
                    WHERE gate_status IN ('ask', 'hold')
                    ORDER BY gate_recorded_at ASC
                    """
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Needs-review query failed: {e}")
            return []

    def count_needs_review(self) -> int:
        """Number of files waiting in the review queue (ask + hold)."""
        try:
            with self._lock:
                conn = self.get_connection()
                row = conn.execute(
                    "SELECT COUNT(*) FROM files WHERE gate_status IN ('ask', 'hold')"
                ).fetchone()
                return row[0]
        except Exception as e:
            logger.error(f"Needs-review count failed: {e}")
            return 0

    def resolve_review(self, file_path: Path) -> bool:
        """Clears the gate state so a file leaves the review queue.

        Called after the user reviews a file (accepted/moved/ignored) or
        when the file disappears. Does not delete the indexed row — the
        file stays searchable, it just no longer demands attention.
        """
        try:
            with self._lock:
                conn = self.get_connection()
                conn.execute(
                    """
                    UPDATE files
                    SET gate_status = NULL, gate_confidence = NULL,
                        gate_reason = NULL, gate_recorded_at = NULL
                    WHERE path = ?
                    """,
                    (str(file_path),),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to resolve review for {file_path}: {e}")
            return False

    # -- transaction journal (ADR-013) -----------------------------------------

    def journal_record(
        self,
        op_type: str,
        source_path: str,
        dest_path: str,
        *,
        inode: Optional[int] = None,
        mtime: Optional[float] = None,
        size: Optional[int] = None,
        reversible: int = 1,
    ) -> int:
        """Appends a pending journal entry BEFORE a mutation executes."""
        with self._lock:
            conn = self.get_connection()
            cur = conn.execute(
                """
                INSERT INTO journal
                    (op_type, source_path, dest_path, inode, mtime, size,
                     reversible, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    op_type,
                    source_path,
                    dest_path,
                    inode,
                    mtime,
                    size,
                    reversible,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            return cur.lastrowid

    def journal_query(
        self, status: Optional[str] = None, op_type: Optional[str] = None
    ) -> List[Dict]:
        """Returns journal entries, optionally filtered by status/op_type."""
        query = "SELECT * FROM journal WHERE 1=1"
        params: List[Any] = []
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        if op_type is not None:
            query += " AND op_type = ?"
            params.append(op_type)
        query += " ORDER BY id"
        with self._lock:
            conn = self.get_connection()
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def journal_mark_committed(self, entry_id: int):
        with self._lock:
            conn = self.get_connection()
            conn.execute(
                "UPDATE journal SET status = 'committed', committed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), entry_id),
            )
            conn.commit()

    def journal_mark_reversed(self, entry_id: int):
        with self._lock:
            conn = self.get_connection()
            conn.execute(
                "UPDATE journal SET status = 'reversed', reversed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), entry_id),
            )
            conn.commit()

    def journal_count(self, status: Optional[str] = None) -> int:
        query = "SELECT COUNT(*) FROM journal"
        params: List[Any] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status)
        with self._lock:
            conn = self.get_connection()
            row = conn.execute(query, params).fetchone()
            return row[0]

    def journal_schema_version(self) -> int:
        with self._lock:
            conn = self.get_connection()
            row = conn.execute("SELECT MAX(version) FROM journal_schema_version").fetchone()
            return row[0]

    def journal_provenance(self, path: str) -> List[Dict]:
        """
        "Where did X go?" (roadmap 3.2 / ADR-016).

        Returns every journal entry that ever touched `path` as a source or
        a destination, oldest first. Empty list when the path is unknown.
        """
        with self._lock:
            conn = self.get_connection()
            rows = conn.execute(
                """
                SELECT * FROM journal
                WHERE source_path = ? OR dest_path = ?
                ORDER BY id
                """,
                (path, path),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- fingerprint cache (roadmap 5.1) --------------------------------------

    def get_cached_fingerprint(self, file_path: Path) -> Optional[Tuple[str, Any]]:
        """
        Returns a cached (kind, value) fingerprint ONLY when the file's size
        and mtime still match what was cached (recompute guard).
        """
        try:
            stats = file_path.stat()
            with self._lock:
                conn = self.get_connection()
                row = conn.execute(
                    """
                    SELECT kind, value FROM fingerprints
                    WHERE path = ? AND size = ? AND mtime = ?
                    """,
                    (str(file_path), stats.st_size, stats.st_mtime),
                ).fetchone()
            if row is None:
                return None
            kind, encoded = row["kind"], row["value"]
            if encoded.startswith("i:"):
                return kind, int(encoded[2:])
            if encoded.startswith("s:"):
                return kind, encoded[2:]
            return kind, encoded
        except Exception as e:
            logger.error(f"Fingerprint cache read failed for {file_path}: {e}")
            return None

    def store_fingerprint(self, file_path: Path, kind: str, value: Any) -> bool:
        """Caches a fingerprint for a path; ints are kept parseable as text."""
        try:
            stats = file_path.stat()
            encoded = f"i:{value}" if isinstance(value, int) else f"s:{value}"
            with self._lock:
                conn = self.get_connection()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fingerprints (path, kind, value, size, mtime)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(file_path), kind, encoded, stats.st_size, stats.st_mtime),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Fingerprint cache write failed for {file_path}: {e}")
            return False


db_service = DbService()