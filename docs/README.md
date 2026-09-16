# FileManager — Engineering Documentation

> How this project got to where it is: the honest audit of the original system, the
> transformation, the agentic architecture, and the decisions behind every change.

## The Docs

| Doc | What it is |
|---|---|
| [00-origin.md](00-origin.md) | Project history: idea → tool → agentic upgrade |
| [01-audit.md](01-audit.md) | Audit of the old system — real bugs with file:line evidence |
| [02-old-vs-new.md](02-old-vs-new.md) | The transformation: what changed and why |
| [03-agentic-architecture.md](03-agentic-architecture.md) | The "File Council" design — agents, scoring, gates |
| [04-ease-of-life.md](04-ease-of-life.md) | User-facing features and the pain they solve |
| [05-roadmap.md](05-roadmap.md) | Phased implementation plan with verification per step |
| [07-ai-integration.md](07-ai-integration.md) | Local LLM + Agentic RAG design (qwen3 + nomic-embed-text) |
| [decisions/](decisions/) | ADR-001..017 — the engineering decisions, evidence-first |

---

## Suggested reading order

1. `01-audit.md` — the criticism is evidence-based, not taste-based
2. `02-old-vs-new.md` — the transformation arc
3. `03-agentic-architecture.md` — how the design actually works
4. `04-ease-of-life.md` + `05-roadmap.md` — the product sense + the plan
5. `07-ai-integration.md` — the current assistant design