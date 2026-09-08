# ADR-004: SQLite for Metadata Indexing

## Status
Accepted

## Context
As the file count grows and we move toward NLP-based search, querying the filesystem directly becomes too slow. We need a way to store file metadata for instant retrieval.

## Decision
Use `sqlite3` for local metadata indexing.

## Alternatives Considered
- **JSON Metadata File**:
  - Pros: Simple.
  - Cons: Becomes slow with thousands of entries; lacks relational query capabilities.
- **External Search (Elastic/Solr)**:
  - Pros: Insane scale.
  - Cons: Total overkill for a local file manager; massive dependency overhead.

## Rationale
SQLite is built into Python, requires zero server setup, and provides high-performance SQL querying. It is the perfect middle-ground for indexing thousands of files and supporting complex filters (e.g., date ranges, types).

## Consequences
- **Benefits**: Zero dependencies, relational queries, transaction safety, high performance.
- **Limitations**: Requires managing a local database file; schemas must be maintained.

## Update (2026-09-09): Implemented
SQLite metadata indexing shipped in `src/services/db_service.py`: a single
WAL-mode connection (`PRAGMA journal_mode=WAL`, busy timeout), a `files`
table with `upsert_file` / `query_files`, plus the append-only `journal` and
`fingerprints` tables. ADR-008 is the implementation record for the same
decision; this ADR is the earlier proposal that was accepted and built.
