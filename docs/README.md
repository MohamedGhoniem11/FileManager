# FileManager — Story Map (docs/)

> This folder is the **interview artifact**. It tells one story: how a working-but-broken file organiser was audited honestly, understood deeply, and upgraded with agentic AI patterns — the same patterns proven in a multi-agent hackathon project.

## The Three-Act Arc

```
ACT 1: The Origin    Download Organizer (idea doc) → FileManager Pro (this repo)
ACT 2: The Discovery War Room hackathon → agentic AI skills (5 agents, Band SDK, confidence scoring, human-in-the-loop)
ACT 3: The Upgrade   FileManager + agent patterns = "Agentic FileManager" (File Council architecture)
```

## The Docs

| Doc | What it is | Read it to see |
|---|---|---|
| [00-origin.md](00-origin.md) | Where this project came from | The honest origin story: idea → tool → hackathon |
| [01-audit.md](01-audit.md) | Old System Audit (the truth) | Real bugs with file:line evidence, verified two ways |
| [02-old-vs-new.md](02-old-vs-new.md) | The Transformation Pitch | Why the old way was limited, what the new way does |
| [03-agentic-architecture.md](03-agentic-architecture.md) | File Council design | How War Room agent patterns map onto file management |
| [04-ease-of-life.md](04-ease-of-life.md) | Feature list | What's added and why it matters to a real user |
| [05-roadmap.md](05-roadmap.md) | Phased implementation plan | Testable milestones, one demonstrable idea per commit |
| [06-demo-script.md](06-demo-script.md) | Screen recording guide | The ~20 min interview demo, engineered shot-by-shot |
| [decisions/](decisions/) | ADR-001..009 (existing) + ADR-010..015 (new) | The engineering decisions, none made by vibes |

## Two Repos, One Story

- [`MohamedGhoniem11/FileManager`](https://github.com/MohamedGhoniem11/FileManager) — this repo, the upgrade target
- `The War Room` (hackathon, archived in vault) — where the agent patterns came from

The git history of this repo is part of the story: `docs(audit)` → `docs(architecture)` → implementation. Each commit is one demonstrable idea.

---

## Reading order for an interview setting

1. `01-audit.md` — establish that the criticism is evidence-based, not taste-based
2. `02-old-vs-new.md` — the emotional arc ("this thing did X badly, now it does Y")
3. `03-agentic-architecture.md` — the thinking (this is the "are you actually good" test)
4. `04-ease-of-life.md` + `05-roadmap.md` — the product sense + the plan
5. `06-demo-script.md` — the proof you can communicate it