# ADR-016: Safe Journal-Backed Undo (Reverse Replay)

## Status
Accepted

## Context
ADR-013 built the append-only transaction journal and set the direction: "undo = reverse replay of committed entries in FIFO order." Audit finding H3 is fully closed only when that replay exists, is safe, and answers "where did X go?" Roadmap Step 3 (3.1 undo, 3.2 provenance) is the first consumer.

Naive replay is dangerous. Undoing a move that was followed by external edits, a crash, or another move can silently destroy newer data. Production file managers keep undo in-memory and lose it on restart — ours is persisted, so it must be *at least as* conservative as an in-memory stack in every case where the world changed underneath us.

## Decision
`Organizer.undo_last(count)` reverse-replays the newest committed moves (LIFO: the most recent move is undone first), and `DbService.journal_provenance(path)` answers "where did X go?" per path.

Undo only touches entries that pass **every** gate:

1. **status == `committed`** — pending entries were never executed; reversed entries were already undone; both are skipped.
2. **`reversible == 1`** — overwrites destroyed pre-existing content (ADR-013), their inverse is unsafe; they are skipped.
3. **`op_type == 'rename'`** — copy+delete and trash need different inverses (recopy / restore-from-trash); those are future work, not guessed.
4. **Dest still exists** — nothing to move back if the file was deleted afterwards.
5. **Source is free** — undo never clobbers a newer file that appeared at the original location.
6. **Inode still matches** — if the file at dest is no longer the file we moved (replaced/moved externally), undo refuses.

Success marks the entry `reversed` with `reversed_at`; the journal stays append-only (triggers from ADR-013 still protect it). Failed candidates are logged as warnings with the entry id and are left `committed` — undo reports the **count of successfully reversed entries only**, never a silent partial story.

## Alternatives Considered
- **Undo everything (ignore the gates):** literally the data-loss paths documented in ADR-013's validation research (Zed #48697, tine #305). Rejected.
- **In-memory undo stack:** loses history on restart, no provenance. Rejected — ADR-013 already chose persistence.
- **Undo only reversible-from-dest:** skipping the inode check speeds the happy path but would move a *different* file into the old path on in-place replacement. Rejected — inode check is one `stat()`.

## Rationale
The journal's whole point is that a move is a transaction: *pending → committed → reversed*. Undo is the committed→reversed transition, and it must be the exact inverse of the recorded action against the same file. The six gates make "undo" refuse loudly instead of corrupting quietly — consistent with the project's surface-don't-punish principle.

## Consequences
- **Benefits:** H3 closed end-to-end; undo survives restarts; "where did X go?" is a one-query answer; the demo script now has a real, provable safety story.
- **Limitations:** Only single-move renames are undoable today (copy+delete, trash, and batch multi-file ops need their own inverses — future steps); undo requires the journal to be intact (pruning policy still pending, per ADR-013).