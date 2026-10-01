# Planning failures must not look like finished scripts

The Waterloo demo exposed three independent boundaries: the selected provider
must be OpenAI Responses for `gpt-5.6-luna` at `max`; the request and response
envelopes must fit their local bounds; and the manual writing scaffold must not
be approvable as a finished script.

The affected production had a rejected provider request, two 180-second
timeouts, then an explicitly opened manual draft. No successful AI proposal
preceded its approval. A subsequent live regression request exposed a separate
256 KiB response-envelope rejection.

## Current behavior

- Keep the selected Luna model and MAX effort; never silently substitute a model.
- Allow 600 seconds, 48,000 output tokens (including reasoning), and 128,000
  request bytes. Keep the existing per-request and session spending bounds.
  Explain token exhaustion explicitly. No automatic paid retries.
- Bound the full Responses envelope at 2 MiB rather than treating output tokens
  as a bound on serialized response metadata and schema as well.
- Explain pending generation in the UI. Do not offer a blank manual draft while
  a generation is in progress. After failure, offer explicit AI retry separately
  from opening a blank manual draft.
- Save manual work normally, but reject approval while the editor's writing
  prompts remain. Previously approved scaffolds are also exposed as incomplete
  when read, without deleting their history. Legitimate factual placeholders,
  silent performance and intentional static shots are not prohibited.
- Reject a model result containing the same scaffolding without replacing the
  saved script. The shot-design skill asks for a concrete story and encoded
  motion, not a generic blank shot or mandatory motion in every film.
- Supply explicit hexadecimal appearance colors, normalized performer-track
  endpoints and zero-based dialogue selection in the provider contract. Allow
  different actors' performance beats to overlap while rejecting overlapping
  beats for the same actor.
- Retain a rejected proposal in its failed job for diagnosis. Explicit recovery
  edits must pass normal validation, belong to the same session and brief
  generation, remain unapproved, and show their recovered/edited provenance.
  Recovery does not issue another model request.
- A continuous take with insufficient compiled source time is retained as
  blocked, with available/required seconds and an explicit timing correction.
  Block all edits sharing that take, but allow unrelated shots to rehearse.
  Never stretch playback or freeze its last frame to imply missing footage.

## Reproduce without API spending or hardware

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_creative_planning tests.test_director_script_bridge tests.test_provider_catalog_compaction tests.test_performers tests.test_shot_design -q
node --test apps/rehearsal/tests/director.test.mjs apps/rehearsal/tests/director-movement.test.mjs
```

The provider tests simulate a valid response above 256 KiB and an oversized
response above the new bound. Both remain single requests with a closed
connection. Manual-template tests exercise server rejection, old persisted
approval, model-result rejection, and the browser approval/retry controls.

A live check is separate and explicitly budgeted: create a script from a saved
brief, inspect its model provenance and job result, then compile its current
rehearsal manifest. Check achieved source duration and actual cart/actor/camera
samples, not only movement names or prose. Simulation does not authorize or
qualify physical robot playback.

The recovered Waterloo model draft required explicit pace corrections for two
short captures. It now compiles as six shots but still has framing, attention,
motion-target and nominal clearance review warnings. It is not approved. A
separate authored five-shot, 60-second Waterloo rehearsal was checked with no
blocked shots, revision findings or artificial preview holds. Do not confuse
that authored fallback with a fully validated, untouched model generation.
