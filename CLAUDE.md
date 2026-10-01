# TakeOne — project context for coding agents

Robotic filming rig: one UART-driven cart, two SO-101 arms (phone camera +
light) on Feetech buses via the vendored `lerobot/` tree. Software plans and
rehearses camera moves in a local browser simulator; physical playback is a
separate, explicit, supervised path. Read `AGENTS.md` (working conventions)
before changing subsystem boundaries; `docs/architecture.md` is the system map.

## Layout

- `packages/takeone/` — all product Python (stdlib-only core; mujoco/scipy/numpy
  only via the `simulation` extra). Key packages: `previs` (studio previews),
  `planning` (validated shot compiler), `motion` (hardware paths, studio
  playback), `cart`, `director`, `voice`, `recording`, `editor`, `simulation`.
- `apps/rehearsal/` — stdlib HTTP server (`server.py`, port 8766) + authored
  Three.js UI in `dist/` (plain ES modules, no bundler — **`dist/` is source,
  never build output; do not delete it as a cache**).
- `apps/editor/` — React/Vite editor UI (port 5178); backend is
  `takeone.editor.cli serve`. `dist/edit.html` in the rehearsal app is a
  different thing: it answers which takes have footage on this disk
  (`recording/sync.py`, matching by the clip name the phone recorded under) and
  never claims TakeOne has read those frames.
- `lerobot/` — complete vendored LeRobot with local changes; has its own
  AGENTS.md and Python 3.12 venv. Do not "upgrade" or reformat it.
- `configs/`, `calibration/` — versioned truth. Calibration originals are
  byte-preserved; never regenerate or reformat them.
- `data/` — evidence: measurements, run manifests, verification logs. Append,
  don't rewrite. `data/previs-cache/` and `data/review-cache/` are regenerable
  caches (gitignored).
- `archive/recovery/` — pre-migration snapshots consumed by
  `scripts/check_integrity.py`. Keep.

## Commands (Windows PowerShell is the primary environment)

- `scripts/Setup.ps1` — root env (Python 3.13 + uv + npm).
- `scripts/TakeOne.ps1 -Command simulator|diagnose|dry-run|test`.
- `test` runs `scripts/verify.py`: `python -m unittest discover -s tests`,
  simulation tests (need mujoco/numpy/scipy), `npm test` + `npm run check` in
  `apps/rehearsal`, `scripts/check_integrity.py`, `ruff check` + `ruff format
  --check` on `packages/takeone tests scripts` (line length 110).
- After robot-model changes: `python -m takeone.simulation.model`, then
  `node apps/rehearsal/export_models.mjs`, then tests.

## Hard rules

- The simulator must never open a serial port; no hardware side effects at
  import or test time. Device work is opt-in and human-supervised.
- Never claim hardware readiness from simulated results. Measured, assumed,
  simulated and transmitted values stay distinguishable. Keep existing
  physical blockers visible rather than inventing approvals.
- Preserve hardware/protocol boundaries: device identity checks, calibration
  endpoints, servo health faults, the UART command cap (±0.15, two decimals),
  the 60 ms firmware watchdog handling, and explicit execution confirmation.
- Validate at real boundaries (HTTP bodies, uploaded files, device I/O,
  provider responses); trust typed internals — don't re-validate the same fact
  in layer after layer.
- Voice live (Feature 09): the browser talks to Gemini directly with a
  single-use token minted by `voice/live_tokens.py`; the API key stays
  server-side, the persona/tools/compression are locked in the token, and all
  production changes go through `voice/tools.py`'s validated dispatcher. Tool
  results are spoken — keep them under 600 chars; refusals must name the field.
  No voice tool may ever start physical robot motion. Google-facing wire shapes
  live ONLY in `provider_gemini._token_request_body`, one marked section of
  `dist/voice-live.js`, `review/vlm.GeminiFrameAnalyst`, and
  `director/provider.GeminiPlanner._generate_body` (script planning over
  generateContent, used when the server holds `GEMINI_API_KEY` rather than
  `OPENAI_API_KEY`); fix disagreements there, nowhere else. The token-mint body was exercised against the live
  service with a real key on 2026-09-17 by the repository owner and its field
  names reflect that run; the browser socket section and the vision client
  remain unverified. `review/vlm.GeminiFrameAnalyst` is never instantiated, so
  every verdict today is `local-pixel-statistics`.
