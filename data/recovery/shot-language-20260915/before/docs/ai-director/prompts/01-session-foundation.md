# 01 — Director contracts and session owner

Implement work package 01 in `C:\TakeOne` as a principal software engineer. Deliver working product code and an offline demonstration, not another architecture proposal.

Read `C:\TakeOne\AGENTS.md`, the root README, `docs/architecture.md`, `docs/ai-director/README.md`, and `docs/ai-director/implementation-rules.md`. The shared rules are part of this prompt. Inspect `packages/takeone/contracts.py`, current planning/execution boundaries and the app before adding code. Dependencies: existing workspace only.

## Outcome

A user can create, inspect, revise and resume a Director session through the local app. One deterministic owner controls its state. Duplicate commands, delayed AI replies and old recording acknowledgements cannot affect a different session or take. No camera, model or motor connection is needed for this package.

## Implement

1. Add the smallest useful `packages/takeone/director` domain and application layer. Define strict versioned contracts for a production brief, capability snapshot, scene/shot references, beat/timeline intervals, proposals, observations and take/job identity. Implement fields exercised by this slice; do not create empty services for later packages. Reuse existing units and provenance rather than replacing the motion contracts.
2. Implement the session transition table from the delivery plan. All accepted transitions pass through one owner. Separate session state, provider job state, recorder acknowledgement and physical execution status. Preview availability cannot imply hardware readiness.
3. Give requests an operation ID, session/take/plan identity, expected revision, deadline and cancellation generation. Include a runtime/clock epoch so a monotonic timestamp from a previous boot is not compared as though it belonged to this boot. Make duplicate handling deterministic and stale results explicit.
4. Persist session state and its associated event atomically in SQLite through a small repository boundary. Store evidence/media references rather than media blobs. Record pending job intent and reconcile unknown completion; do not claim exactly-once execution across an uncooperative external service.
5. Expose local create/read/revise/cancel use cases in the existing app with a plain-language session summary and explicit mode. Add a fixture/replay demonstration whose label cannot be mistaken for a live model or recorder. No hidden demo fallback.
6. Report current capabilities from actual configuration/evidence, retaining unknown phone integration and physical blockers. Do not run LeRobot connect, open serial ports or modify readiness evidence.

## Acceptance

- Create a session, restart the application and recover its last committed state and revision.
- Reject an old revision, cancelled decision and result for the previous take without altering current state.
- Repeating the same operation ID does not create another take/job; conflicting reuse returns an error.
- A persistence failure cannot leave an acknowledged state change without its event.
- A simulated success remains labeled simulated; missing capability remains unavailable.
- Unit/integration tests run without network access, camera discovery side effects or hardware imports opening devices.

Complete root verification after relevant changes and verify the served session workflow. Leave `docs/ai-director/implementation/01-session-foundation.md` with evidence, changed boundaries and remaining limitations. Update only package 01 in the manifest. Do not implement later packages or add a generic multi-agent framework.
