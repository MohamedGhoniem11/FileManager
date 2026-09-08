# ADR-011: Classification Engine — Rules + Statistics (LLM Considered, Not Adopted)

## Status
Accepted

## Context
The old system loaded spaCy (`en_core_web_sm`, ~700MB dependency chain) but all parsing was keyword/regex — the model never influenced a decision (audit M1/M2). The upgrade needs content-aware classification with confidence scores. Options: a small local LLM, an API-based LLM, or a deterministic rules+statistics engine.

## Decision
Build the classifier on **deterministic rules + content statistics** (extension priors, content keywords, ContentProfile signals, prior history) that outputs confidence scores and is fully unit-testable. An LLM backend (local via Ollama or API) was considered as an optional upgrade but was **not adopted**; the shipped engine is rules + statistics only, with no pluggable interface. The system never hard-fails on model absence because there is no model.

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
Deterministic base = testable, fast, offline, and honest about confidence (statistical signals are well-defined). An LLM backend was considered as optional headroom for the "semantic search" narrative, but was not adopted — the deterministic engine is what shipped. This also directly answers the interview question "why not just use an LLM?" — with a real tradeoff table.

## Consequences
- **Benefits**: Deterministic behavior for tests, tiny dependency footprint, believable confidence scores.
- **Limitations**: No LLM-grade semantic understanding; regex/keyword ceiling on exotic inputs. An LLM backend remains future work if semantic search is ever needed.

## Update (2026-09-09): What shipped
The shipped architecture is: extension-prior + filename keywords +
ContentProfile signals → confidence (`src/core/classifier.py`,
`src/core/analyzer.py`), a gate that decides auto/ask/hold
(`src/core/gate.py`), and declarative YAML rules with dry-run evaluation
(`src/core/rules_agent.py`). There is no pluggable classifier interface and
no LLM wiring anywhere in `src/`; the "optional LLM" was considered and
explicitly not adopted. Rules + statistics is what shipped.