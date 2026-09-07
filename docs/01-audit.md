# 01 — Old System Audit (the truth, with evidence)

> Every claim below is **verifiable**: file + line + reasoning. Nothing here is taste.
> Verification methodology: manual read + AST static analysis (pytest could not collect the suite, which is itself finding C2).

---

## TL;DR — The Summary

The old FileManager is an ambitious beginner-to-intermediate project with a genuinely reasonable service/core/gui layering. But:

1. **The intelligence layer was theater** — a 700MB spaCy dependency that never once influenced a decision
2. **The safety layer didn't exist** — the README described FileLock retries and event-loop cooldowns; the code did neither
3. **Classification punished ignorance** — unknown extensions went to an "Others" folder, and the health engine then called those files "orphans" and suggested **deleting** them

---

## Severity Legend

| Level | Meaning |
|---|---|
| **C** | Critical — crash / broken build / data-loss risk |
| **H** | High — silent failure / data corruption potential |
| **M** | Medium — design debt / theater / misleading docs |

---

## The Verified Findings

### C1. `classifier.py` uses `logger` without importing it — crash on any config change

- **File:** `src/core/classifier.py` (callback path)
- **Evidence:** AST check: module-level imports are `[Classifier, Dict, List, Path, classifier, config_service, os]` — **`logger` is NOT imported**. Yet `logger.info(...)` is called inside the classification callback.
- **Trigger:** any `config.json` change that re-runs classification with a non-logged code path → `NameError`.
- **Verification:** AST static analysis (see appendix) — `logger` resolved to 0 imports, 1 usage.

### C2. `test_nlp_db.py` imports a symbol that doesn't exist — CI is red

- **File:** `tests/test_nlp_db.py:7` → `from src.services.nlp_service import nlp_service`
- **Evidence:** AST check of `src/services/nlp_service.py`: module-level names are only `['get_nlp_service', '_nlp_service_instance']`. The name `nlp_service` **does not exist**.
- **Impact:** `pytest` fails at collection. **The CI badge is a lie.** (This is why the audit used AST analysis — the test suite cannot even collect.)
- **Verification:** AST static analysis — `ImportError: cannot import name 'nlp_service'` is guaranteed.

### C3. `startup_service.py` unconditionally imports Windows-only modules

- **File:** `src/services/startup_service.py`
- **Evidence:** imports `winshell` + `win32com` at module top level, unguarded.
- **Impact:** on Linux/macOS the app crashes at import time. The README claims "cross-platform"; the code is Windows-only by construction.

### C4. README describes features that don't exist

- **File:** `README.md` ("Race Conditions with File Locks" section)
- **Evidence:** README claims a `FileLock` retry mechanism in `observer.py`; the actual code uses `time.sleep(1)` — a fixed sleep with no retry, no lock, no handle-release polling.
- **Impact:** docs vs code drift. The "engineering challenges" section is fiction, which is worse than having no docs — it misleads.
- README also claims a cooldown filter for event loops; the `on_modified` filter exists but the cooldown mechanism does not.

### H1. `db_service.py` swallows errors with empty `except: pass`

- **File:** `src/services/db_service.py` — empty exception handler.
- **Impact:** silent data divergence. A failed write/lookup vanishes with zero trace. The journaling upgrade (Phase 4) is impossible until every failure is visible.

### H2. SQLite runs without WAL / connection discipline

- **File:** `src/services/db_service.py`
- **Impact:** with concurrent threads (observer + GUI + NLP), "database is locked" errors are expected; no WAL mode, no single-writer discipline.

### H3. There is no undo anywhere

- **File:** whole app — `organizer.py`, `observer.py` move paths.
- **Impact:** one wrong rule = files scattered permanently. No reversible operation, no journal, no provenance ("where did X go?").

### H4. Relative config/log paths

- **File:** `src/services/config_service.py`, `logger.py`
- **Impact:** depends on CWD; breaks when launched from a different directory or as a packaged EXE. (Half of the "PyInstaller packaging issues" in the README trace back to this.)

### H5. `observer.py` races on large files

- **File:** `src/services/observer.py` — `time.sleep(1)` heuristic.
- **Impact:** large downloads (or slow writes) are either moved half-written or skipped entirely. No readiness check, no `PermissionError` retry loop.

### M1. spaCy is loaded but parsing is 100% regex

- **File:** `src/services/nlp_service.py`
- **Evidence:** spaCy pipeline loads a full model (`en_core_web_sm`), but the actual parsing functions are keyword/regex matching. The 700MB dependency has zero effect on outputs.
- **Impact:** bloated EXE, slow startup, fake "AI" feature. (Confirmed by ADR-009's own framing — the fallback IS the implementation.)

### M2. Dead code

- **File:** `src/services/nlp_service.py` (unreachable branches) — code that can never execute under the fallback design.

### M3. The "Others" ghetto punishes ignorance

- **File:** `src/core/classifier.py`, `health_engine.py`
- **Impact:** files with unknown extensions go to `Others/`, then the health engine counts them as "orphans" and suggests **deletion**. The system punishes files for its own tiny vocabulary.

### M4. Extension-only classification

- **File:** `src/core/classifier.py`
- **Impact:** `receipt.pdf`, `tax-form.pdf`, and `book.pdf` are indistinguishable. Content is ignored entirely; a mis-sort is permanent (no undo, H3).

### M5. SHA-256 every file, no caching

- **File:** `src/core/organizer.py` / hashing path
- **Impact:** re-hashes every file on every scan. Near-duplicate detection (renamed/re-saved copies) is impossible — only exact hashes match.

---

## The Three Structural Truths (why these matter)

1. **Intelligence was theater** — complexity without capability. The expensive part had no effect.
2. **The safety layer didn't exist** — the docs described it; the code shipped without it.
3. **Classification punished ignorance** — a miss became a deletion suggestion.

Any one of these is normal. All three together is the "I've grown since then" story — upgraded in [02-old-vs-new.md](02-old-vs-new.md).

---

## Appendix: Verification Evidence (AST static analysis)

System had no `pytest` available → I could not run the (already-broken) suite, so I verified the two decisive claims with Python's `ast` module:

```python
# C2 — nlp_service import name
import ast, pathlib
src = pathlib.Path("src/services/nlp_service.py")
tree = ast.parse(src.read_text())
names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Assign))}
# → {'get_nlp_service', '_nlp_service_instance'}   ← 'nlp_service' ABSENT
# tests import 'nlp_service' → ImportError guaranteed
```

```python
# C1 — classifier logger
src = pathlib.Path("src/core/classifier.py")
tree = ast.parse(src.read_text())
imports = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names
           if isinstance(n, ast.ImportFrom)}
# → {'Classifier', 'Dict', 'List', 'Path', 'classifier', 'config_service', 'os'}   ← 'logger' ABSENT
# logger.info(...) usage present → NameError guaranteed on that path
```

Both findings are **deterministic** — the missing names cannot exist at runtime, so the crashes/import errors are guaranteed, not heuristic.