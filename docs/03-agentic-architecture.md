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
| **Analyzer** | Logs agent (evidence gathering) | Reads file internals: PDF text, image EXIF/OCR, code structure, archive manifest | file path + content | `ContentProfile` (typed, Pydantic) |
| **Classifier** | Metrics agent (anomaly scoring) | Proposes category + confidence from content profile + history | ContentProfile, filename, priors | Proposal (category, confidence 0-1) |
| **Dedup Agent** | Runbook agent (pattern matching) | Exact + near-duplicate fingerprints | ContentProfile hashes, similarity | Duplicate clusters + stale copies |
| **Rules Agent** | Change agent (deploy correlation) | Evaluates user policies vs file facts; flags safe/risky | User policy set + ContentProfile | Matched policies + risk flags |
| **Corrector** | Deliberation loop (AGREE/CHALLENGE) | Learns from user corrections; adjusts classifier priors | correction events | updated priors |

**Frameworks note:** The War Room used multiple SDKs to prove interop. For a desktop tool, ONE lightweight decision layer (rules+statistics base, optional small LLM) is the call — see [ADR-011](decisions/ADR-011-classification-engine-rules-plus-llm.md).

---

## 2. The Deliberation Protocol (the "why agents" answer)

Old flow (deterministic, 1 op):
```
extension → move
```

New flow (evidence + contention):
```
file arrives
  → Analyzer extracts ContentProfile
  → Classifier proposes:            Tax (0.92), Documents (0.05)...
  → Dedup Agent:                    "hash-equal to Tax/invoice-2024-03.pdf"
  → Rules Agent:                    "policy 'receipts → Tax' matches (safe)"
  → Commander deliberation:
      - all agents weighted (War Room scorer pattern)
      - agreement → confidence up, disagreement → confidence down
      - verdict path:
          ≥ threshold     → move + journal
          below threshold → human gate (preview + confirm)
  → Corrector listens: user correction → priors update next time
```

### Channels (event bus — [ADR-010](decisions/ADR-010-in-process-event-bus.md))

```
file-events ──► Commander ──► analysis-results ──► Analyzer
                    │              │
                    ├──► proposals ───► Classifier
                    ├──► deliberation ─► Dedup, Rules
                    ├──► verdicts ─────► Journal, GUI
                    └──► corrections ──► Corrector → Classifier priors
```

---

## 3. Confidence Scoring (port of War Room `scorer.py`)

| Signal | Weight |
|---|---|
| Analyzer content signals | 0.45 |
| Classifier proposal | 0.25 |
| Dedup corroboration | 0.15 |
| Rules match | 0.10 |
| Prior history / corrections | 0.05 |

Deliberation adjustments (War Room AGREE/CHALLENGE protocol):
- Dedup agrees with classifier → +0.08
- Rules flags risk (`risk=high`) → cap at 0.70 max / force human gate
- Low Analyzer signal (empty/opaque file) → max confidence 0.60 → always asks human

Gates (thresholds per category — [ADR-015](decisions/ADR-015-per-category-confidence-thresholds.md)):
- ≥ 0.80 → auto-move + journal entry
- 0.50–0.79 → suggest + human confirm (preview)
- < 0.50 → hold in "needs review", never auto-act

---

## 4. Data Model (Pydantic — same discipline as War Room)

```python
class ContentProfile(BaseModel):
    path: Path
    mime_hint: str
    extracted_text: str | None        # PDF/doc/code/text
    metadata: dict[str, Any]          # EXIF, headers, manifest
    fingerprints: dict[str, str]      # sha256, perceptual, normalized-text
    confidence_floor: float           # 1.0 on unreadable → forces gate

class ClassificationProposal(BaseModel):
    category: str
    confidence: float
    evidence_ids: list[str]           # EVD-* traceability (War Room pattern)

class Verdict(BaseModel):             # commander output
    path: Path
    action: Literal["move","hold","ask"]
    target: Path | None
    confidence: float
    reasoning: str
    journal_id: str | None

class JournalEntry(BaseModel):        # the undo story
    id: str
    timestamp: datetime
    action: str
    source: Path
    destination: Path | None
    verdict: Verdict
    reversible: bool
```

