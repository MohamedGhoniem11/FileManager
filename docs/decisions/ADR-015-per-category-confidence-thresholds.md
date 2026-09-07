# ADR-015: User-Configurable Confidence Thresholds per Category

## Status
Accepted

## Context
The Commander gates actions by confidence (auto-move vs ask-human vs hold). A single global threshold would force every category into the same automation level — but "receipts" (low stakes, easy to classify) and "keep-if-unsure work files" (high stakes) clearly merit different behavior.

## Decision
Expose **per-category confidence thresholds** in the config, with safe defaults:
- Global defaults: auto ≥ 0.80, ask 0.50–0.79, hold < 0.50
- Per-category overrides (e.g., "Critical/Work: always ask, auto disabled")
- Risk-flagged rules (Rules Agent) cap effective confidence at 0.70 and force the gate regardless of thresholds (safety invariant, not user-bypassable)

## Alternatives Considered
- **Single global threshold**:
  - Pros: Simple.
  - Cons: Wrong granularity; users can't trust auto-mode for precious folders.
- **No thresholds (always ask)**:
  - Pros: Safest.
  - Cons: Annoying daily; defeats the purpose of confidence scoring.

## Rationale
Per-category thresholds make the confidence-scoring story real and user-facing: the score exists because it gates behavior, and the gate is tunable where it matters. Safety-critical categories remain protected by the risk-cap invariant.

## Consequences
- **Benefits**: Users can automate low-stakes folders and keep high-stakes ones manual; the HITL story is demonstrable per category.
- **Limitations**: Config surface grows (acceptable — validated by typed config schema from ADR-013's migration effort).