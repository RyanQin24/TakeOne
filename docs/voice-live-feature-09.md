# Feature 09 — TO speaks: browser-direct live voice direction

The Director gained ears, a voice and on-demand eyes for HTN 2026. The browser
holds a WebSocket to Gemini Live using a single-use ephemeral token minted by
the local server; audio never passes through Python, the API key never reaches
the client, and **the only thing that can change production state is a tool
call POSTed back to loopback**, where the existing ownership tokens, envelope
validation, recording latch and movement-catalog bounds all apply unchanged.

Nothing in this feature can start the physical robot. `propose_shot` compiles
previews, `rehearse` warms and links the simulator, `start_take`/`stop_take`
drive the offline recorder through its existing fixture gate. Physical playback
remains the operator's explicit **Run on robot** press.

## Topology

```
BROWSER (dist/voice-live.js + worklet)          PYTHON 127.0.0.1:8766
  mic 16 kHz PCM ──WSS──▶ GEMINI LIVE           POST /api/voice/live/token
  speaker ◀──24 kHz PCM──┘   │                    mints uses:1 token; locks model,
  JPEG frames on demand      │ tool calls          persona, tools, compression
                             ▼                   POST /api/voice/tool
                     POST /api/voice/tool  ────▶   owned envelope → dispatcher
                                                 GET /api/voice/live/status
```

- **Token gate** (`voice/live_tokens.py` + `voice/provider_gemini.py`): one
  owned request → one single-use token. The persona (`voice/persona.py`,
  inheriting the robot-film-director SKILL verbatim), the tool declarations and
  `contextWindowCompression` are locked inside the token; the browser cannot
  alter them. Resumption handles round-trip through the same gate.
- **Production state** (`voice/session_context.py`): a ≤32 KiB block regenerated
  from the database at every connect and resume — movement catalog with exact
  ranges, current script with visual rules and timed performer cues, marks, last
  three take verdicts, refusal vocabulary. The September 15 shot-language upgrade
  measured a six-shot silent production at 29,810 bytes and raised this fixed
  state limit from 16 KiB to 32 KiB. The separate persona limit remains 16 KiB.
  The block, not the transcript, is the session's memory: compression can drop
  any turn because every durable decision was committed through a tool.
- **Tools** (`voice/tools.py`): fourteen are declared. Seven creative and
  recording tools — `propose_shot`, `revise_script`, `approve_script`,
  `rehearse`, `start_take`, `stop_take`, `describe_frame` — and the seven
  embodied tools that were shipped without being written down here:
  `inspect_scene`, `select_subject`, `prepare_filming_behavior`,
  `adjust_filming_behavior`, `start_filming_behavior`, `hold_filming_behavior`,
  `stop_filming_behavior`. `start_filming_behavior` is the only motion-capable
  tool in the product and is fail-closed three ways over.
  Results are capped at 600 characters (they are read aloud), refusals name the
  offending parameter and its allowed range exactly as the studio translator
  does, and the compile path answers from the content-addressed previs cache.
  `speculative: true` warms a compile from partial arguments without holding
  the turn. While the recording latch is engaged the only permitted calls are
  `stop_take` and a replayed `start_take` retry.
- **Recording linkage**: `recording_takes` migrated to `user_version=2` with a
  real `plan_id` column (indexed) and a `take_verdicts` table. `start_take`
  carries the compiled plan's id onto the take.
- **Review** (`packages/takeone/review/`): keyframes cached on
  `(media_sha256, timestamps)`; verdicts cached on media + plan + prompt
  version. The analyst ladder degrades and never breaks: a Gemini vision
  analyst when configured → local pixel statistics (pure-Python Laplacian
  focus, exposure, inter-frame change — a blurred take measurably ranks below
  its sharp original) → probe-only metadata scoring. The VLM is asked only what
  pixels can answer; the compiler already holds the commanded shot as ground
  truth. `POST /api/recording/takes/<id>/review` persists the verdict.
- **Pre-warm** (`previs/prewarm.py`): the server warms every template (plus the
  duration grid on stationary shots) in a startup daemon thread, calling
  `compile_preview` directly so it never contends with the operator's compile
  lock (`--no-prewarm` opts out). `python -m takeone.previs.prewarm --demo
  FILE` warms the exact demo path. Cache bound raised to 512 entries.
- **Shell**: the primary navigation is now four steps (Director → Shot Studio →
  Record → Edit); Voice Rehearsal moved under Utilities. Every surface carries
  a **TO** control that lazy-loads the live module on first use; the Director
  page binds the conversation to its open production.

## Configuration

`configs/voice-live.json` (versioned; **enabled since `c5146d5`**, not disabled
by default as this document previously said) selects the model, response
modalities, compression trigger and token lifetimes. The model id lives only in
this file: `provider_gemini` accepts anything matching `KNOWN_MODEL_PREFIXES`,
or exactly the ids listed in an optional `model_allowlist`, and a value that
matches neither is a startup error naming the value and the accepted pattern. The API key is
read from `GEMINI_API_KEY` in the server environment and never leaves the
process. `GET /api/voice/live/status` reports availability without leaking
anything.

## What has never run

This slice was built and tested without network access. Every seam that
touches Google is unverified against the live service and deliberately
isolated: the token request body (`provider_gemini._token_request_body`), the
WebSocket wire mapping (one marked section of `dist/voice-live.js`) and the
vision request (`review/vlm.GeminiFrameAnalyst.analyze`). Before Thursday:
mint one real token, open one real session, and fix any wire disagreements in
those three places only. Microphone capture, playback and barge-in need a real
browser check; the pure logic around them is unit-tested.

## Verification

- `tests/test_voice_tools.py` — refusals name fields and bounds; the latch
  silences everything but `stop_take`; identical request bodies replay one
  take; results stay under the speech cap; token gate locks persona and tools;
  provider config is strict (23 tests, 6 requiring the simulation extra).
- `tests/test_verdict.py` — blurred < sharp; verdict and keyframe caches replay
  deterministically; the analyst ladder degrades to probe-only; an end-to-end
  start→stop→ready→review run persists the verdict beside its plan.
- `tests/test_session_context.py` — full scripts, including silent shots and
  detailed performance beats, fit the 32 KiB state ceiling; the block is
  document-derived and carries no conversation; oversize fails loudly.
- `tests/test_previs_prewarm.py`, `tests/test_recording_plan_link.py` — grid
  shape and cache bound; schema migration equals a fresh v2 database.
- `apps/rehearsal/tests/voice-live.test.mjs` — PCM conversion, GoAway timing,
  barge-in gating, envelope refresh from results, speculation, resumption
  storage, interruption flush (10 tests).

## Known limitation carried forward

`test_movement_library`'s `tilt_up` case reportedly fails on Linux while
passing on the Windows demo machine, with recent work reverted. The likely
mechanism is IK solver-path divergence near the wrist pitch limit under a
different BLAS build. This environment has no scipy, so it could be neither
reproduced nor safely fixed; the test is deliberately left intact so the
Windows run keeps proving the contract. Investigate on a Linux machine with
the simulation extra before trusting Linux CI for the movement library.
