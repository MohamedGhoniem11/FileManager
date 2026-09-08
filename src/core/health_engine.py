"""
Health Engine
-------------
Audit tool for scanning directories for structural and data redundancy issues.
Identifies empty folders, duplicate files, zero-byte files, and orphans.
"""
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Optional
from src.services.logger import logger
from src.services.config_service import config_service
from src.core.classifier import classifier
from src.core.fingerprint import fingerprint_file, hamming_distance
from src.services.db_service import db_service

#: Max hamming distance (of 64 bits) to consider two fingerprints "near-duplicate".
_NEAR_DUP_MAX_HAMMING = 6

class HealthEngine:
    """Core logic for performing deep-scans and directory auditing."""

    def __init__(self):
        self.reset_results()

    def reset_results(self):
        self.results = {
            "empty_folders": [],
            "duplicates": {}, # {hash: [paths]}
            "orphans": [],
            "zero_byte_files": [],
            "space_waste_bytes": 0,
            "fingerprint_clusters": []
        }

    def scan_directory(self, root_path: Path) -> Dict:
        """Performs a comprehensive scan of the given directory."""
        self.reset_results()
        if not root_path.exists():
            return self.results

        # Track file hashes for deduplication
        hashes: Dict[str, List[Path]] = {}
        fingerprint_entries: List[Tuple[Path, str, Any]] = []

        for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
            current_dir = Path(dirpath)
            
            # 1. Check for empty folders
            if not dirnames and not filenames:
                self.results["empty_folders"].append(current_dir)
                continue

            for f in filenames:
                file_path = current_dir / f
                
                try:
                    stats = file_path.stat()
                    
                    # 2. Zero-byte files
                    if stats.st_size == 0:
                        self.results["zero_byte_files"].append(file_path)
                    
                    # 3. Orphans (extensions not in config)
                    if classifier.classify(file_path) == "Others":
                        self.results["orphans"].append(file_path)

                    # 4. Duplicates (hashing)
                    if stats.st_size > 0:
                        f_hash = self._calculate_hash(file_path)
                        if f_hash:
                            if f_hash not in hashes:
                                hashes[f_hash] = []
                            hashes[f_hash].append(file_path)
                        fp = self._cached_fingerprint(file_path)
                        if fp is not None:
                            fingerprint_entries.append((file_path, *fp))

                except Exception as e:
                    logger.error(f"Error scanning file {file_path}: {e}")

        # Process duplicates
        for f_hash, paths in hashes.items():
            if len(paths) > 1:
                self.results["duplicates"][f_hash] = paths
                # Calculate wasted space (all but one copy)
                try:
                    single_size = paths[0].stat().st_size
                    self.results["space_waste_bytes"] += single_size * (len(paths) - 1)
                except:
                    pass

        self.results["fingerprint_clusters"] = self._cluster_fingerprints(fingerprint_entries)

        return self.results

    def _cached_fingerprint(self, path: Path) -> Optional[Tuple[str, str]]:
        """Fingerprint via the DB cache; falls back to computing + caching."""
        cached = db_service.get_cached_fingerprint(path)
        if cached is not None:
            return cached
        try:
            fp = fingerprint_file(path)
        except Exception:
            return None
        if fp["value"] is None:
            return None
        db_service.store_fingerprint(path, fp["kind"], fp["value"])
        return fp["kind"], fp["value"]

    def _cluster_fingerprints(self, entries: List[Tuple[Path, str, str]]) -> List[Dict]:
        """Groups near-duplicate fingerprints into 'N files ≈ M versions' clusters."""
        clusters: List[List[Tuple[Path, str, str]]] = []
        for path, kind, value in entries:
            placed = False
            for cluster in clusters:
                _, rep_kind, rep_value = cluster[0]
                if (
                    kind == rep_kind
                    and isinstance(value, int)
                    and isinstance(rep_value, int)
                    and hamming_distance(rep_value, value) <= _NEAR_DUP_MAX_HAMMING
                ):
                    cluster.append((path, kind, value))
                    placed = True
                    break
            if not placed:
                clusters.append([(path, kind, value)])

        reports: List[Dict] = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            versions = {v for _, _, v in cluster}
            reports.append({
                "kind": cluster[0][1],
                "files": [path for path, _, _ in cluster],
                "file_count": len(cluster),
                "versions": len(versions),
                "summary": f"{len(cluster)} files ≈ {len(versions)} real versions",
            })
        return reports

    def _calculate_hash(self, path: Path, chunk_size: int = 8192) -> Optional[str]:
        """Calculates SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Could not hash {path.name}: {e}")
            return None

health_engine = HealthEngine()
