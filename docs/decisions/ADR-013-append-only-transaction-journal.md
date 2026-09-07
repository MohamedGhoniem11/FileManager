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