- World Scout (Feature 18): Google Photorealistic 3D Tiles are display data and
  never become planning geometry. `location_scout/contracts.WorldEvidence`
  enforces that at construction; `require_planning_authority` gates every
  consumer. Planning geometry comes only from open map data, operator
  measurement, Photo Scout or authored proxies. Google Maps Platform wire shapes
  live ONLY in `location_scout/grounding_google.py` and the tile section of
  `dist/location-world.js`; fix disagreements there, nowhere else. Latitude and
  longitude stop at `location_scout/geodesy.py` — everything downstream is
  ordinary scene-local metres. `configs/location-planning.json` selects
  `gpt-5.6-sol` at `high` for location reasoning only; script planning stays on
  `gpt-5.6-luna` and `director/provider.MODELS` is the reviewed allowlist that
  carries each model's published prices. Sol is a planner: its response schema
  holds prose, rating enums and one bounded rank, and nothing else.
- The rig has one lens range, `MIN_FOCAL_MM`/`MAX_FOCAL_MM` in `previs/channels.py`.
  `previs/camera.apply_camera` is the authority on the focal curve and overwrites
  every frame `previs/program.focal_length` produced during the solve; the two
  clamp to the same range. A move that asks for a focal length outside it is
  filmed at the limit and says so (`lens_clamped`, `requested_focal_mm`, and a
  note) — a clamped Dolly Zoom has stopped holding subject size, and
  `framing_drift_percent` is the detector for exactly that, not a measure of
  optical fidelity on the handset.
- Tracking judges framing on whatever camera `configs/perception-source.json`
  names, and every take records which one. Blackmagic REST is transport control,
  not video, so the phone's own image arrives as an ordinary video device (its
  USB-C/HDMI feed through a capture card, or Continuity Camera) and the browser
  selects it. `kind: phone_lens_feed` sets `witness_to_lens_offset` to
  `none_same_lens` and is the operator's claim, stored as `operator_reported`;
  it never becomes a claim that TakeOne has read the recorded clip, and it
  cannot be set without explicit confirmation.
- A phone take drives the lens only from cues it was given. `PhoneRecorder`
  builds its plan from `context["shot"]` — the reviewed `camera_cues` the Record
  page sends with the take — and a take without them leaves the lens exactly
  where the operator framed it. Never fabricate cues to fill that gap, and never
  clamp a focal length the calibration has not measured: `mapped_zoom` refuses,
  and a refused take is the honest outcome. The Record page warns before Start
  when a scene's focal range falls outside the measured points.
- Cart pace policy is `previs_policy.cart_pace_max_m_s` in
  `configs/arm-execution.json` (0.50 m/s). It stays inside the unchanged UART
  command cap of 0.15: the provisional linear map puts that cap at 0.5156 m/s.
  A turn needs the outer wheel faster than the centre pace and can still
  saturate; the planner clips and reports achieved travel. Raising it further
  needs a commissioned wheel response, not an edit.
- SI units, explicit frames, monotonic timestamps, named arm roles. Phone
  wrist-roll is motor ID 6; light wrist-roll is ID 5.
- Mesh JSON from `visual_model` is byte-faithful to compiled MuJoCo
  coordinates (a test pins this); never round it for payload size.
- Frame arrays in shot payloads are compared exactly for plan fidelity; do not
  round or reformat them.

## Frontend performance rules (Shot Studio `/`, Motor Lab `/motor-test.html`)

- All rendering is on-demand through `dist/render-loop.js`: invalidate on
  change, return `true` from paint only while playback/motion continues. Never
  add an unconditional `requestAnimationFrame` loop.
- No allocation in per-frame paths (`pose()`, `updateScene`,
  `animateDrive`) — reuse hoisted temporaries; guard DOM writes behind
  value-diff checks (`setText`).
- `/api/model` responses are ETagged; clients rebuild GPU geometry only when
  `modelHash` changes. Dispose Three.js geometries/materials when replacing
  them (`disposeRobot`, `rebuildPath`).

## Testing notes

- Python ≥3.12 required (StrEnum, `datetime.UTC`). Tests: `tests/` (product,
  stdlib-only), `tests/simulation/` (mujoco), `tests/editor/` (hermetic),
  `apps/rehearsal/tests/*.test.mjs` (node --test; some import vendored
  `three`).
- Don't rewrite tests to make a refactor pass; they encode contracts
  (encoder-count exactness, byte-preserved calibration, fidelity checks).
