# 03 — Agentic Architecture: The File Council

> Grounded in The War Room's actual patterns (agents, weighted scoring, deliberation, human-in-the-loop, evidence trails) mapped onto the file domain. Decisions formalized in [ADR-010..015](decisions/).

---

## 0. Design Goal

Upgrade FileManager WITHOUT rewriting its working skeleton (services/core/gui layering survives). Add an **agentic judgment layer** where the old system had a lookup table — reusing War Room *patterns*, not reusing its frameworks.

---

## 1. The Agent Roster (War Room → File Domain)

| Agent | War Room origin | File-domain job | Inputs | Output |
|---|---|---|---|---|
| **Commander** | Incident Commander (orchestrates verdicts) | Orchestrates classification verdicts; owns confidence gates; writes journal | All agent outputs | Verdict: move / hold / ask-human |
| **Analyzer** | Logs agent (evidence gathering) | Reads file internals: PDF text, image EXIF presence, code structure, archive manifest | file path + content | `ContentProfile` (typed dataclass) |
| **Classifier** | Metrics agent (anomaly scoring) | Proposes category + confidence from content profile + history | ContentProfile, filename, priors | Proposal (category, confidence 0-1) |
| **Dedup Agent** | Runbook agent (pattern matching) | Exact + near-duplicate fingerprints | ContentProfile hashes, similarity | Duplicate clusters + stale copies |
| **Rules Agent** | Change agent (deploy correlation) | Evaluates user policies vs file facts; flags safe/risky | User policy set + ContentProfile | Matched policies + risk flags |
| **Corrector** | Deliberation loop (AGREE/CHALLENGE) | Learns from user corrections; adjusts classifier priors | correction events | updated priors |

**Frameworks note:** The War Room used multiple SDKs to prove interop. For a desktop tool, ONE lightweight decision layer (rules+statistics base) is the call — see [ADR-011](decisions/ADR-011-classification-engine-rules-plus-llm.md).

---

## 2. The Decision Protocol (the "why agents" answer)

Old flow (deterministic, 1 op):
```
extension → move
```

New flow (evidence + gate):
```
file arrives
  → Analyzer extracts ContentProfile
  → Classifier proposes:            PDFs (0.80), Documents (0.05)...
  → Rules Agent:                    "policy 'receipts → PDFs' matches (safe)"
  → Gate decides (auto / ask / hold):
      - confidence = extension prior + content evidence + priors memory
      - risk-flagged rules cap confidence at 0.70
      - verdict path:
          ≥ 0.80 (auto) → move + journal
          0.50–0.79 (ask) → index in place, ask the user
          < 0.50 (hold) → index in place, never auto-act
  → Corrector: user correction → priors update next time
```

### Wiring (direct calls — no event bus)

```
observer._process_file
  → classifier.classify_with_confidence(file)
  → rules_agent.evaluate(file, classification)
  → gate.decide(category, confidence, thresholds, risk_flagged)
  → auto: organizer.move_file + db_service.upsert_file
  → ask/hold: db_service.upsert_file (index in place)
```

---

## 3. Confidence Scoring (port of War Room `scorer.py`)

| Signal | Weight |
|---|---|
| Extension prior (known category) | 0.60 |
| Extension prior (unknown → "Others") | 0.15 |
| Content evidence: image | +0.25 |
| Content evidence: receipt (strong keywords) | +0.20 |
| Content evidence: any readable content | +0.05 |
| Priors memory (corrections for this filename family) | +0.05 per correction, capped at +0.20 |

Adjustments:
- Risk-flagged rules cap effective confidence at 0.70 and demote auto → ask ([ADR-015](decisions/ADR-015-per-category-confidence-thresholds.md))
- Confidence is clamped to [0, 1]

Gates (thresholds per category — [ADR-015](decisions/ADR-015-per-category-confidence-thresholds.md)):
- ≥ 0.80 → auto-move + journal entry
- 0.50–0.79 → ask: index in place, leave for the user
- < 0.50 → hold: index in place, never auto-act

---

## 4. Data Model (typed, dependency-free)

```python
@dataclass
class ContentProfile:                 # analyzer output
    kind: str                         # pdf|image|code|text|archive|binary|unknown
    text_sample: str = ""             # extracted text (pdf/code/text)
    dimensions: tuple | None          # images
    keywords: list[str]               # top content tokens
    metadata: dict[str, Any]          # has_exif, headers, manifest

class Classification(NamedTuple):     # classifier output
    category: str
    confidence: float
    subcategory: str | None           # "receipt" | "code" | None
    signals: dict[str, Any]           # extension, content_kind, keywords, ext_prior, priors

class GateDecision(NamedTuple):       # gate output
    action: str                       # "auto" | "ask" | "hold"
    band: str
    effective_confidence: float
    reason: str
```

The journal is a SQLite table, not an in-memory model: `op_type` (rename/copy_delete/trash), source/dest paths, inode, mtime, size, `reversible`, `status` (pending/committed/reversed), and timestamps — append-only, DB-trigger enforced.

---

## 5. The Transaction Journal (safety layer — replaces "no undo")

