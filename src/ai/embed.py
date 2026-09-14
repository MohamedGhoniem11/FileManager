"""
Embedding Helpers — cosine similarity + Ollama embedding bridge
----------------------------------------------------------------
Pure-Python cosine similarity (no numpy) and prefixed-embedding helpers
for nomic-embed-text (search_query / search_document prefixes).

ADR ref: ADR-017 (local embeddings, pure-Python cosine)
"""
import math
from typing import List

from src.ai import llm_client
from src.services.config_service import config_service
from src.services.logger import logger


def cosine(a: List[float], b: List[float]) -> float:
    """Pure-Python cosine similarity. No numpy."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def get_embed_model() -> str:
    """Returns configured embedding model name."""
    ai_cfg = config_service.get("ai", {})
    if isinstance(ai_cfg, dict):
        return ai_cfg.get("embed_model", "nomic-embed-text")
    return "nomic-embed-text"


def embed_text(text: str) -> List[float]:
    """Embed a single text string. Returns vector."""
    model = get_embed_model()
    return llm_client.embed(model, text)


def embed_query(text: str) -> List[float]:
    """Embed a search query (nomic-embed-text uses 'search_query:' prefix)."""
    model = get_embed_model()
    prefixed = f"search_query: {text}"
    return llm_client.embed(model, prefixed)


def embed_document(text: str) -> List[float]:
    """Embed a document for indexing (nomic-embed-text uses 'search_document:' prefix)."""
    model = get_embed_model()
    prefixed = f"search_document: {text}"
    return llm_client.embed(model, prefixed)
