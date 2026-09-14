# 07 — AI Integration: Local LLM + Agentic RAG

> How a 0.6B local language model and embedding-based retrieval turn the Assistant from a deterministic parser into a grounded, context-aware co-pilot — with zero network calls and zero new pip dependencies.

## Why

ADR-011 killed spaCy theater and shipped a deterministic regex engine. It was honest, testable, and small — but it has a ceiling: no semantic understanding, no memory of indexed files, no way to answer "where are my tax documents from last quarter?" with anything better than keyword matching.

The user wants the Assistant to understand natural questions about their files and answer with grounded citations — all locally, all private, smallest possible footprint.

## Design Principles

| Principle | What it means in practice |
|---|---|
| **Zero network** | All inference runs via ollama on `127.0.0.1:11434`. No API keys, no telemetry, no cloud. Verified by grep: zero network imports in `src/`. |
| **Zero new pip deps** | ollama client uses stdlib `urllib.request`. Embeddings use pure-Python cosine over `math` and `json`. No numpy, no torch. |
| **LLM proposes, deterministic systems dispose** | LLM confidence never feeds the gate directly. LLM picks intent/tools; existing deterministic code (NLP service, ConfigAgent, gate) still owns the action. Any LLM failure falls back to the current regex engine. |
| **Off by default** | `ai.enabled` is `False` in the config schema. The app is inert until the user explicitly opts in. |
| **Smallest model wins** | qwen3:0.6b (~522MB) for routing + text generation. nomic-embed-text (~274MB) for embeddings. Total: ~800MB on disk. Models are config-configurable; swap in `all-minilm:l6-v2` (~23MB) if even smaller is desired. |

## Architecture

```
User types in Assistant
        │
        ▼
┌─────────────────────────────────────────────┐
│  chat.py  (_process_request)                │
│                                             │
│  if ai.enabled:                             │
│    agent.process(text)  ──────────┐         │
│  else:                            │         │
│    nlp_service.parse(text)        │         │
│                                   ▼         │
│                          ┌──────────────┐   │
│                          │  agent.py    │   │
│                          │  (tool loop) │   │
│                          └──────┬───────┘   │
│                                 │           │
│            ┌────────────────────┼────┐      │
│            ▼                    ▼    ▼      │
│    ┌──────────────┐   ┌────────┐ ┌──────┐  │
│    │ llm_client   │   │ embed  │ │ db   │  │
│    │ (ollama API) │   │ (.py)  │ │ svc  │  │
│    └──────────────┘   └────────┘ └──────┘  │
│            │                    │           │
│            ▼                    ▼           │
│    ┌──────────────┐   ┌──────────────┐     │
│    │ qwen3:0.6b   │   │ nomic-embed  │     │
│    │ (generate)   │   │ -text        │     │
│    └──────────────┘   └──────────────┘     │
│                                             │
│  On any LLM error → fallback to             │
│  nlp_service.parse(text) (deterministic)    │
└─────────────────────────────────────────────┘
```

### Module Map

| Module | Responsibility | File |
|---|---|---|
| **LLM Client** | Wraps ollama HTTP API via stdlib `urllib`. Timeout, retry, offline detection. | `src/ai/llm_client.py` |
| **Embeddings** | Calls ollama `/api/embed`, pure-Python cosine similarity. | `src/ai/embed.py` |
| **RAG Indexer** | Background poller: embeds new/changed files into SQLite. | `src/ai/rag_indexer.py` |
| **Assistant LLM** | Prompt → structured JSON (intent + entities + confidence). | `src/ai/assistant_llm.py` |
| **Agent** | Tool loop: LLM picks tools (search/answer/config/scan/status), RAG fills context, deterministic code executes. | `src/ai/agent.py` |

## LLM Client (`src/ai/llm_client.py`)

```python
# Conceptual contract (not final implementation):
def chat(model: str, prompt: str, *, think: bool = False,
         timeout_s: int = 30) -> str:
    """POST /api/generate, return response text.
    Raises ConnectionError if ollama unreachable.
    Raises TimeoutError on deadline."""

def embed(model: str, text: str) -> list[float]:
    """POST /api/embed, return vector.
    Raises ConnectionError / TimeoutError."""

def is_available() -> bool:
    """GET /api/tags, return True if ollama responds."""
```

