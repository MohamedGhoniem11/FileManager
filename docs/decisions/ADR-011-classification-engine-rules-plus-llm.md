# ADR-011: Classification Engine — Rules+Statistics Base with Optional LLM

## Status
Accepted

## Context
The old system loaded spaCy (`en_core_web_sm`, ~700MB dependency chain) but all parsing was keyword/regex — the model never influenced a decision (audit M1/M2). The upgrade needs content-aware classification with confidence scores. Options: a small local LLM, an API-based LLM, or a deterministic rules+statistics engine.

## Decision
Build the base classifier on **deterministic rules + content statistics** (keyword weights, metadata signals, filename heuristics, prior history) that outputs confidence scores and is fully unit-testable. Expose a **pluggable classifier interface** so an LLM (local via Ollama or API) can be an optional upgrade; the system must never hard-fail when the LLM is absent — it falls back to the deterministic engine.

## Alternatives Considered
- **spaCy again (status quo)**:
  - Pros: Already in requirements.
  - Cons: Proven theater (M1); huge bundle; no confidence output.
- **API LLM (primary)**:
  - Pros: Best semantic quality.
  - Cons: Privacy (files are personal), latency, offline broken, cost.
- **Local LLM (Ollama) required**:
  - Pros: Private, good quality.
  - Cons: Multi-GB install for a file sorter; heavy for the feature's value.

## Rationale
Deterministic base = testable, fast, offline, and honest about confidence (statistical signals are well-defined). LLM as pluggable optional = headroom for the "semantic search" narrative without making the app unusable without it. This also directly answers the interview question "why not just use an LLM?" — with a real tradeoff table.

## Consequences
- **Benefits**: Deterministic behavior for tests, tiny dependency footprint, graceful degradation, believable confidence scores.
- **Limitations**: LLM-grade semantic understanding only when the optional model is configured; regex-quality ceiling on exotic inputs until then.