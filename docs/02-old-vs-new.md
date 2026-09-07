# 02 — Agentic FileManager: The Transformation Pitch

**Before:** a file sorter that guesses by extension.
**After:** a system that examines, deliberates, and asks before it acts.

---

## 1. The Old System (honest snapshot)

### What it did
- Watch a folder → read a file's extension → move it to a matching folder
- SHA-256 duplicate detection (exact copies only)
- Regex "NLP" assistant + a 700MB spaCy model that never made a decision
- Health audit: empty folders, zero-byte files, "orphans"
- Windows-only desktop app (customtkinter)

### What it couldn't do — and the failure modes

| The old way | The failure |
|---|---|
| `report_final.pdf` → "PDFs" folder | A *receipt*, a *tax form*, and a *book* are all just "PDFs" to it |
| Unknown `.xyz` → "Others" folder | The health engine then calls these "orphans" and suggests DELETING them — the system punishes files for its own tiny vocabulary |
| Move a file → done, forever | One wrong rule = files scattered permanently. No undo. No trace |
| sleep(1) then move | Large downloads still being written get skipped or moved half-baked |
| "find my invoices from March" | Regex can't do semantic search — it matched keywords, not meaning |

### The audit verdict (evidence, not vibes)
- CI was red: a test imports a symbol that doesn't exist (`test_nlp_db.py` → `nlp_service`)
- Config changes crashed a background thread: `classifier.py` uses `logger` without importing it
- README described a FileLock retry + event-loop cooldown — **neither exists in the code**
- 700MB of NLP dependencies for pure regex matching

Full evidence: [01-audit.md](01-audit.md)

---

## 2. The Three Structural Truths

1. **The intelligence layer was theater** — complexity without capability
2. **The safety layer didn't exist** — the docs described it; the code shipped without it
3. **Classification punished ignorance instead of learning** — a miss became a deletion suggestion

---

## 3. The New System — "The File Council"

Instead of one dumb mapping table, file handling becomes a **deliberation**:

```
                     ┌──────────────────────┐
                     │     Commander        │  ← orchestrates, scores, gates
                     └──────────┬───────────┘
                    fan-out analysis
        ┌─────────────┬──────────┼──────────┬──────────────┐
        ▼             ▼          ▼          ▼              ▼
   ┌───────────┐ ┌───────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
   │ Analyzer  │ │Classifier │ │Dedup   │ │Rules     │ │ Corrector│
   │ Agent     │ │ Agent     │ │ Agent  │ │ Agent    │ │ (learns) │
   └───────────┘ └───────────┘ └────────┘ └──────────┘ └──────────┘
        │ reads        │ proposes    │ near-    │ applies   │ user drags
        │ content      │ category +  │ dup      │ policies  │ file →
        │ inside files │ confidence  │ detect   │ + HITL    │ system remembers
```

### What each agent actually does (domain-real)

| Agent | Reads | Decides | Example outcome |
|---|---|---|---|
| **Analyzer** | PDF text, image EXIF/OCR, code structure, archive manifest | What IS this file, not what does its suffix say | "This isn't a PDF — it's a tax receipt (sender: bank)" |
| **Classifier** | Analyzer output + filename + history | Category with confidence score | "Tax — 92% confidence" |
| **Dedup Agent** | Content fingerprints (not just SHA-256) | Near-duplicates: same doc re-saved, renamed, converted | "These 11 'final_v2' files are 3 real versions" |
| **Rules Agent** | User policies + file facts | Which rule fires, and is it safe? | "Videos > 1GB → External drive (requires confirmation)" |
| **Commander** | All agent outputs | The verdict: move / hold / ask human | "94% sure → auto-move, journaled. 58% → ask you first." |
| **Corrector** | Your corrections | Updates the classifier's priors | You drag a receipt to "Tax" → it never guesses "PDFs" again |

---

## 4. Side-by-Side (the interview slide)

| Dimension | OLD | NEW |
|---|---|---|
| Classification input | file extension | file **content** + context + history |
| Classification output | one bucket | **category + confidence score** |
| Model | 700MB spaCy, never used | lightweight, used for real decisions |
| On disagreement | — (impossible) | agents **deliberate**; commander arbitrates |
| On uncertainty | silent mis-sort | **asks the human** (HITL gate) |
| On mistakes | permanent, invisible | **undo journal**, every move traceable |
| Duplicates | exact hash only | exact + **near-duplicate** fingerprints |
| Old files | accumulate forever | **lifecycle policies** (archive, threshold alerts) |
| After user correction | nothing | **learns** for the future |
| Platforms | Windows only | **cross-platform** |
| Tests | broken suite | green, high coverage, TDD'd |

---

## 5. Where The War Room Patterns Live

Every agentic muscle came from the hackathon project — that's the portfolio bridge:

| War Room pattern (The War Room) | Reused here as |
|---|---|
| Incident Commander (LangGraph) | File Commander orchestrating verdicts |
| Metrics/Logs/Change/Runbook agents | Analyzer / Classifier / Dedup / Rules agents |
| AGREE/CHALLENGE deliberation protocol | Agent disagreement before final classification |
| `scorer.py` weighted confidence + gating | Confidence gate: auto-move vs ask-human |
| HITL remediation engine | Confirm-before-risky-move + undo journal |
| Evidence trail → Git-Ops postmortem | Transaction journal for every movement |
| Pydantic schemas everywhere | Validated config + typed file metadata |

> "Same architectural patterns, different domain: incident response → file organization."

---

## 6. The One-Sentence Pitch

> **"The old system treated file organization as a lookup table. The new one treats it as a judgment call — with the same confidence scoring, human gates, and audit trails I built for multi-agent incident response."**

---

## 7. Before / After (for the screen recording)

| Metric | Before | After |
|---|---|---|
| Test suite | broken (ImportError) | green |
| Classification accuracy | ext-only guessing | content + confidence scoring |
| Undo | none | full journal |
| Data-loss risk | silent overwrites possible | gated + journaled |
| Platform | Windows | cross-platform |
| Learning | none | correct-once-remembers-forever |