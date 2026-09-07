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