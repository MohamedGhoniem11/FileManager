# 06 — Demo Script: Screen Recording Guide for Interviews

> A recording walkthrough that tells the "old → diagnosis → upgrade" story in ~20 minutes, with every claim shown on screen.
>
> **Recording status (as of Step 2):** Videos 1, 2 and 4 are recordable **now**. Video 3's File Council segment (confidence scoring, human gate, learning) describes roadmap **Steps 3–6, which are not built yet** — record the "Safety Layer groundwork" variant below today (it shows what exists), and re-record Video 3 once Step 6 lands. Every claim must be on screen; nothing here may be staged.

---

## 0. Recording Ground Rules

- **Split into 4 short videos** (easier to re-record one take than redo 20 min)
- Every claim = shown evidence (file:line, screenshot, live run)
- Record in the **same terminal/cwd each time** (background consistency signals care)
- Voice: narrate the *why*, not the *what*. "I'm fixing this because the test suite can't even collect — that means CI is meaningless" ≫ "I'm fixing a test import"
- `recording.txt` in the repo root lists the 4 videos + key timestamps

---

## Video 1 — "I Wrote This" (War Room, ~4 min)

**Goal:** establish agentic credibility + the skills that will be reused.

| Time | Action on screen | Script beat |
|---|---|---|
| 0:00 | Open The War Room repo, README architecture diagram | "In the Band of Agents hackathon I built a multi-agent incident response platform." |
| 0:30 | `bank` → agents/ tree (commander + 4 specialists) | "Five agents — LangGraph commander, CrewAI/Pydantic AI/Anthropic/Claude specialists, on a shared event bus." |
| 1:00 | Open `lib/scorer.py` — show weights | "The killer feature: agents don't just answer, they score their confidence. 25% metrics, 25% logs..." |
| 1:40 | Show AGREE/CHALLENGE protocol (docs/architecture.md deliberation table) | "They don't just report — they challenge each other. An unresolved challenge docks confidence." |
| 2:20 | Open `lib/remediation.py` + git_ops | "And nothing runs unsupervised: human-in-the-loop remediation, plus auto-committed postmortems." |
| 3:30 | Wrap | "That's the toolkit. Now let's point it at an older project of mine — and be honest about what it was." |

**Skill tags to drop (verbally):** LangGraph orchestration, multi-framework interop, confidence scoring, HITL, event bus, Git-Ops artifacts.

---

## Video 2 — "The Honest Audit" (~5 min)

**Goal:** show diagnosis-is-the-impressive-skill. Old system, evidence-first.

| Time | Action on screen | Script beat |
|---|---|---|
| 0:00 | Open FileManager repo, run `pytest --collect-only` for real | "First thing I noticed: the CI is red. A test imports a symbol the module never defines. Let me prove it — not just read it." |
| 0:40 | Show the AST check output (module-level names vs the import) | "`nlp_service` doesn't exist in nlp_service.py. The test suite can't even collect. CI is a lie until this is fixed." |
| 1:20 | Open `classifier.py` — point at `logger.info` with no import | "Second: config changes crash a background thread. `logger` is used but never imported — NameError the moment anyone edits config.json." |
| 2:00 | Open README claims vs `observer.py` (`time.sleep(1)`) | "The README brags about a file-lock retry system. The code sleeps for a second and hopes. Docs said one thing, code did another." |
| 2:40 | Show spaCy load + regex parse (nlp_service.py) | "The expensive part: a 700MB NLP stack that never influences a single decision. All parsing is keyword regex." |
| 3:20 | Show the severity table (C1-C4 / H1-H5 / M1-M5) | "I classified every finding by impact × blast radius — crashes, data risk, then architecture debt. Not by taste." |
| 4:00 | The three truths | "Intelligence is theater. The safety layer doesn't exist. And it *punishes* files it fails to classify — 'Others' becomes 'orphans' becomes 'delete me'." |
| 4:40 | Wrap | "That's not a bad beginner project — that's a *normal* one. My job was to find the real faults, not the obvious ones." |

**Skill tags:** evidence-based review, AST static analysis, docs-vs-code drift, severity taxonomy, reading tests as intent.

---

## Video 3 — "The Agentic Upgrade" (~8 min) — THE MONEY SHOT