- **Write-ahead design:** journal entry is committed BEFORE the move; the move is a "pending" entry finalized on success — [ADR-013](decisions/ADR-013-append-only-transaction-journal.md)
- **Undo = replay journal in reverse** (file-level: `move:dest→src`; only journaled moves are undoable — deletes are not journaled)
- **Provenance:** every path change queryable — "where did X go?" (the War Room evidence trail → postmortem pattern)
- SQLite **WAL mode + single-connection discipline** (fixes audit H2)

---

## 6. What FAILS CLOSED (safety invariants)

1. **Unreadable file → no content evidence → confidence stays at the extension prior (0.60 known category, 0.15 unknown) → never auto-moves**
2. **Risk-flagged rule → capped 0.70 / forced gate** (Rules Agent veto power)
3. **Never delete what you failed to classify** (kills the "Others → orphan → delete" abuse)
4. **Journal before action** — crash mid-move = recoverable, not lost
5. **Dry-run by default** — cleanup and lifecycle runs preview first (`cleanup.dry_run`), and the Maintenance tab shows proposed actions before anything executes

---

## 7. What We Deliberately Keep / Kill

### Keep
- services/core/gui layering (it aged well)
- customtkinter (noted as debt in audit; UI is not this story — [ADR-003](decisions/ADR-003-gui-toolkit-tkinter.md) stands)
- watchdog observer shell (event source — wired into the classification pipeline)
- dry-run-first culture (already good — make it universal)

### Kill
- spaCy theater ([ADR-011](decisions/ADR-011-classification-engine-rules-plus-llm.md))
- `time.sleep(1)` (readiness retry — roadmap step 1.4)
- "Others orphan deletion" path
- Unconditional Windows imports ([ADR-014](decisions/ADR-014-cross-platform-platformdirs.md))

---

## 8. Landscape Check — what exists vs what we build (checked Sep 2026)

The agentic file-organizer space was surveyed before locking this design. Two honest conclusions:

### The space splits into two shallow patterns
1. **"Smart Sorter"** (llama-fs 5.8k★, Local-File-Organizer 3.4k★, AI File Sorter 1.6k★): one LLM decides the category and moves the file. **Zero or near-zero safety** — no confidence gating, no undo, no human gate in the big ones.
2. **"Review Tool"** (TheYellowDuck, sift-ai, both 0★): a simple confidence threshold routes to a human. Closest to our gate, but single-model, no deliberation, no learning loop.

### The gaps nobody fills (our honest moat)
| Gap in the landscape | Who has it | What we build instead |
|---|---|---|
| Multi-agent deliberation | **None** (everyone uses one model or a tiered pipeline) | Analyzer → Classifier → Rules → Gate pipeline with explainable confidence signals |
| Confidence-gated escalation | sift-ai only (0★, threshold only) | Auto/ask/hold bands escalate uncertain files to the human |
| Correction-driven learning | One unverified 0★ project (pickle-based) | Persistent priors that update from corrections, tested |
| Structured decision journal | Nobody (TheYellowDuck has move-only log) | Journaled moves with confidence scores, queryable, undoable |

### Calibration is the non-negotiable (validated against production systems)
Production confidence gates exist for exactly this shape of problem: **Microsoft SCL** (multi-tier spam thresholds: 5-6 vs 9), **Salesforce Data 360 auto tagging** ("approve tags at threshold, rest to manual review"), **AWS AgentCore** claims routing (auto-approve vs HUMAN_REVIEW, fail-safe default), **NVIDIA**'s 4-band router. The deliberate protocol follows the **uncertainty-sampling** pattern from active learning (Munro, *HITL Machine Learning*, ch. 3).

The one lesson all of them converge on: **a raw confidence score is not a probability.** Modern classifiers are systematically overconfident (Guo et al., ICML 2017). The implemented response:
- **Asymmetric thresholds**: conservative auto-move band (≥ 0.80), wide ask-human band (0.50–0.79) — wrong move ≈ irreversible cost
- **Risk cap**: risk-flagged rules cap effective confidence at 0.70 and can never auto-fire
- **Per-category overrides**: categories can tighten their own auto/ask thresholds

This is encoded in [ADR-015](decisions/ADR-015-per-category-confidence-thresholds.md).

---

## 9. Journal validated against real undo systems

The append-only journal ([ADR-013](decisions/ADR-013-append-only-transaction-journal.md)) goes **beyond** production desktop file managers — which is correct for a batch organizer:
- Dolphin (`KIO::FileUndoManager`) and Nautilus both keep undo **in-memory only**; a crash loses everything. Our journal survives restart.
- Deletes are **not** journaled: `delete_file` removes directly, so undo covers moves only ([ADR-016](decisions/ADR-016-safe-journal-backed-undo.md)).
- Known pitfall (Zed, tine bugs): **undo after external modification loses data.** Journal must record per-file `mtime + size` at op time and **validate state before replaying undo**.
- Cross-device (`EXDEV`) and hardlink identities also break naive replay — the journal records operation type + inode; every entry today is `rename`, so undo renames back (copy+delete and trash inverses are not implemented).