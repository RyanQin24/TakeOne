# 02 — Creative planning

Date: 2026-09-12. Local software implemented; live provider acceptance unverified.

## Outcome

The Director now turns a saved brief into an editable production document through one of three explicit paths: a user-requested live model proposal, a manually written script, or a selected editorial sample. A sample is never substituted for a failed live request. The authored interface uses a focused idea composer, a persistent production library, and Brief / Script / Shots views. Quiet charcoal and warm paper surfaces, original SVG studies, clear typography and restrained controls replace the foundation dashboard.

The user can save audience, tone and verified facts; edit dialogue and performance cues; choose a line alternative; request shorter or differently toned alternatives; change proposed shot times, framing, actor/mark assignment, camera/light/edit intent; edit scene locations, actor names and mark descriptions; add actors, marks, shots and scenes; approve a creative revision; inspect history; and export the proposal. Unknown facts remain questions/placeholders. Proposed times are milliseconds on a media timeline, not device timestamps or a claim of executable timing.

The single live adapter targets the architecture's selected `gpt-5.6-terra` through OpenAI Responses, using strict structured output, no tools, no automatic retries and no fallback model. It records the requested/returned model, response ID, input digest, selected skill version, rig capability digest and reported token usage. The three curated skills are product presentation, dialogue coverage and reaction/eyeline, all version 1.0.0.

## Boundaries and revisions

`CreativePlanning` shares `DirectorService`'s database ownership lease, scope, expiry and idempotent receipts. It does not create a second owner. HTTP acknowledges a job without waiting for inference. Only one live planning request can occupy this runtime. A cancelled or timed-out transport retains its worker slot until it returns; later results cannot overwrite an edit or revive an approval. A deadline timer makes a stalled job visibly fail, independently of transport completion. Restart reconciliation invalidates pending work without retrying it.

Database schema 2 is additive: `creative_briefs`, `creative_revisions` and `planning_requests` are new tables. Existing sessions, events, jobs and receipts remain intact. Creative revisions are append-only. A line or shot edit increments the session revision and cancellation generation, cancels pending jobs, clears approval, and removes dependent preview/take-acceptance references. Edits are refused while recording is starting, active or finalizing. Approval means approval of the creative script; it does not approve a measured room layout or hardware motion.

`static`, `arm_pan_tilt` and `straight_dolly` still require physical solver validation. Strafe, stairs, unqualified orbit, unavailable optical zoom and other unsupported requests remain visible and block script approval until explicitly revised. The camera intent, dialogue and notes remain bounded data. They cannot execute code, call a shell, discover hardware, change calibration or send servo/motor commands. The rig-configuration fingerprint is checked again before a provider result is applied.

Fact IDs prevent references to facts that were never supplied. They do **not** prove that a model's natural-language claim is true or faithfully paraphrases a source; the user must review the dialogue. No live semantic-quality or latency result is claimed in this package.

## Connection and cost controls

Defaults in `configs/director-planning.json`:

| Control | Setting |
|---|---|
| Live planning | Disabled until explicitly enabled |
| Credential | Server process environment: `OPENAI_API_KEY` |
| Selected model | `gpt-5.6-terra` |
| Job deadline | 45 seconds |
| Output token limit | 6,000, including reasoning tokens |
| Serialized request limit | 24,000 UTF-8 bytes |
| Per-request reservation limit | USD 0.15 |
| Per-production cumulative reservation limit | USD 1.00 |
| Retries / model substitution | None |

Reservations conservatively use serialized UTF-8 bytes plus a framing allowance for input, the output-token ceiling, and configured pricing of USD 2 per million input tokens / USD 12 per million output tokens. These are application estimates, not a provider-enforced billing cap. Reservations remain consumed for failed, cancelled and timed-out requests because upstream work may already be billable. Current provider pricing and account access must be checked before enabling paid use. The browser confirms each live request and discloses what is sent. Keys are absent from browser storage, job payloads and logs.

To connect, set the environment variable in the server's launching environment, set `enabled` to `true`, and restart that Director server. The regular launcher is `C:\TakeOne\scripts\TakeOne.ps1 -Command simulator -Port 8770`; use an available port and stop only the intended Director instance when doing a supervised restart. Do not stop the independent cart runner to configure planning.

