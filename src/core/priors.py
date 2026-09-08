"""
Priors Store — correction memory (roadmap 4.2 / 5.2 groundwork)
--------------------------------------------------------------
Persists the classifier's learning: when a user (or Rules Agent) corrects a
file to a subcategory, the filename tokens involved are recorded. Later
classifications of similar filenames inherit that memory, so a miss becomes a
lesson instead of a repeated mistake.

Storage: JSON under platformdirs user_data (hermetic in tests via conftest).
"""
import json
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Dict, List

import platformdirs

from src.services.logger import logger

_STOPWORDS = {
    "a", "an", "the", "of", "to", "for", "and", "or", "in", "on", "with",
    "this", "that", "is", "are", "was", "were", "it", "as", "at", "by",
}


class PriorsStore:
    """Thread-safe token -> {subcategory: count} memory backed by JSON."""

    def __init__(self):
        self._path = Path(platformdirs.user_data_dir("FileManager")) / "priors.json"
        self._data: Dict[str, Dict[str, int]] = {}
        self._lock = threading.RLock()
        self._load()

    # -- lifecycle ----------------------------------------------------------

    def reset_path(self, path: Path):
        """Points the store elsewhere (test isolation)."""
        with self._lock:
            self._path = path
            self.clear()

    def clear(self):
        with self._lock:
            self._data = {}
            self._persist()

    def _load(self):
        try:
            if self._path.exists():
                with open(self._path) as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self._data = {
                        str(k): {str(kk): int(vv) for kk, vv in v.items()}
                        for k, v in loaded.items() if isinstance(v, dict)
                    }
        except Exception as e:
            logger.error(f"Priors load failed ({self._path}): {e}. Starting empty.")

    def _persist(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w") as f:
                json.dump(self._data, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.error(f"Priors persist failed ({self._path}): {e}")

    # -- API ----------------------------------------------------------------

    @staticmethod
    def _tokenize(stem: str) -> List[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{1,}", stem.lower())
        return [w for w in words if w not in _STOPWORDS and len(w) > 1]

    def record(self, token: str, subcategory: str, count: int = 1):
        """Bumps the count for a single filename token -> subcategory."""
        if not token or not subcategory:
            return
        with self._lock:
            bucket = self._data.setdefault(token, {})
            bucket[subcategory] = bucket.get(subcategory, 0) + count
            self._persist()

    def record_path(self, file_path: Path, subcategory: str):
        """Records every token of a filename stem under `subcategory`."""
        tokens = self._tokenize(file_path.stem)
        with self._lock:
            for token in tokens:
                bucket = self._data.setdefault(token, {})
                bucket[subcategory] = bucket.get(subcategory, 0) + 1
            self._persist()
        logger.info(
            f"Priors: learned '{file_path.stem}' -> '{subcategory}' "
            f"(tokens: {tokens})"
        )

    def influence(self, stem: str) -> Counter:
        """Aggregated {subcategory: total} evidence for a filename's tokens."""
        with self._lock:
            agg: Counter = Counter()
            for token in self._tokenize(stem):
                for sub, count in self._data.get(token, {}).items():
                    agg[sub] += count
            return agg

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}


priors_store = PriorsStore()