- Uses `urllib.request` + `json.loads` — zero pip deps.
- All calls have configurable timeouts (default 30s for generate, 10s for embed).
- `is_available()` pings `/api/tags` once; cached for 60s to avoid hammering.
- On `ConnectionError` or `TimeoutError`, callers fall back to deterministic path.

### qwen3:0.6b Quirk

qwen3 models enable thinking by default. With `num_predict` budget under ~30 tokens, thinking consumes the entire budget and the response comes back empty. The client **always passes `"think": false`** in the request body for the 0.6B routing use-case. This is a known, documented behavior — not a bug.

## Embeddings + Vector Store (`src/ai/embed.py` + `src/ai/rag_indexer.py`)

### Embedding Model

- Default: `nomic-embed-text` (768-dim, ~274MB)
- Alternative: `all-minilm:l6-v2` (~23MB, 384-dim) — swap via config
- nomic-embed-text requires API prefixes: `"search_document:"` for indexing, `"search_query:"` for retrieval

### Storage

SQLite table added to existing `~/.local/share/FileManager/metadata.db`:

```sql
CREATE TABLE IF NOT EXISTS embeddings (
    path    TEXT PRIMARY KEY,
    model   TEXT NOT NULL,
    vector  TEXT NOT NULL,       -- JSON array of floats
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Pure-Python cosine similarity (no numpy):

```python
def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
```

### Indexer

Background `threading.Thread` (daemon, poller pattern):

1. Query `files` table for paths NOT in `embeddings` (or where `mtime > embeddings.updated_at`)
2. Batch-embed (up to 16 per ollama call via `/api/embed` with list input)
3. Insert into `embeddings` table
4. Sleep `config.ai.index_interval_s` (default: 300s)
5. Starts only if `config.ai.enabled == True`

### Retrieval

```python
def search(query: str, top_k: int = 5) -> list[dict]:
    """Embed query → cosine against all vectors → return top_k results."""
    # Returns: [{"path": "...", "filename": "...", "category": "...",
    #            "snippet": "...", "score": 0.82}, ...]
```

`snippet` = `text_sample` column from the `files` table (truncated to 200 chars).

## Agent Tool Loop (`src/ai/agent.py`)

The agent is a **single-turn** LLM call that picks a tool and returns structured JSON. No multi-step chains, no autonomous loops — that would be disproportionate for a file manager.

### Tool Definitions

| Tool | What it does | Deterministic fallback |
|---|---|---|
| `search` | RAG retrieval: embed query → top-k → LLM generates answer with citations | `nlp_service._handle_search()` |
| `answer` | General question about system status (no file search needed) | `nlp_service._handle_config()` for status |
| `config` | Config change proposal → gates through `config_agent` + Yes/No confirm bar | `nlp_service._handle_config()` |
| `scan` | Trigger manual scan of a path | `nlp_service` scan_path intent |
| `status` | Return system stats | `nlp_service._handle_config()` for debug_info |
| `unknown` | Can't determine intent | `nlp_service` full fallback |

### Prompt Structure

```
You are a file manager assistant. Given the user's message and the context below,
choose the best tool.

Available tools: search, answer, config, scan, status, unknown

Return JSON:
{"tool": "<tool>", "query": "<refined query for search>", "params": {}}

Context:
- Indexed files: {total_files} files across {categories}
- Example files: {sample filenames}
```

### RAG Answer Flow (for `search` tool)

1. Embed user query via `nomic-embed-text`
2. Retrieve top-5 matches from vector store
3. Format context: `"filename | category | snippet"` per match
4. LLM generates natural-language answer with filename citations
5. If zero matches: one auto-refine retry with the original query; if still zero, return "no relevant files found"
6. **No hallucinated paths** — citations are only filenames from retrieved results

## Config Schema v3

New `ai` key added to `DEFAULT_CONFIG` in `config_service.py`:

```python
# Schema v2 → v3 migration
def _migrate_to_v3(loaded: Dict[str, Any]) -> Dict[str, Any]:
    loaded.setdefault("ai", {
        "enabled": False,
        "model": "qwen3:0.6b",
        "embed_model": "nomic-embed-text",
        "timeout_s": 30,
        "index_interval_s": 300
    })
    return loaded