> **⏳ Recordable TODAY (Steps 1–2 only):** replace the File Council beats below with the **"safety layer groundwork"** variant:
> 1. Run `python demo/reset_state.py` first — fresh config + DB + journal for the take.
> 2. `python demo/make_samples.py` → `demo/scratch-downloads/` with the receipt PDF + near-dup images + opaque file.
> 3. Point the app at that scratch folder, drop `invoice_amazon_march.pdf` in it, watch it classify and move.
> 4. `sqlite3 ~/.local/share/FileManager/metadata.db "SELECT * FROM journal;"` — show the committed row (op_type, source, dest). That's write-before-action journaling in action.
> 5. Try `DELETE FROM journal;` — show the DB-level trigger refusing it (append-only enforced by the database itself).
> 6. Show `docs/05-roadmap.md` Step 3: undo replay is the next milestone — this is its foundation.
>
> The full File Council sequence below (0:00–7:00) is **recordable only after Steps 3–6**:

**Goal:** the File Council demo. This is the "look how cool" reel.

| Time | Action on screen | Script beat |
|---|---|---|
| 0:00 | Open architecture: Commander + 5 agents diagram | "Instead of extension→folder, files now go through a deliberation. Let me show you." |
| 0:30 | Put a fake `invoice_amazon_march.pdf` in the watch folder | "Watch what happens with a file that's *obviously* a receipt, not just 'a PDF'." |
| 1:00 | Watch Analyzer extract text → Classifier proposes "Tax, 0.92" | "The Analyzer reads inside — PDF text, image metadata. The Classifier proposes with a *confidence score*, not a bucket." |
| 1:40 | Show Dedup + Rules corroborating, confidence rises | "Agreement raises the score — the same AGREE protocol from the War Room." |
| 2:20 | File moves to Tax/, journal row appears | "Above 0.80 it moves and journals itself. One click = undo. Let's prove it." |
| 2:50 | Click UNDO → file returns → journal shows `reversed` | "Every move is a transaction. This is the part the old system simply didn't have." |
| 3:40 | Feed a low-confidence file (e.g., an unclear month invoice) | "Now watch a hard one — the Analyzer struggles, so the score is 0.58. Below threshold." |
| 4:20 | Human gate pops: "Move to Tax? (58%)" → confirm | "It *asks* instead of guessing. This is the HITL gate from my remediation engine." |
| 5:00 | Drag the mis-classified file to the right folder | "And the part I'm proudest of: it learns. I correct it once —" |
| 5:30 | Feed a *similar* file; it lands correctly now | "— and the priors update. Misses become lessons, not deletes." |
| 6:00 | Show test suite green + coverage % | "And it's tested: green suite, TDD'd. Confidence scoring is unit-tested, the gates are tested, the journal is tested." |
| 7:00 | Wrap | "Same codebase I showed you in Video 2 — agentic judgment layer on top, safety layer underneath. Not a rewrite." |

**Skill tags:** multi-agent orchestration, confidence scoring, HITL, transaction/journal design, self-learning, TDD.

---

## Video 4 — "The Result & The Lessons" (~3 min)

| Time | Action on screen | Script beat |
|---|---|---|
| 0:00 | Before/after table (audit → fixed) | "Engineering is a loop: diagnose, design, build, measure, repeat. This is the before/after." |
| 0:40 | `git log --oneline` showing the commit journey | "The git history shows the upgrade path — fix CI, add journal, add agents, add tests. Each commit is a single demonstrable idea." |
| 1:20 | Q&A cheat-sheet moment | "If you ask why agents — it's sorting, but it's really *judgment*: near-duplicates, receipts vs reports, learning from corrections. That's the part rules engines can't do." |
| 2:00 | Close | "Best lesson from this: the hard part wasn't the AI — it's the safety. An agent that moves files wrong is worse than a dumb tool that's predictable. So I built the safety first." |

---

## Checklist before recording

- [ ] `pytest` genuinely green + coverage command output visible
- [ ] AST verification snippet ready to re-run live (Video 2) — see [audit appendix](01-audit.md)
- [ ] `python demo/reset_state.py` run — fresh config + DB + journal for this take
- [ ] `python demo/make_samples.py` — generated `demo/scratch-downloads/` (receipt PDF, near-dup images, opaque file)
- [ ] App pointed at `demo/scratch-downloads` as the watch folder (never the real Downloads)
- [ ] Terminal theme + monospace font consistent across videos
- [ ] `recording.txt` in repo root with timestamps

## Anti-disaster rules

- **Rehearse once fully, unrecorded** — the demo MUST not show you improvising the file paths
- Have a **fresh config + DB + journal** state for each take (or a reset script `demo/reset_state.py`)
- If you flub a take: stop, re-record THAT video, don't splice
- Record audio check + screen-size check (1080p+, readable terminal font ~16pt+)
- **Kill notifications** — a WhatsApp popup on a confidence scoring slide is how demos die