An optional standalone acceptance command sends exactly one curated, non-private brief through the same application and budget boundary:

```powershell
& 'C:\TakeOne\.venv\Scripts\python.exe' 'C:\TakeOne\scripts\verify_director_planning_live.py' --allow-paid --skill product
```

It is excluded from automatic test discovery, requires configured access, and writes a uniquely named report under `data/verification`. Repeat separately with `dialogue` and `reaction` only when those additional paid requests are intended. Inspect each generated script's truthfulness, blocking and unresolved questions; a successful HTTP response alone is not quality acceptance.

## Verification and status

The reproducible root command is:

```powershell
& 'C:\TakeOne\scripts\TakeOne.ps1' -Command test
```

The final check counts and exit codes are recorded in `data/verification/director-step02-evidence.json` and `data/verification/summary.json`. Tests cover additive migration, supplied-fact persistence, strict scene references/timing, source-instruction containment, unsupported movement, actual preview/take-acceptance invalidation, capture-stage exclusion, duplicate receipt/budget behavior, one-job backpressure, cancellation, restart, malformed/refused/incomplete provider output, no-retry transport failures, job deadlines independent of stalled transport, and a complete sample/edit/inspect path through HTTP.

Actual browser checks used the served application at desktop width and 390 × 844: custom brief creation, fact persistence, manual script creation, sample selection, dialogue editing, refresh persistence, approval then line-choice invalidation, unsupported sideways-move rejection, camera-direction revision to phone-arm aiming, accessible narrow navigation, modal validation without losing edits, and the missing-key connection state. The narrow page had no horizontal overflow. The browser console reported no errors in the inspected log snapshot. These are local interface checks, not live-model or hardware tests.

The verification database is `data/verification/director-step02.sqlite3`. The delivered app uses the normal `data/director/sessions.sqlite3` store. Before the new runtime took ownership, the normal store had zero sessions and zero pending jobs. The cart-testing server at port 8769 was not stopped. Live provider acceptance remains unverified; see the [work-package manifest](../work-packages.json) for current delivery status across packages.

## File mapping and recovery

| Before | After / responsibility |
|---|---|
| `apps/rehearsal/dist/director.html` foundation dashboard | Authored prompt composer, production editor, connection and edit dialogs |
| `apps/rehearsal/dist/director.css` foundation styles | Responsive Director visual system, keyboard focus and reduced-motion treatment |
| `apps/rehearsal/dist/director.js` foundation UI | Application controller for saved briefs, creative jobs, edits and revisions |
| Illustrations/framing visuals absent | `apps/rehearsal/dist/director-visuals.js`: original, local SVG assets |
| Foundation API/contracts/repository | Additive creative API, `script` phase and schema-v2 tables; original demonstration API retained for foundation verification |
| Creative planning absent | `packages/takeone/director/{creative,skills,provider,planning}.py` |
| Provider configuration absent | `configs/director-planning.json`; no credentials committed |
| Package-02 tests absent | `tests/test_creative_planning.py`, additional HTTP acceptance, opt-in live script |

Before replacing the UI, byte copies of all three authored files were saved to `data/recovery/director-step02-before/`. Recovery hashes are recorded with the evidence. The previous foundation implementation is also tracked in Git. Recovery should restore that UI only together with its matching source revision; do not delete or replace the active SQLite store with an older schema file. The schema migration itself only adds tables and leaves original table contents intact. No calibration original, LeRobot source, firmware, device setting, robot geometry or cart-control logic was changed for this package.

## Sources consulted

- [Vizard Agent](https://agent.vizard.ai/): inspected the public landing page, its prompt-first hierarchy and template entry points. The TakeOne artwork, palette, layout and production workflow were authored locally; no private screens, branding or assets were copied.
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs): strict `text.format` schema, required fields and refusal handling.
- [Selected planning model](https://developers.openai.com/api/docs/models/gpt-5.6-terra): Responses support, structured output, reasoning options and pricing baseline. This research verifies documented capabilities, not this account's live access.