---

## 5. The Transaction Journal (safety layer — replaces "no undo")

- **Write-ahead design:** journal entry is committed BEFORE the move; the move is a "pending" entry finalized on success — [ADR-013](decisions/ADR-013-append-only-transaction-journal.md)
- **Undo = replay journal in reverse** (file-level: `move:dest→src`; delete: only if trash-enabled)
- **Provenance:** every path change queryable — "where did X go?" (the War Room evidence trail → postmortem pattern)
- SQLite **WAL mode + single-connection discipline** (fixes audit H2)

---

## 6. What FAILS CLOSED (safety invariants)

1. **Unreadable file → confidence floor 0.60 → always human gate** (never auto-move opaque content)
2. **Risk-flagged rule → capped 0.70 / forced gate** (Rules Agent veto power)
3. **Never delete what you failed to classify** (kills the "Others → orphan → delete" abuse)
4. **Journal before action** — crash mid-move = recoverable, not lost
5. **Dry-run everywhere** — every screen has a "show me first" preview built on the same pipeline

---

## 7. What We Deliberately Keep / Kill

### Keep
- services/core/gui layering (it aged well)
- customtkinter (noted as debt in audit; UI is not this story — [D4 decision](decisions/ADR-003-gui-toolkit-tkinter.md) stands)
- watchdog observer shell (event source — just wired into channels)
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
| Multi-agent deliberation | **None** (everyone uses one model or a tiered pipeline) | Analyzer/Classifier/Dedup/Rules debate; Commander arbitrates |
| Confidence-gated escalation | sift-ai only (0★, threshold only) | Per-agent disagreement → council vote → escalate only contested files |
| Correction-driven learning | One unverified 0★ project (pickle-based) | Persistent correction ledger → policy/prior updates, tested |
| Structured decision journal | Nobody (TheYellowDuck has move-only log) | Verdicts with agent reasoning, queryable, undoable |

### Calibration is the non-negotiable (validated against production systems)
Production confidence gates exist for exactly this shape of problem: **Microsoft SCL** (multi-tier spam thresholds: 5-6 vs 9), **Salesforce Data 360 auto tagging** ("approve tags at threshold, rest to manual review"), **AWS AgentCore** claims routing (auto-approve vs HUMAN_REVIEW, fail-safe default), **NVIDIA**'s 4-band router. The deliberate protocol follows the **uncertainty-sampling** pattern from active learning (Munro, *HITL Machine Learning*, ch. 3).

The one lesson all of them converge on: **a raw confidence score is not a probability.** Modern classifiers are systematically overconfident (Guo et al., ICML 2017), so:
- Measure **Expected Calibration Error (ECE)** on a held-out set; apply temperature scaling / isotonic regression
- Re-derive thresholds from **calibrated** scores, not raw ones
- Keep **deterministic overrides** (critical file classes never auto-move regardless of score — mirroring AWS's fail-safe routing)
- Use **asymmetric thresholds**: conservative auto-move band, wide ask-human band (wrong move ≈ irreversible cost)

This is now encoded in [ADR-015](decisions/ADR-015-per-category-confidence-thresholds.md).

---

## 9. Journal validated against real undo systems

The append-only journal ([ADR-013](decisions/ADR-013-append-only-transaction-journal.md)) goes **beyond** production desktop file managers — which is correct for a batch organizer:
- Dolphin (`KIO::FileUndoManager`) and Nautilus both keep undo **in-memory only**; a crash loses everything. Our journal survives restart.
- `send2trash` establishes the "never hard-delete" primitive — our Journal should delegate deletes to OS trash.
- Known pitfall (Zed, tine bugs): **undo after external modification loses data.** Journal must record per-file `mtime + size` at op time and **validate state before replaying undo**.
- Cross-device (`EXDEV`) and hardlink identities also break naive replay — journal tracks operation type + inode, and marks non-atomic moves as `copy+delete` (undo = re-copy).