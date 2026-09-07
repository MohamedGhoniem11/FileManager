# ADR-013: Append-Only Transaction Journal (SQLite, Versioned)

## Status
Accepted

## Context
The old system had no undo and no provenance anywhere (audit H3): one wrong rule scattered files permanently. The upgrade's safety story (Undo Everything, "where did X go?") requires a durable record of every filesystem mutation, crash-safe, and queryable.

## Decision
Maintain a **strict append-only journal** in SQLite:
- Every mutation (move/rename/delete/copy) writes a journal entry **before** the action executes; the entry is marked `pending → committed → reversed`.
- Journal schema is versioned (schema_version table) with a migration path (fixing the missing config-schema pattern generally — H4/F9).
- SQLite opened in **WAL mode with single-connection discipline** (fixing H2).
- Undo = reverse replay of committed entries in FIFO order; reversible flag per action type.

## Alternatives Considered
- **In-memory undo stack**:
  - Pros: Simple.
  - Cons: Lost on restart → "undo" useless after a crash; no provenance over time.
- **Filesystem-level versioning (hardlinks/snapshots)**:
  - Pros: Powerful.
  - Cons: Platform-specific, heavy, overkill for a file sorter.
- **Plain log file (JSONL)**:
  - Pros: Simple, human-readable.
  - Cons: No atomic transactions, no migration story, weak querying.

## Rationale
SQLite gives atomicity (journal-before-action is crash-safe), WAL gives concurrency without locks, and append-only gives a clean provenance history. It mirrors the War Room evidence-trail philosophy: "every action is traceable."

## Consequences
- **Benefits**: Undo exists and survives crashes; "where did X go" queryable; audit trail for the interview demo; fixes H2/H3 in one decision.
- **Limitations**: Disk growth over time (add pruning policy later); every mutation has a write cost (acceptable at desktop scale).

## Update (2026-09-07): Validation against real undo systems
Research verified the design and added three hardening rules:
1. **Pre-undo state validation** — record per-file `mtime + size` at journal time; before replaying an inverse op, verify the target still matches. Undo-after-external-change is a documented data-loss path (Zed #48697, tine #305); silent overwrite is unacceptable.
2. **Never hard-delete — delegate to OS trash** — use `send2trash` (or equivalent) for deletes so the journal's inverse is "restore from trash", not "recreate from nothing".
3. **Track operation type + inode** — cross-device `EXDEV` moves fall back to copy+delete (non-atomic); hardlinks share inodes. Naive reverse replay breaks on both. Journal stores `op_type` (rename/copy+delete/trash) and records inode, so undo re-copies instead of renames when needed.
   Production file managers (Dolphin KIO::FileUndoManager, Nautilus) keep undo **in-memory only** — our persisted journal is deliberately stronger, which is the right call for unattended batch operations (with checkpoint compaction to bound growth, per oplog-undo's `compact()` pattern).