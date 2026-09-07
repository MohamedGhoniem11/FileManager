# ADR-012: Near-Duplicate Detection via Perceptual + Normalized-Text Fingerprints

## Status
Accepted

## Context
Old duplicate detection hashed every file with SHA-256 (audit M5). It only catches byte-identical copies. Real duplicates are usually *near* duplicates: the same document re-saved (different bytes), renamed, converted, or a screenshot re-exported. The Dedup Agent needs to cluster these.

## Decision
Compute **typed fingerprints** per file:
- Images: perceptual hash (`dhash` → Hamming distance threshold)
- Documents/text/code: normalized-text + `simhash` (tokenize → normalize case/whitespace → hash → Hamming distance)
- Binaries/other: SHA-256 fallback (exact only)
Store fingerprints in the journal/SQLite with incremental computation (fingerprint cached, recomputed only when size+mtime change — fixing M5's re-hash-everything).

## Alternatives Considered
- **SHA-256 only (status quo)**:
  - Pros: Trivial.
  - Cons: Misses renamed/re-saved/converted files → duplicate clusters wrong.
- **Full `ssdeep` fuzzy hashing for everything**:
  - Pros: Strong for similar binaries.
  - Cons: Overkill and slow at scale; poor for text where simhash is better.

## Rationale
Per-type fingerprints match how files actually duplicate in practice. Incremental caching removes the old "hash everything every scan" cost. Hamming-distance thresholds give the confidence score a concrete input ("88% similar to Tax/invoice-2024-03.pdf").

## Consequences
- **Benefits**: Real duplicate clusters (renamed/re-saved caught), fast scans, confidence contribution for the Commander.
- **Limitations**: Thresholds need tuning per type; perceptual hashes fail on heavy image edits (acceptable — those aren't "duplicates" to users anyway).