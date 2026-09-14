# ADR-017: Local LLM + Agentic RAG for the Assistant

## Status

Accepted (supersedes ADR-011's "LLM considered, not adopted" stance)

## Context

ADR-011 shipped a deterministic regex engine for the Assistant (NLP service). It was the right call: spaCy was theater (audit M1/M2), deterministic rules are testable, tiny, and honest about confidence. That ADR explicitly said "an LLM backend was considered but not adopted" and left it as future work.

Two conditions changed:

1. **The user explicitly requested it.** Not a theoretical upgrade — a concrete ask: "I want to install a rag system like agentic rag" using the smallest model available.
2. **The ollama runtime is now installed** on the machine (v0.34.0, user-space, no systemd). qwen3:0.6b and nomic-embed-text are pulled and verified working (API smoke test: generate returns tokens, embed returns 768-dim vectors).

The question is no longer "should we add an LLM?" but "how do we add one without undoing the honesty ADR-011 achieved?"

## Decision

Adopt a **local LLM + agentic RAG** for the Assistant chat, built on:

- **qwen3:0.6b** (~522MB) for text generation and intent routing
- **nomic-embed-text** (~274MB) for file embeddings and retrieval
- **stdlib urllib** ollama client (zero new pip dependencies)
- **SQLite-backed vector store** (JSON-text vectors in existing metadata.db)
- **Pure-Python cosine similarity** (no numpy, no torch)

The LLM **proposes**, the existing deterministic systems **dispose**:

- LLM picks a tool (search/answer/config/scan/status/unknown)
- Config changes still gate through `config_agent` + the Yes/No confirm bar
- File classification still uses the gate's confidence thresholds
- Any LLM failure (timeout, offline, bad output) falls back seamlessly to the current `nlp_service` regex engine

The feature is **off by default** (`ai.enabled: false`). The app is identical to pre-AI state until the user opts in.

## Alternatives Considered

- **API LLM (OpenAI/Claude)**:
  - Pros: Best quality, no local compute.
  - Cons: Privacy violation (files are personal), requires internet, ongoing cost, external dependency. Rejected — project privacy posture is "all local."
- **Larger local models (qwen3:8b, llama3:8b)**:
  - Pros: Better reasoning and generation quality.
  - Cons: 5-6GB VRAM pressure on RTX 3060 Ti 8GB, heavy for a file sorter. User chose smallest. Rejected.
- **Classifier ensemble via LLM (replace existing gate)**:
  - Pros: Unified AI-driven classification.
  - Cons: Disproportionate complexity, loss of deterministic testability, user explicitly chose smallest scope (Assistant only). Rejected — ensemble is future work if needed.
- **Keep ADR-011 status quo (no LLM)**:
  - Pros: Zero risk, zero complexity.
  - Cons: Ceiling on Assistant capability (no semantic search, no grounded answers). User explicitly asked for the upgrade. Rejected.
- **Skip RAG, use LLM memory only**:
  - Pros: Simpler.
  - Cons: No grounding = hallucinated file paths, unreliable answers. RAG provides verifiable citations. Rejected.

## Rationale

The core principle is **"LLM proposes, deterministic systems dispose."** ADR-011's value wasn't "no LLM" — it was "no theater." The regex engine was honest because it couldn't lie about confidence. The LLM integration preserves that honesty by:

1. Keeping the gate's confidence thresholds deterministic (LLM never feeds them)
2. Requiring explicit user consent for any config change (existing confirm bar)
3. Falling back to deterministic code on any failure (transparent to the user)
4. Citing only retrieved filenames, never inventing paths

The 0.6B model is honest about its limitations: fine for routing (which tool?), acceptable for short answers with RAG context, weak at open-ended generation. The design acknowledges this in the config (`model` is configurable) and in the fallback chain.

## Consequences

- **Benefits:** Assistant can now answer grounded questions about indexed files ("where are my PDFs from last week?"); semantic search beyond keyword matching; agentic tool selection; all local, all private, zero new dependencies.
- **Limitations:** Requires ollama runtime (~2.1GB binary + CUDA libs) installed separately; 0.6B model has limited reasoning (compensated by RAG grounding + deterministic fallback); background indexer adds a persistent thread; embeddings table grows with file count (acceptable for personal use).
- **Migration:** ADR-011's "not adopted" stance is superseded. The deterministic engine is preserved as fallback — it is not deleted or degraded, just no longer the primary path when AI is enabled.
