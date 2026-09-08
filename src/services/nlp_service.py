"""
NLP Service — deterministic rule engine (roadmap 4.3, ADR-011)
-------------------------------------------------------------
Parses natural language queries to extract user intent and entities.

ADR-011 killed the spaCy theater: the old stack loaded a ~700MB model that
never influenced a single decision (audit M1/M2). This service is now a pure,
deterministic rule engine — same intents, zero heavyweight dependencies —
and the systems it feeds (ConfigAgent, search) are fully unit-testable.
"""
import re
from typing import Dict, Any, List, Optional
from src.services.logger import logger
from datetime import datetime, timedelta

class NlpService:
    """Deterministic rule-based interpretation of user requests (ADR-011)."""

    #: Kept for API compatibility; rules are the primary and only mode.
    is_fallback_mode = True
    nlp = None

    def parse(self, text: str) -> Dict[str, Any]:
        """Translates user text into a structured command."""
        text = text.lower().strip()

        # 1. Intent Detection - Specific commands first
        if any(w in text for w in ["scan", "index", "reindex"]):
            match = re.search(r'(?:scan|index|reindex)\s+(.+)', text)
            path = match.group(1).strip() if match else None
            return {"intent": "scan_path", "entities": {"path": path}}

        elif any(w in text for w in ["stats", "info", "overview", "debug", "status"]):
            return {"intent": "debug_info", "entities": {}}

        elif any(w in text for w in ["config", "make", "stop", "change", "set", "category", "folder", "enable", "disable"]):
            return self._handle_config(text)

        elif any(w in text for w in ["clean", "cleanup", "fix", "health", "audit"]):
            return {"intent": "run_cleanup", "entities": {}}

        # 2. General Search (Lowest priority)
        if any(w in text for w in ["find", "show", "search", "where is", "where are", "look for"]):
            return self._handle_search(text)

        # Fallback to general search if unsure
        return self._handle_search(text)

    def _handle_search(self, text: str) -> Dict[str, Any]:
        """Extracts search criteria."""
        entities = {}

        # Extension extraction (e.g. "pdfs", "images", "text files")
        ext_map = {
            "pdf": ".pdf", "pdfs": ".pdf",
            "image": "Images", "images": "Images",
            "video": "Videos", "videos": "Videos",
            "document": "Documents", "documents": "Documents",
            "music": "Audio", "audio": "Audio",
            "zip": ".zip", "zips": ".zip", "archive": ".zip"
        }
        for word, val in ext_map.items():
            if word in text:
                if val.startswith("."):
                    entities["extension"] = val
                else:
                    entities["category"] = val

        # Size extraction (e.g. "large", "> 5mb", "bigger than 10gb")
        if "large" in text or "big" in text:
            entities["min_size"] = 10 * 1024 * 1024 # 10MB

        # Improved regex to handle "larger than", "bigger than", etc.
        size_match = re.search(r'(?:larger|bigger|more than|above|>)\s*(?:than\s*)?(\d+)\s*(mb|gb|kb)', text)
        if size_match:
            val = int(size_match.group(1))
            unit = size_match.group(2).lower()
            mult = {"kb": 1024, "mb": 1024*1024, "gb": 1024*1024*1024}
            entities["min_size"] = val * mult[unit]

        # Date extraction (e.g. "today", "yesterday", "last week")
        now = datetime.now()
        if "today" in text:
            entities["date_after"] = now.replace(hour=0, minute=0, second=0).isoformat()
        elif "yesterday" in text:
            entities["date_after"] = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()
        elif "last week" in text:
            entities["date_after"] = (now - timedelta(days=7)).isoformat()

        # Filename extraction (everything else between quotes or common markers)
        name_match = re.search(r'"([^"]+)"', text)
        if name_match:
            entities["filename"] = name_match.group(1)

        if not entities:
            # If we didn't extract any meaningful search criteria, don't just return all files.
            # Convert "unknown" text to a filename search if it looks like a single word query?
            # Or just return unknown.
            # Let's try to interpret the whole text as a filename if it's short
            if len(text.split()) < 3:
                entities["filename"] = text
            else:
                 return {"intent": "unknown", "entities": {}}

        return {"intent": "search_files", "entities": entities}

    def _handle_config(self, text: str) -> Dict[str, Any]:
        """Extracts configuration change requests."""
        entities = {}

        # Category creation/modification
        if "category" in text or "folder" in text:
            # "make music go into Audio folder"
            # "create a category for screenshots"
            entities["action"] = "update_mapping"

            # Simple keyword extraction for now
            if "screenshot" in text:
                entities["target"] = "Screenshots"
                entities["extensions"] = [".png", ".jpg"]

        if "stop" in text:
            entities["action"] = "toggle_monitor"
            entities["value"] = False

        if "enable cleanup" in text or "real cleanup" in text:
            entities["action"] = "set_cleanup_mode"
            entities["value"] = False # dry_run = False

        if any(w in text for w in ["run", "every", "minutes"]):
            interval_match = re.search(r'(\d+)\s*minutes', text)
            if interval_match:
                entities["action"] = "set_interval"
                entities["value"] = int(interval_match.group(1))

        return {"intent": "update_config", "entities": entities}

# Lazy initialization to avoid recursive process issues on import
_nlp_service_instance = None

def get_nlp_service():
    global _nlp_service_instance
    if _nlp_service_instance is None:
        _nlp_service_instance = NlpService()
    return _nlp_service_instance