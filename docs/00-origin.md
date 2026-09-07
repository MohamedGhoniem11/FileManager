# 00 — Origin: Download Organizer → FileManager → War Room

> The honest backstory. No rewriting history — the projects speak for themselves.

## Act 1: The Idea — "Download Organizer"

The first artifact was a **spec**, not a product: a note describing an app that watches a Downloads folder, classifies files by type, and keeps directories tidy.

- The problem was real: manual file organization is tedious, error-prone, and doesn't scale.
- The spec was simple: watch → classify → move → stay out of the way.

## Act 2: The Build — "FileManager Pro"

The spec became a real application:

- `watchdog` real-time folder monitoring
- An extension-based classification engine
- SHA-256 duplicate detection
- A Natural-Language "assistant" tab backed by spaCy
- SQLite metadata + query history
- a `customtkinter` desktop UI
- GitHub Actions CI, PyInstaller packaging, 9 ADRs

It was a genuinely ambitious beginner project: modular layers, error-handling ambitions, dry-run-first culture. **But** — as the [audit](01-audit.md) proves with evidence — the intelligence was mostly theater, the safety layer described in the README did not exist in the code, and the test suite was red.

That's not a bad project. That's a *normal* project. The interesting work happens next.

## Act 3: The Discovery — "The War Room"

Between building FileManager and upgrading it, a second project happened: a **multi-agent incident response platform** built in the Band of Agents hackathon.

Five agents (Commander + 4 specialists) spoke over a shared event bus. Crucially, they didn't just answer — they **scored their own confidence** (a weighted `scorer.py`), challenged each other in a deliberation protocol, and escalated uncertain actions to a human-in-the-loop. Every action produced an evidence trail that fed an auto-generated postmortem.

The lesson: **the capability wasn't the clever part — the safety was.**

## Act 4: The Upgrade — "Agentic FileManager"

Two repos, one story. This repo's upgrade reuses the *patterns*, not the frameworks:

| War Room pattern | FileManager reuse |
|---|---|
| Incident Commander | File Commander (verdict orchestration) |
| Specialist agents | Analyzer / Classifier / Dedup / Rules / Corrector agents |
| AGREE/CHALLENGE deliberation | Disagreement before final classification |
| Weighted confidence + gate | Auto-move vs ask-human threshold |
| Human-in-the-loop remediation | Confirm-before-risky-move + undo journal |
| Evidence trail → postmortem | Transaction journal for every filesystem action |
| Typed Pydantic schemas | Validated config + typed file metadata |

Full design in [03-agentic-architecture.md](03-agentic-architecture.md).

---

## Why this story matters (interview framing)

> "I built a multi-agent system in a hackathon, then I took an older project of mine, audited it honestly, and upgraded it using those patterns — safety first, evidence always. This repo is that upgrade, documented as I made the decisions."