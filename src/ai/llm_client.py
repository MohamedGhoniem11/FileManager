"""
LLM Client — Ollama HTTP wrapper (stdio-stdlib only)
------------------------------------------------------
Wraps the Ollama HTTP API using urllib — zero pip dependencies.
Targets qwen3:0.6b for chat and nomic-embed-text for embeddings.

ADR ref: ADR-017 (local LLM + agentic RAG, stdlib-only policy)
"""
import json
import time
import urllib.request
import urllib.error
from typing import Optional

from src.services.logger import logger

OLLAMA_BASE = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_S = 30
DEFAULT_EMBED_TIMEOUT_S = 10

# is_available cache
_last_ping = 0.0
_last_ping_result = False
_ping_cache_ttl = 60.0


def _request(
    path: str,
    data: Optional[dict],
    *,
    method: str = "POST",
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> dict:
    """Request to ollama, return parsed response.

    POST JSON by default (data required). For GET endpoints (e.g. /api/tags)
    pass data=None and method="GET" — no body, no Content-Type header.
    Raises ConnectionError if ollama unreachable.
    Raises TimeoutError on deadline.
    Raises ValueError on non-200 or invalid JSON.
    """
    url = f"{OLLAMA_BASE}{path}"
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise ConnectionError(f"Ollama unreachable: {e}") from e
    except TimeoutError:
        raise
    except Exception as e:
        raise ValueError(f"Ollama request failed: {e}") from e


def chat(
    model: str,
    prompt: str,
    *,
    think: bool = False,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """POST /api/generate with stream:false, format:"json".

    Passes 'think': false in the request body (q3:0.6b quirk — thinking
    consumes token budget on small models).
    Returns the 'response' field text.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "think": think,
        "options": {"num_predict": 256},
    }
    resp = _request("/api/generate", payload, timeout_s=timeout_s)
    return resp.get("response", "")


def embed(
    model: str,
    text: str,
    *,
    timeout_s: int = DEFAULT_EMBED_TIMEOUT_S,
) -> list[float]:
    """POST /api/embed. Returns the first embedding vector (list of floats).

    For nomic-embed-text: 768-dim.
    """
    payload = {"model": model, "input": text}
    resp = _request("/api/embed", payload, timeout_s=timeout_s)
    embeddings = resp.get("embeddings", [])
    if not embeddings:
        raise ValueError("Ollama returned no embeddings")
    return embeddings[0]


def embed_batch(
    model: str,
    texts: list[str],
    *,
    timeout_s: int = 30,
) -> list[list[float]]:
    """POST /api/embed with 'input' as a list. Returns list of vectors.

    Falls back to one-by-one if batch fails.
    """
    if not texts:
        return []
    payload = {"model": model, "input": texts}
    try:
        resp = _request("/api/embed", payload, timeout_s=timeout_s)
        embeddings = resp.get("embeddings", [])
        if len(embeddings) == len(texts):
            return [vec for vec in embeddings]
    except Exception as e:
        logger.warning(f"Batch embed failed, falling back to one-by-one: {e}")

    # Fallback: one by one
    results = []
    for text in texts:
        try:
            results.append(embed(model, text, timeout_s=timeout_s))
        except Exception:
            logger.warning(f"Single embed failed for text, using zero vector")
            results.append([0.0] * 768)
    return results


def is_available(timeout_s: int = 5) -> bool:
    """GET /api/tags. Returns True if ollama responds. Cache result for 60s."""
    global _last_ping, _last_ping_result
    now = time.time()
    if now - _last_ping < _ping_cache_ttl:
        return _last_ping_result
    try:
        _request("/api/tags", None, method="GET", timeout_s=timeout_s)
        _last_ping_result = True
    except Exception:
        _last_ping_result = False
    _last_ping = now
    return _last_ping_result
