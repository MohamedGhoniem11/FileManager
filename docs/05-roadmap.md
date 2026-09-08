# 05 — Roadmap: Phased Implementation Plan

> Testable milestones. Each step is one demonstrable idea — commit-sized, screen-recordable on its own.
> This fixes the audit findings in dependency order (F-numbers link to [01-audit.md](01-audit.md)).

---

## Step 1 — Correctness fixes (green CI, stable app, honest docs) ✅ Done

| # | Work | Fixes | Verification |
|---|---|---|---|
| 1.0 | Platform-marker `winshell`/`pypiwin32` in `requirements.txt` *(found during setup: pip install fails on Linux)* | C6 | `pip install -r requirements.txt` on ubuntu succeeds |
| 1.1 | Import `logger` in `classifier.py` | C1 | `pytest` + manual config-change run |
| 1.2 | Fix `test_nlp_db.py` import (use `get_nlp_service()`) | C2 | `pytest` collects + passes |
| 1.3 | Platform-guard `startup_service.py` (import only on Windows) | C3 | import on Linux/macOS succeeds |
| 1.4 | Replace `time.sleep(1)` with readiness retry (`PermissionError` loop + partial-size guard) in `observer.py` | C4 | large-download test: no half-moves |
| 1.5 | Correct README claims (FileLock, cooldown, clone URL, badge, test count) | C4 | README matches code |

**Gate:** `pytest` green end-to-end. This alone turns the red CI badge into a real one.

## Step 2 — Data integrity (journal groundwork) ✅ Done

| # | Work | Fixes | Verification |
|---|---|---|---|
| 2.1 | SQLite WAL + single-connection discipline | H2 | [concurrent-thread stress test](../tests/test_data_integrity.py) |
| 2.2 | Replace empty `except: pass` with structured logging | H1 | [failure-injection test](../tests/test_data_integrity.py) |
| 2.3 | Absolute config/log paths via `platformdirs` | H4 | [default-home tests](../tests/test_data_integrity.py), [ADR-014](decisions/ADR-014-cross-platform-platformdirs.md) |
| 2.4 | Config schema version + migration path | (F9) | [version-bump migration tests](../tests/test_config.py) |
| 2.5 | Transaction journal schema (append-only, versioned) | H3 | [journal tests](../tests/test_journal.py), [ADR-013](decisions/ADR-013-append-only-transaction-journal.md) |

**Gate:** no silent failure paths remain; every move is journaled.

## Step 3 — The undo story ✅ Done

| # | Work | Fixes | Verification |
|---|---|---|---|
| 3.1 | Journal-backed undo: reverse replay, batched undo | H3 | [undo tests](../tests/test_undo.py): LIFO replay, batched undo, writes count of reversed entries |
| 3.2 | Provenance queries ("where did X go?") | H3 | [journal_provenance tests](../tests/test_undo.py): source/dest lookup, id-ordered, empty for unknown paths |

**Gate:** undo is unit-tested ([ADR-016](decisions/ADR-016-safe-journal-backed-undo.md)) and demoable via `Organizer.undo_last()` — GUI wiring rides on later GUI steps.

## Step 4 — The intelligence story (Analyzer + content classification)

| # | Work | Fixes | Verification |
|---|---|---|---|
| 4.1 | `ContentProfile` extraction (PDF text, EXIF, code head, archive manifest) | M4 | fixture files → expected profiles |
| 4.2 | Classifier uses ContentProfile + priors, outputs confidence | M4, M1 | classification accuracy snapshot test |
| 4.3 | Kill spaCy theater / regex-only paths | M1, M2 | [ADR-011](decisions/ADR-011-nlp-classification-engine.md) decision implemented |

**Gate:** a receipt and a book (both `.pdf`) classify differently, with confidence.

## Step 5 — Deduplication + learning

| # | Work | Fixes | Verification |
|---|---|---|---|
| 5.1 | Near-duplicate fingerprints (perceptual + normalized-text) | M5 | renamed/re-saved copies cluster correctly |
| 5.2 | Corrector loop: priors update from user drags | M3 | correction → next similar file lands right |

**Gate:** duplicate clusters show "N files ≈ 3 real versions"; correction learning is tested.

## Step 6 — Trust & configurability (gates + rules)

| # | Work | Fixes | Verification |
|---|---|---|---|
| 6.1 | Confidence threshold gate (auto / ask / hold) | M3 | threshold tests per category |
| 6.2 | Rules Agent (visual + NL rules, dry-run preview) | M4 | rule-match tests + dry-run no-op test |
| 6.3 | Risk-flagged rules cap confidence / force gate | (safety) | risk-rule never auto-moves |

**Gate:** below-threshold files always ask; risky rules never auto-fire.

## Step 7 — Lifecycle + multi-location

| # | Work | Fixes | Verification |
|---|---|---|---|
| 7.1 | Age/size lifecycle policies + scheduled runs | (B6) | aging fixture → archive action |
| 7.2 | Multi-location monitoring, per-location rules | (B7) | two watch folders, independent rules |

## Step 8 — Cross-platform polish

| # | Work | Fixes | Verification |
|---|---|---|---|
| 8.1 | Remove remaining Windows-only import paths | C3 | CI runs the suite on ubuntu + windows + macos |
| 8.2 | `platformdirs` config/log/cache homes everywhere | H4 | packaged and source runs |

## Step 9 — Health Audit 2.0 + assistant polish

| # | Work | Fixes | Verification |
|---|---|---|---|
| 9.1 | Health findings explain + propose safe undoable actions | M3 | no delete suggestion without explicit ask |
| 9.2 | Universal proposed-change confirmation | (B10) | every mutation shows preview first |

---

## Working agreement

- **TDD**: each step starts with a failing test, ends with a passing one
- **Commit-sized**: each step = one commit with a clean message (`fix(ci): ...`, `feat(undo): ...`)
- **No silent fixes**: every change links to the finding it resolves
- **Docs stay truthful**: README and docs/ updated in the same commit as behavior changes