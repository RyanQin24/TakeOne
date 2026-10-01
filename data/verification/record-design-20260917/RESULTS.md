# Prompt 16 results — Record dual-frame, iPhone capture, one design system

Recorded 2026-09-17 against `b615d77` plus in-flight tracking work by the
repository owner (see "Concurrent edits" below). Same host and shim as
`BASELINE.md` beside this file.

## What is verified here, and what is not

This host runs Python 3.10 with a `StrEnum`/`UTC` shim, has no `mujoco`, no
`scipy`, no runnable `ruff`, no phone on the network and no browser. Therefore:

- **Verified:** files, unit tests against fakes, the enforcement tests, and the
  measurements below.
- **NOT verified here, `[UNVERIFIED]`:** every `/api/phone/*` and
  `/api/live-director/observe` route as served (`server.py:17` cannot import
  without `mujoco`), the whole device-facing half of `PhoneRecorder`, the Record
  page in a browser, `ruff`, and the editor's `vitest` suite (its
  `node_modules/rollup` is a Windows build).

## Test results

| Suite | Baseline | After | Delta |
|---|---|---|---|
| Python `test_[a-l]*` | 215 tests, 0 failures, 17 errors | 234 tests, 0 failures, 17 errors | error name set **identical** |
| Python `test_[m-z]*` | 362 tests, 0 failures, 47 errors, 9 skipped | 401 tests, 0 failures, 49 errors, 9 skipped | +2 errors, both `test_tracking.HTTPTests` (owner's in-flight work, `No module named 'mujoco'`) |
| `npm test` | 279 tests, 277 pass, 2 fail | 309 tests, 307 pass, 2 fail | same two `.venv/bin/python` failures |
| `npm run check` | exit 0 | exit 0 | now also checks token parity and 53 modules |
| `scripts/check_integrity.py` | exit 0 | exit 0 | unchanged |
| `apps/editor` `tsc --noEmit` | — | exit 0 | — |

`grep -c "^FAIL:"` returns 0 on both Python logs. Failing-name sets are in
`python-error-name-set-after-batch1.txt` and `-batch2.txt`.

## Budget movement (§9)

| Budget | Target | Before | After |
|---|---|---|---|
| Product CSS (`du -b dist/*.css`) | ≤ 60 KB | 205,477 B | **136,734 B** — target missed, see below |
| CSS files per page | 4 | 2–6 | **4** |
| Colour literals outside the token file | 0 | ~550 | **0** |
| Distinct `font-size` values | ≤ 5 | ~64 | **5** |
| `!important` | 0 | 176 | **0** |
| `text-transform: uppercase` | 0 | 23 | **0** |
| Three.js payload (3 pages + asset library) | 331 KB | 603,113 B | **338,908 B** |
| `requestAnimationFrame` outside `render-loop.js` | one-shot or bounded | 9 in 4 files | 8 in 3 files; **none added** |
| Instrument Serif | absent | 2 copies | absent |

**The CSS budget was missed and I do not think it is reachable.** After pruning
every rule whose classes a page never renders, collapsing all fifteen sheets,
scoping out other pages' rules and removing the shell layer from page files,
Shot Studio is 337 rules at about 108 bytes each and Director 316. That is
authored layout for two complex applications, not fat. Reaching 60 KB would mean
deleting layout those pages need.

## Concurrent edits

The working tree was being edited during this work by the repository owner: a
live-tracking feature (`motion/tracking.py`, `scripts/tracking/*`,
`configs/tracking.json`, `tests/test_tracking.py`, `docs/live-tracking.md`) and a
rewrite of `provider_gemini._token_request_body`.

That rewrite replaced `liveConnectConstraints` with `bidiGenerateContentSetup`,
wrapped `responseModalities` in `generationConfig` and made `triggerTokens` a
string. The owner confirms it was exercised against the live Gemini service with
a real API key on 2026-09-17, so **the token-mint body is no longer an unverified
seam**, and `CLAUDE.md` has been corrected to say so. The three tests in
`tests/test_voice_tools.py` that still asserted the old field names were rewritten
to the verified shape.

Google's current documentation independently confirms the other two guesses in
`c5146d5`: `gemini-3.8-live` is a real Live model id, and ephemeral tokens are
minted at `POST /v1beta/auth_tokens` and work only with `v1beta`. So live voice
failing was never a wrong model id.

## Honesty ledger

`physical_path_verified` is still hardcoded `False`. `POST /api/live-director/arm`
still returns 409 `physical_path_unverified`. `observe()` grants no motion
authority, never commands the actuator, and refuses while armed. No phone route
reaches the motion path and no voice tool can press record on the camera. Every
`source="phone"` take carries `real_media_verified: false`, `media: null` and
`media_location: "phone_internal_storage"`, and its media route answers
`media_on_device`, not a 500.
