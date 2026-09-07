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

## Update (2026-09-07): Calibration is a precondition, not an option
Research on production confidence gates (Microsoft SCL, Salesforce Data 360, AWS AgentCore, NVIDIA router; underpinned by Guo et al. ICML 2017) established one non-negotiable: **a raw confidence score is not a probability.** Modern classifiers are systematically overconfident. Thresholds derived from raw scores therefore auto-move files at real accuracy far below the nominal threshold.

Amendments:
1. **Measure Expected Calibration Error (ECE)** on a held-out set before thresholds are trusted.
2. **Apply temperature scaling / isotonic regression** to calibrate scores; re-derive all thresholds from calibrated scores.
3. **Deterministic overrides** — certain file classes (e.g., anything in a critical directory, any delete-class action) bypass the confidence gate entirely and require human review regardless of score (mirrors AWS AgentCore's fail-safe default: `(0, HUMAN_REVIEW)`).
4. **Asymmetric thresholds** — auto-move band conservative (high), ask-human band wide, because a wrong move is near-irreversible (false-move ≫ false-hold in cost); track the two error rates separately.
5. **Discrete bands over hard edge** — treat 0.79 vs 0.81 as the same band, not a cliff; avoid claiming precision the score doesn't have.