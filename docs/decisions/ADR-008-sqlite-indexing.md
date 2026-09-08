# ADR-008: SQLite for Metadata Indexing

## Status
Accepted

## Context
The application needs to support complex "time-aware" and "size-aware" searches (e.g., "files from last week"). Real-time monitoring only provides events, not a queryable history.

## Decision
Use SQLite as a lightweight persistent index for file metadata.

## Alternatives Considered
- **In-Memory JSON**:
  - Pros: Simple.
  - Cons: High RAM usage for large directories; persistence is slow (rewrite whole file).
- **Elasticsearch/Lucene**:
  - Pros: Powerful search.
  - Cons: Total overkill; massive dependency footprint.

## Rationale
SQLite is built-in to Python, serverless, and extremely efficient at querying relational data. It allows the NLP engine to translate user intent into standard SQL queries without scanning the disk every time.

## Consequences
- **Benefits**: Near-instant search responses, decoupled from actual disk I/O.
- **Limitations**: Database and disk can occasionally drift if manual changes happen while the app is off; mitigated by 'Initial Sync'.

## Update (2026-09-09): Implementation record
This is the implementation record for SQLite indexing (ADR-004 is the
earlier proposal for the same decision). Live in `src/services/db_service.py`:
WAL mode, a `files` table with `upsert_file` (INSERT OR REPLACE) and
`query_files` (filename/extension/category/size/date filters), plus the
append-only `journal` and `fingerprints` tables. Initial Sync populates the
index from the watched locations.
