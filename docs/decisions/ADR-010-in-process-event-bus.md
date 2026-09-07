# ADR-010: In-Process Event Bus over Network Bus

## Status
Accepted

## Context
The agentic upgrade introduces multiple agents (Analyzer, Classifier, Dedup, Rules, Corrector) that must coordinate. The War Room hackathon project used a network event bus (Band SDK channels) where agents ran as separate processes. FileManager is a single desktop application; agents running as separate processes would add orchestration overhead, serialization complexity, and process lifecycle management with no user-visible benefit.

## Decision
Use an in-process typed event bus (observer/subscriber pattern) with named channels matching the War Room channel topology (`file-events`, `analysis-results`, `proposals`, `deliberation`, `verdicts`, `corrections`). Agents remain Python objects coordinated by the Commander; the channel abstraction is preserved so the topology is identical to a networked design.

## Alternatives Considered
- **Network bus (Band SDK, multi-process)**:
  - Pros: Matches hackathon directly; scale-ready.
  - Cons: Overhead for a desktop tool; process management; harder packaging.
- **Direct method calls (no bus)**:
  - Pros: Simplest.
  - Cons: Couples agents; no "channels" story for the interview; harder to trace events.

## Rationale
The value is the coordination *pattern*, not the transport. An in-process bus keeps the architecture honest ("agents talk over typed channels") while remaining a single installable desktop app. It also enables the evidence-journaling story: every event passing through the bus can be recorded.

## Consequences
- **Benefits**: Simple deployment, testable bus (unit-test channel routing), preserved two-repo narrative ("same topology either way").
- **Limitations**: Not horizontally scalable; a future web/multi-process version would swap the transport without redesign.