MIGRATIONS = {
    2: _migrate_to_v2,
    3: _migrate_to_v3,
}
```

| Key | Default | Meaning |
|---|---|---|
| `ai.enabled` | `False` | Master switch. Inert until flipped. |
| `ai.model` | `"qwen3:0.6b"` | Text generation model (ollama name) |
| `ai.embed_model` | `"nomic-embed-text"` | Embedding model (ollama name) |
| `ai.timeout_s` | `30` | Per-request timeout |
| `ai.index_interval_s` | `300` | Background indexer poll interval (seconds) |

## Integration Point: `chat.py`

```python
# src/gui/chat.py — _process_request (conceptual change)
def _process_request(self, text: str):
    try:
        from src.services.config_service import config_service
        ai_enabled = config_service.get("ai", {}).get("enabled", False)
    except Exception:
        ai_enabled = False

    if ai_enabled:
        try:
            from src.ai.agent import Agent
            agent = Agent()
            result = agent.process(text)
            # result has same shape as nlp_service.parse():
            # {"intent": ..., "entities": ..., "response": ...}
            if result.get("response"):
                self.after(0, lambda: self.add_message("Bot", result["response"]))
                return
            # If agent returns intent+entities, fall through to existing handlers
            intent = result.get("intent", "unknown")
            entities = result.get("entities", {})
        except Exception:
            # LLM unavailable — deterministic fallback
            pass

    # Existing deterministic path (unchanged)
    result = get_nlp_service().parse(text)
    ...
```

Key integration rule: **the LLM path and the deterministic path produce the same interface** — `{"intent": ..., "entities": ..., "response": ...}`. The GUI never knows which path was taken.

## Safety & Trust

| Concern | Mitigation |
|---|---|
| LLM hallucinates a file path | Citations are only filenames from retrieval results, never invented paths |
| LLM makes config change without consent | `config` tool returns a proposal; existing Yes/No confirm bar gates it |
| LLM unavailable (ollama not running) | `ConnectionError` → automatic fallback to `nlp_service` (deterministic) |
| Model too slow / hangs | Configurable timeout (default 30s); thread-based so GUI stays responsive |
| User doesn't want AI | `ai.enabled` defaults to `False`; app is identical to pre-AI state when off |
| Large model download surprise | Total footprint ~800MB; documented in docs and ADR-017; user must opt in |

## Phases

| Phase | What | Test gate |
|---|---|---|
| **1. Foundation** | `llm_client.py` + `embed.py` + `config_schema_v3` | `is_available()` returns True/False; embed returns 768-dim vector; schema migration v2→v3 works; all 236 existing tests pass |
| **2. Indexing** | `rag_indexer.py` + SQLite embeddings table | Indexer finds unembedded files, batch-embeds, stores correctly; search returns relevant results for known queries |
| **3. Intelligence** | `assistant_llm.py` + `agent.py` | Agent returns correct tool for known inputs; RAG answer includes real filenames; fallback fires when ollama is down |
| **4. Integration** | `chat.py` wiring + GUI indicator | Chat works with AI on/off; fallback transparent; no regressions in 236 tests |
| **5. Polish** | Live test with real models + app restart | End-to-end: type question → get grounded answer with file citations |

## Open Questions

1. **Embedding store size at scale**: For a personal file manager (hundreds to low thousands of files), the JSON-text vectors in SQLite are fine. At 10K+ files, consider binary packing or a dedicated vector store. Not needed now.
2. **Model swap**: If user wants absolute minimum, `all-minilm:l6-v2` (~23MB, 384-dim) can replace nomic-embed-text via config change. Quality trade-off exists but is acceptable for file-level retrieval.
3. **Multi-turn conversation**: Currently single-turn (one question, one answer). Multi-turn would need conversation history in the prompt. Future work if needed.
4. **Classifier ensemble**: Explicitly SKIPPED per user decision (smallest model, focus on Assistant). Could be added later via the same `llm_client.py` foundation.

## Files

| File | Role |
|---|---|
| `src/ai/llm_client.py` | ollama HTTP client (stdlib urllib) |
| `src/ai/embed.py` | Embedding calls + cosine similarity |
| `src/ai/rag_indexer.py` | Background indexer + SQLite vector store |
| `src/ai/assistant_llm.py` | Prompt → structured JSON (intent extraction) |
| `src/ai/agent.py` | Tool loop (search/answer/config/scan/status) |
| `src/gui/chat.py` | Integration point (LLM-first, deterministic fallback) |
| `src/services/config_service.py` | Schema v3 migration (`ai:` key, off by default) |
| `src/services/nlp_service.py` | Deterministic fallback (ADR-011, unchanged) |
