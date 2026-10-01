# GPT-Live robot bridge — 19 September 2026

## Scope and physical acceptance

The GPT-Live WebRTC page on port 8769 now delegates real robot requests to a
bounded loopback bridge in `takeone.voice.live_robot`. The main rehearsal server
on port 8766 remains the playback/tracking owner. A separate cart-only commissioning
worker now uses the same cross-process device lock and existing CartRunner. The
voice tool can prepare a proposal; only the local operator's separate approval
button can request this worker. No model-accessible execution or arming tool exists.

This is **software implementation**, not physical robot-control acceptance.
The new one-shot timed test is not qualified distance-based jogging. The main server
currently reports `actuator_available: false`, `physical_path_verified: false`,
and `armed: false`. Those gates have not been changed. A full planned filming
shot can reposition both arms and trigger enabled phone capture, so it must not
be silently substituted for “move the robot back a little.”

## Available tools

- `get_robot_status`: live owner and qualification state; owner tokens are stripped.
- `list_robot_shots`: current offline shot catalog.
- `prepare_robot_shot`: existing validated shot planner; no execution. Review and
  prepare matching settings in Shot Studio before any independently authorized Run.
- `request_robot_move`: validates and preserves direction and explicit SI distance
  (null if unspecified). In the standalone page, a forward request with no distance
  prepares the exact timed commissioning review below. Other directions and explicit
  distances remain rejected; they never silently select another movement.
- `stop_robot`: independently requests Stop from the owned cart test and active playback/tracking owners;
  neither successful transmission nor idle software state proves physical stopping.

GPT-Live uses Responses delegation with completed function items collected from
nested `response.output_item.done` events. On `response.completed`, results are
returned through `response.item.create`, then `response.create` resumes reasoning.
The Live voice model conveys the result. Speech interruption alone does not cancel
robot work. The browser has an explicit Stop control while a tool session is active.

Tool sessions expire after five minutes, are revoked on End/disconnect, reject
changed duplicate call IDs, and memoize retries. Browser requests require matching
loopback Origin and a session capability. OpenAI and robot-owner keys remain local;
tool results and spoken content are sent to OpenAI as part of the requested voice
integration. Listen-only sessions have no tools. No microphone is used by the
separate robot-tool check.

## Supervised one-shot commissioning

The current configuration permits a proposed forward test: 0.5 seconds of equal
logical wheel commands +0.04, followed by zero-speed requests. The configured
wiring polarity is -1, so the actual nonzero UART packet is `-0.04,-0.04\n`.
These are controller values, not measured metres per second or travel distance.
Direction and stopping still require operator observation. The cart is configured
as COM5 / USB serial 0001; the worker checks this identity before opening the port.
Both arms, phone capture and lighting are excluded; the operator must physically
support the arms/payload as required by the existing hardware runbook.

1. Start a voice conversation and ask for a small forward move, or select
   **Prepare forward test — no movement** without microphone or OpenAI access.
2. Review the exact test card, verify the physical device, clear the area, support
   both arms/payload, and keep the physical abort accessible. Only then check the
   operator confirmation and click **Run this exact test — moves cart** once.
3. Observe actual direction, travel and stopping. Do not infer these from a
   `commands_completed` software result. No automatic increase, reverse or repeat
   is performed if the cart does not move.

Each review expires after 90 seconds, is bound to its browser capability and exact
source/configuration hash, and is consumed before worker launch. Duplicate start
requests cannot replay it. The child waits for the approving browser's execution
heartbeat before connecting. A 0.75-second control lease, Stop, or pipe EOF latches
cancellation. Existing startup/shutdown zero windows are 0.1 seconds each. The host
lease and UART zero requests are **not** a verified firmware watchdog or emergency
stop. End/disconnect cancels this browser's cart test; speech interruption does not.
No reconnect automatically resumes motion. Plan, approval, worker log and actual
write/timing report are recorded under `data/runs/voice-cart-<run-id>/`.

## Run and verify

Start the main app normally, then from the checkout root:

```powershell
.\.venv\Scripts\python.exe scripts/gpt_live_director_test.py --port 8769
.\.venv\Scripts\python.exe -m unittest tests.test_live_robot tests.test_cart_nudge tests.test_cart_runtime.SchedulerTests -v
node --test apps/rehearsal/tests/*.test.mjs
```

Open `http://127.0.0.1:8769/` and select **Run robot-tool check (no mic)**.
This sends a text sample through the real Live session's delegated backend,
not prerecorded audio. It checks the tool round trip, not speech recognition.
The original user microphone test established that conversation separately.

Earlier bridge-only acceptance: the backend called `request_robot_move` with backward
and null distance, received the current unqualified controller state, and TO
spoke the missing-controller blocker. No hardware motion was attempted.

Current verification: 45 focused Python checks and all 372 rehearsal JavaScript
tests passed. All motor tests use injected transports; tests never open serial ports.
The previously verified bridge also compiled a static shot without running it.
Scoped Ruff lint/format and JavaScript syntax checks passed. The robot runtime
loaded the worker's help entry point without opening a device. Windows USB inventory
matched COM5 / 0001. A real no-microphone GPT-Live session called request_robot_move
for forward with null distance, returned operator_review_required, rendered the
exact card with Run disabled, and told the operator to review before clicking Run.
The check was ended without checking the approval box or starting the worker.

The required full PowerShell test launcher was attempted. It reported editor VFX
test failures/errors before it was deliberately cancelled to remove background
test load ahead of the supervised hardware handoff. No full Python-suite pass or
physical commissioning pass is claimed. Its partial output is in the existing
verification log; focused results above were rerun successfully afterward.

To finish physical acceptance, run one exact operator-approved test with the
operator present and record direction/response/stopping evidence. This does not
automatically qualify autonomous or distance-based motion. Do not turn on a
qualification boolean to make this test pass.

## Before/after mapping

The standalone server's inline conversation-only prompts moved to
`packages/takeone/voice/live_robot.py` and became tool-aware instructions.
Existing WebRTC negotiation, microphone opt-in, transcript and listen-only flow
remain in their original files. The new pure JavaScript tool event loop is isolated
in `gpt-live-tools.js`. The cart test is isolated in `cart/nudge_plan.py`,
`cart/nudge.py`, `cart/nudge_worker.py` and `gpt-live-nudge.js`. CartRunner now compares
the adapter's returned wire packet with the polarity-adjusted expected packet,
retaining separate logical/expected/actual evidence; this fixes false faults for
the existing inverted-wiring configuration. No calibration originals, device
configuration, main-app qualification gates, or unrelated user changes were changed.

Protocol reference: https://developers.openai.com/api/docs/guides/live-delegation
