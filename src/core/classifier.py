"""
Classification Engine — rules + content statistics (roadmap 4.2, ADR-011)
------------------------------------------------------------------------
Extension mapping remains the fast default (`classify`), but the engine now
also derives a typed, explainable classification WITH confidence:

- `classify_with_confidence(path)` -> Classification(category, confidence,
  subcategory, signals). Signals are the visible evidence behind the score —
  the "file council" story: extension prior, content keywords, priors memory.
- `record_correction(path, subcategory)` feeds the corrector loop
  (roadmap 5.2 groundwork): a user/in-agent correction updates priors so the
  next similar file classifies right.

Deterministic rules + statistics per ADR-011: fully unit-testable, offline,
honest about confidence. No spaCy, no LLM needed for the base path.
"""
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

from src.services.config_service import config_service
from src.services.logger import logger
from src.core.analyzer import extract_profile
from src.core.priors import priors_store

#: Content keywords that identify a "receipt" subcategory (vs other PDFs).
_RECEIPT_KEYWORDS = {
    "invoice", "receipt", "total", "tax", "paid", "amount", "order",
    "item", "subscription", "purchase", "thank you",
}

#: Multiple content signals that earn a strong content confidence bump.
_CONTENT_STRONG_KEYS = {"receipt", "invoice", "total"}


class Classification(NamedTuple):
    """Explainable classification output (category + confidence + evidence)."""
    category: str
    confidence: float
    subcategory: Optional[str] = None
    signals: Dict[str, Any] = {}


class Classifier:
    """Handles file categorization: fast extension path + content-confidence path."""

    def __init__(self):
        self.refresh_mappings()
        config_service.register_callback(self.refresh_on_config_change)

    def refresh_on_config_change(self, new_config: dict):
        logger.info("Classifier refreshing categories due to config change.")
        self.refresh_mappings()

    def refresh_mappings(self):
        """Reloads categories from the config service."""
        raw_categories = config_service.get_categories()
        # Flatten for faster lookup: {ext: category}
        self.extension_map: Dict[str, str] = {}
        for category, extensions in raw_categories.items():
            for ext in extensions:
                self.extension_map[ext.lower()] = category

    # -- fast extension path (backward-compatible) ---------------------------

    def classify(self, file_path: Path) -> str:
        """Returns the category for a given file path based on its extension."""
        extension = file_path.suffix.lower()
        return self.extension_map.get(extension, "Others")

    # -- confidence path (roadmap 4.2 / ADR-011) ------------------------------

    def classify_with_confidence(self, file_path: Path) -> Classification:
        """Content-aware classification with an explainable confidence score.

        Confidence = extension prior + content evidence + priors memory,
        clamped to [0, 1]. Unknown extensions start low and only content
        signals can lift them.
        """
        extension = file_path.suffix.lower()
        category = self.extension_map.get(extension, "Others")
        ext_prior = 0.60 if category != "Others" else 0.15

        profile = extract_profile(file_path)
        keywords = set(profile.keywords)
        text = (profile.text_sample or "").lower()

        # -- subcategory from content ---------------------------------------
        matched = {k for k in _RECEIPT_KEYWORDS if k in text or k in keywords}
        subcategory: Optional[str]
        if matched:
            subcategory = "receipt"
        elif profile.kind == "code":
            subcategory = "code"
        else:
            subcategory = None

        # -- confidence assembly ---------------------------------------------
        confidence = ext_prior

        # content bump: images are strong by themselves; receipts get a bump
        # only when the evidence is genuinely multiple/strong
        if profile.kind == "image":
            confidence += 0.25
        elif subcategory == "receipt" and (matched & _CONTENT_STRONG_KEYS):
            confidence += 0.20
        elif profile.has_content:
            confidence += 0.05

        # priors memory: corrections for this filename family raise confidence
        priors_evidence = priors_store.influence(file_path.stem)
        if priors_evidence:
            top_sub, total = priors_evidence.most_common(1)[0]
            if subcategory is None:
                subcategory = top_sub
            confidence += min(0.20, 0.05 * total)

        confidence = round(max(0.0, min(1.0, confidence)), 2)

        signals = {
            "extension": extension,
            "content_kind": profile.kind,
            "content_keywords": profile.keywords,
            "matched_keywords": sorted(matched),
            "ext_prior": round(ext_prior, 2),
            "priors": dict(priors_evidence),
        }
        return Classification(category, confidence, subcategory, signals)

    # -- corrector loop (roadmap 5.2 groundwork) ------------------------------

    def record_correction(self, file_path: Path, subcategory: str):
        """Feeds a human/Rules-Agent correction into the priors memory."""
        priors_store.record_path(file_path, subcategory)
        logger.info(
            f"Classifier learned: {file_path.name} -> {subcategory}"
        )


classifier = Classifier()