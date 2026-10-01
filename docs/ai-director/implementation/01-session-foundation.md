# 01 — Session foundation: implementation evidence

Implemented and verified locally on 2026-09-12. This record covers work package 01 only; see the [work-package manifest](../work-packages.json) for current delivery status and evidence for subsequent packages.

## User outcome

Open `http://127.0.0.1:8768/director.html` in the running local app. Create a production title, idea, duration and format; save, revise, close and reopen it. Sessions survive a page reload and an application restart. The separate **Run offline example** action exercises the future state sequence with fixtures, clearly stating that no AI, media or robot was used.

The updated server currently uses port 8768 because automatic approval review blocked restarting the older server on 8766. The browser tabs now point to the updated app. The production database is `data/director/sessions.sqlite3`, independent of the port. Browser testing used a separate `data/verification/director-ui.sqlite3` on port 8767 so verification briefs do not appear as the user's productions.

To start after leaving the coding session, invoke `C:\TakeOne\scripts\TakeOne.ps1 -Command simulator -Port 8768` and open `/director.html`. It needs the existing root environment and web dependency, but no coding agent or paid model connection. A duplicate server on the same port will fail explicitly; choose another port or stop the app you started. No hardware connection occurs on startup.

## Implemented boundaries

| Responsibility | Before | After |
|---|---|---|
| Director domain and request identity | Design documents only | `packages/takeone/director/contracts.py`: typed immutable briefs, time intervals, shot references, evidence, session state and scoped commands |
| Authoritative session transitions | No runtime owner | `director/service.py`: one transactional owner, transition table, operation receipts, expiry, revisions, cancellation and restart reconciliation |
| Durable sessions and events | None | `director/repository.py`: SQLite state, events, operation receipts and job intent/results |
| Capability reporting | Distributed configuration/evidence | `director/capabilities.py`: read-only snapshot with explicit unavailable integrations and physical blockers |
| HTTP surface | Simulator models and compilation | `director/api.py` called by `apps/rehearsal/server.py`; original simulator routes retained |
| User workflow | 3D rehearsal only | Authored `director.html`, `director.css`, `director.js`, and `director-client.js`; linked from rehearsal |
| Offline example | No session demonstration | `director/demo.py`: fixture-only state sequence, without provider/device calls |
| Verification | Existing motion/runtime tests | 19 Director domain tests, 5 HTTP tests and 3 browser-client tests, plus actual UI exercise |

The Director package has no dependency on the app, serial transport, LeRobot, MuJoCo or a cloud SDK. The existing app still imports the simulator to serve previews. `demo.py` is an explicitly selected scenario; missing integrations never switch to it automatically. No separate agent framework, model training environment, generic plugin system or compatibility path was introduced.

Existing product source before this work is recoverable from commit `8e3bf62abd90f9789224e503fe0e101fcf56c56e`. An intermediate Director implementation was checkpointed as `c07c7ea` while this work was in progress. Source changes remain reviewable against those commits. Recover individual files after comparing the working tree; do not reset the workspace or discard later user changes. Existing authored simulator assets and calibration evidence remain in place.

## State and crash behavior

Requests carry operation ID, runtime epoch, expiry, expected session revision, cancellation generation, take ID and plan ID. Nanosecond timestamps cross JSON as decimal strings so the browser does not lose precision. A runtime epoch prevents comparison against a different runtime's clock. The deadline window is 15 seconds for this local session interface, separate from the cart's 60 ms firmware watchdog.

Each mutation acquires a SQLite write transaction and verifies runtime ownership. State, associated event, job intent and operation receipt commit together. Exact operation replay returns the stored result without another mutation, including after a restart; conflicting reuse of an operation ID is rejected. Accepted revisions or cancellation invalidate the old scope. Results for a different job, take, plan, session or epoch cannot advance the current session.

Starting a new owner marks unfinished jobs as requiring reconciliation and faults their sessions. It does not repeat a recording command or claim that an external device stopped. Older owners cannot continue writing after ownership changes. The HTTP API does not expose the internal job-completion method.

Only saved-brief editing and cancellation are enabled for ordinary productions in this package. The fixture mode exercises planning, preview, rehearsal, readiness, start acknowledgement, recording, finalization, review, acceptance and editing. Fixture completions retain their evidence source and `real_media_verified: false`. Actual recording would require an adapter and verified finalized media in package 06; these test states are not evidence that such an adapter exists.

The browser stores the pending operation before sending it. If delivery becomes uncertain, it blocks another mutation and offers an explicit retry with the same identity. It does not fabricate success or retry with a fresh identity. Confirmed errors are displayed; confirmed saves whose refresh fails remain described as saved.

## Verification completed

The required root command was invoked from `C:\Users\caesa`, outside the project. Final result: **all seven verification commands exit 0**.

| Check | Result |
|---|---|
| Product Python tests | 76 passed, including 24 Director domain/HTTP tests |
| Simulation Python tests | 26 passed |
| Web/client/GLB tests | 12 passed, including 3 new Director client tests |
| Browser JavaScript syntax | Passed |
| Calibration/LeRobot integrity | Passed; 1,092 LeRobot files checked against the preserved inventory |
| Root Ruff lint and format checks | Passed |
| Whitespace/diff check | Passed |

Evidence is in `data/verification/summary.json`, `check-0.txt` through `check-6.txt`, and `root-verification.txt`. Those generated runtime logs are deliberately ignored by version control. The automated tests include real temporary SQLite transactions, concurrent submissions, restart recovery, transaction rollback through an injected SQLite failure, duplicate/conflicting operation identities, stale/cancelled results, recording-stage gates, exact browser timestamp serialization, and real loopback HTTP requests. Camera discovery and motor I/O are not used.

The actual browser workflow on the verification database was: create a 12-second idea (revision 0), revise it to 15 seconds (revision 1), reload, close it (revision 2), reopen it (revision 3), restart the server, and recover the same idea/revision. The explicit example then completed at revision 13 with five fixture jobs and no real media. The navigation layout and stage indicator were visually checked and corrected. The final app on 8768 was verified with an empty production store and working links to the corrected simulator.

The related [wheel correction](../../wheel-layout-correction-2026-09-12.md) was also tested because it was separately requested in the same task. It does not expand the AI Director implementation beyond package 01.

## Limits and next step

This is a loopback, single-user foundation. Lists currently expose the most recent 100 sessions/events/jobs; all records remain stored. There is no cloud synchronization, authentication, media store, automatic retention cleanup or multi-user collaboration yet. SQLite schema version 1 has no upgrade migration because this is the first implemented schema. No latency distribution or hardware performance claim is made.

The current simulator remains a separate parameter-driven preview. Typing an idea into the Director does **not** generate a script or change the 3D scene yet. Capability cards state that limitation. Existing motor commands, polarity configuration, watchdog budget, calibration and physical qualification were not altered by the Director work.

Next is [02 — Creative planning](../prompts/02-creative-planning.md), using the [shared engineering prompt](../../requests/ASTRA-ENGINEERING-PROMPT.md). Package 02 must produce a validated creative brief/script and dialogue suggestions through a selected provider boundary. It must not add live motor control or quietly substitute a demo when provider access is missing. Packages 03–11 remain in the dependency plan.
