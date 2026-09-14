"""
RAG Indexer — background poller, SQLite vector store, cosine search
-------------------------------------------------------------------
Periodically embeds unembedded files into a local SQLite vector store.
Provides a vector-search interface backed by pure-Python cosine similarity.

ADR ref: ADR-017 (RAG index architecture, SQLite vector store)
"""
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import platformdirs

from src.ai.embed import cosine, embed_document, embed_query, get_embed_model
from src.services.config_service import config_service
from src.services.db_service import db_service
from src.services.logger import logger


class RagIndexer:
    """Background indexer: embeds files into SQLite, provides vector search."""

    def __init__(self):
        self._db_path = str(
            Path(platformdirs.user_data_dir("FileManager")) / "metadata.db"
        )
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        """Separate connection for embeddings table (avoids locking db_service)."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create embeddings table if not exists."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                path TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                vector TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

    def start(self) -> None:
        """Start background indexer thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="rag-indexer"
        )
        self._thread.start()
        logger.info("RAG indexer started.")

    def stop(self) -> None:
        """Signal the indexer to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("RAG indexer stopped.")

    def _run(self) -> None:
        """Background loop: find unembedded files, embed, sleep."""
        while not self._stop_event.is_set():
            try:
                count = self._index_pending()
                if count > 0:
                    logger.info(f"RAG indexer: embedded {count} files.")
            except Exception as e:
                logger.error(f"RAG indexer error: {e}")
            ai_cfg = config_service.get("ai", {})
            interval = ai_cfg.get("index_interval_s", 300) if isinstance(ai_cfg, dict) else 300
            self._stop_event.wait(timeout=interval)

    def _index_pending(self) -> int:
        """Find files in DB not in embeddings, embed them. Returns count."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT f.path, f.filename, f.category, f.size
                FROM files f
                LEFT JOIN embeddings e ON f.path = e.path
                WHERE e.path IS NULL
                LIMIT 16
            """).fetchall()

            if not rows:
                return 0

            model = get_embed_model()
            count = 0
            for row in rows:
                try:
                    file_path = row["path"]
                    text = f"{row['filename']} | {row['category'] or 'Unknown'}"
                    vector = embed_document(text)
                    with self._lock:
                        conn.execute("""
                            INSERT OR REPLACE INTO embeddings (path, model, vector, updated_at)
                            VALUES (?, ?, ?, ?)
                        """, (file_path, model, json.dumps(vector),
                              datetime.now().isoformat()))
                        conn.commit()
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to embed {row['path']}: {e}")
            return count
        finally:
            conn.close()

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Embed query → cosine against all vectors → return top_k results."""
        try:
            query_vec = embed_query(query)
        except Exception as e:
            logger.error(f"Embed query failed: {e}")
            return []

        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT path, vector FROM embeddings").fetchall()
            if not rows:
                return []

            scored = []
            for row in rows:
                try:
                    vec = json.loads(row["vector"])
                    score = cosine(query_vec, vec)
                    scored.append((row["path"], score))
                except Exception:
                    continue

            scored.sort(key=lambda x: x[1], reverse=True)
            top = scored[:top_k]

            results = []
            for path, score in top:
                file_info = self._get_file_info(path)
                if file_info:
                    file_info["score"] = round(score, 4)
                    results.append(file_info)
            return results
        finally:
            conn.close()

    def _get_file_info(self, path: str) -> Optional[Dict]:
        """Get filename, category from files table."""
        try:
            with db_service._lock:
                conn = db_service.get_connection()
                row = conn.execute(
                    "SELECT filename, category, size FROM files WHERE path = ?",
                    (path,),
                ).fetchone()
                if row:
                    return {
                        "path": path,
                        "filename": row["filename"],
                        "category": row["category"],
                        "size": row["size"],
                        "snippet": f"{row['filename']} ({row['category']})",
                    }
        except Exception:
            pass
        return {
            "path": path,
            "filename": Path(path).name,
            "category": "Unknown",
            "snippet": Path(path).name,
        }


# Module-level singleton
rag_indexer = RagIndexer()
