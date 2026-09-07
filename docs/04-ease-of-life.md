# 04 — Ease-of-Life Features (what's added & why)

> Features are grouped by the pain they kill. Everything here is domain-real: it fixes a behavior a real user would actually hit.

---

## B1. The Undo Everything

One journal (SQLite): every move/rename/delete with a timestamp and reason.
- One click undoes the last N operations
- Batched undo for "that last cleanup was a mistake"
- **Interview moment:** move files, undo all of it live, show the journal rows

## B2. "Ask me when unsure" (HITL gate)

Configurable confidence threshold, per category.
- Above threshold → auto-move silently
- Below → preview window: "Move `invoice_march.pdf` to **Tax**? (58% — low evidence)"
- **Interview moment:** deliberately trigger low-confidence, show the gate

## B3. Smart Rules (visual + natural language)

- "Videos larger than 1GB → External/Hard-Drive-Cache"
- "Files older than 6 months in Downloads → Archive"
- "Anything inside `Work/` stays in `Work/`"
- Rules evaluated by the Rules Agent with dry-run preview per rule
- **Ease-of-life:** set it once; the agent applies + reports what it did

## B4. Self-Learning Corrections

Drag a file to the "wrong" place → the system learns the mapping + updates confidence.
- Logs every correction; classifier priors evolve
- **Interview moment:** misclassify on purpose, correct it, show that the next file with similar content lands correctly

## B5. Content Preview & Semantic Search

- Preview panel: PDF text, first N lines of code, image thumbnail + EXIF
- Search over *content*, not just filename:
  - "find the receipt with 'Amazon' in the text from March"
  - "show me files containing 'contract' in the last month"
- **Ease-of-life:** "where did I put that contract" becomes findable

## B6. Lifecycle / Aging Policies

- Auto-archive candidates ("not opened in 90+ days")
- Folder threshold alerts ("Downloads is over 5GB")
- Scheduled runs (the TODO's `max_folder_files` finally real)

## B7. Multi-Location Monitoring

- Watch Downloads + Desktop + Documents simultaneously
- Per-location rules and categories

## B8. Cross-Platform

- Guard Windows-only imports, use `platformdirs` for config/log homes
- Installable on Windows/Linux/macOS; the interview can run it on ANY machine

## B9. Health Audit 2.0

- Old: found duplicates/empties, suggested delete
- New: *explains* each finding + proposes a safe action with undo + asks before deleting anything you didn't explicitly request

## B10. Assistant That Actually Assists

- Replace regex theater with real intent parsing (small LLM or solid rules engine — decision recorded in [ADR-011](decisions/ADR-011-nlp-classification-engine.md))
- Actions always show a proposed change + confirmation (already the chat pattern; make it universal)

---

## Why these matter (accessibility / ease-of-life lens)

| Persona | Pain today | Solved by |
|---|---|---|
| Student | Downloads is chaos; "I have no idea where that file went" | content preview, semantic search, undo |
| Professional | "I deleted/sorted the wrong thing and can't undo" | Undo Everything + HITL gate |
| Developer | "I want rules, not babysitting" | Smart Rules + scheduled lifecycle |
| Any user | "It moved files wrong and got worse over time" | self-learning corrections |