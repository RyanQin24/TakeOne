# Ten-shot nighttime rehearsal and per-shot redesign

## Open or reproduce the authored candidate

The local production is **After Dark — Waterloo / 10-shot two-person demo**.
The reproducible script is an authored, unapproved rehearsal, not a live-model
generation or a hardware qualification. The local production also has a real
Luna single-shot revision and an explicitly reviewed correction in history,
described below. Earlier productions remain available unchanged.

From the repository root, with the rehearsal server on port 8766:

```powershell
.venv\Scripts\python.exe scripts/night_demo.py
.venv\Scripts\python.exe scripts/night_demo.py --save
```

The first command validates and compiles without saving. `--save` creates a new
production only if no blocked shots or revision-level findings remain. The printed
session ID and digest form `/?script=<session_id>/<digest>`. `--update <session_id>`
explicitly replaces this demo's document using a revision-checked save; it refuses
a production whose brief/title does not match. Normal history preserves revisions.

## Shot design

Ten edits with 4–8 second beats, separate source takes and off-camera resets.
Alex doubts the rig; Maya changes the brief; the camera answers through motion.

| Shot | Camera and performance |
| --- | --- |
| 1 | 5 s: actor-free architectural tilt-up; cart held |
| 2 | 8 s: front-facing walk-and-talk; Alex challenges the camera |
| 3 | 5 s: Maya's reply with a visible Dutch roll; cart held |
| 4 | 7 s: elevated-platform reveal, stationary lower-level cart, rising phone and delayed lowering light |
| 5 | 4 s: actor-free practical-lamp tilt-down; cart held |
| 6 | 5 s: pan into Maya's question with 48→24 mm reveal; cart held (authored baseline; a live redesign is a separate revision) |
| 7 | 7 s: Dolly Zoom while Alex asks the viewer to watch the background |
| 8 | 5 s: actor-free architectural parallax; phone rises and light lowers |
| 9 | 8 s: Maya's front-facing walking direction with independent height changes |
| 10 | 6 s: pull-out and a two-speaker closing exchange |

The set has a facade, trees and practical lamps. These are illustrative placement
assumptions, not a survey of the venue. Blue/amber wardrobe separates the actors.
Visual inspection caught occlusion in the opening; staggering the supporting
actor made both figures readable. The platform reveal was inspected at 24.7 s:
both full figures and the raised surface are visible. Staging remains illustrative.

Requested cruise during travelling shots is 0.40 m/s. Four shots deliberately
hold the cart while the phone rotates; the whole-film average is consequently
lower than the earlier all-travelling cut. The platform reveal is a fifth held-cart
shot. Moving routes span 2.0–3.2 m.
Independent source takes are 4.4–8.4 seconds, so the edit does not require artificial
freezes. Setup/return travel is outside the 60-second edit.

The opening tilt achieves about 11 degrees of camera rotation relative to the cart,
and the Dutch shot about 9 degrees, both with zero cart travel. The Dolly Zoom
changes from 24 to about 42 mm over roughly 2.6 m of achieved cart travel.
Shot 4 stages both actors on the user's approximately 0.6 m platform. The phone
achieves about 1.201–1.551 m optical height, a 35 cm arm rise, while the cart holds.
The 0.7 m experiment was rejected for severe aim/reach error; this is not a
ground-level camera. Platform size/access/edge clearance still need site review.
Authored baseline focal choices stay between the existing 24–48 mm calibration
endpoints. Physical framing still needs confirmation on the actual phone.
No torque, calibration, maximum-speed policy or physical hardware was changed.

Verification for this update: 98 focused Python tests and all 346 browser tests
passed; changed Python files passed Ruff. The full `TakeOne.ps1 -Command test`
workflow was also run but is not green: broader failures include Windows symlink
fixtures, legacy command snapshots/provider expectations, stale editor design
tokens and formatting in other files. The platform/loader expectations and live
persona overflow discovered in that run were corrected and rechecked in the
focused suite. This is not a claim that the whole repository test suite passes.

The three environmental shots intentionally show only part of large objects;
their manual crop advisories remain visible. No revision-level findings remain.
They have `subject_motion:none`, empty actor IDs, and empty scene cast—not merely
an actor placed out of frame. Actor reactions include explicit head-attention
tracks, not inferred animation from dialogue. Facial acting/audio remain unverified.

## Loading and small-screen review

At a narrow panel width, the sequence flex row put the monitor beyond the right
edge. It now stacks vertically with the film monitor first. The saved dialogue
of the active shot appears below the monitor; silence removes it. This is script
text, explicitly labelled as not recorded audio. It is read from any production's
active shot, not from a demo-specific production ID or hardcoded caption list.

Sequence preparation announces its shot count. Read-only planner requests have
a two-minute deadline and a retry error instead of waiting indefinitely. Old
revision links offer a route back to the current script in Director; they do not
silently replace the requested revision. Robot requests use a separate client.

The dependency-free `studio-startup.js` catches failures that occur *before*
the main module's initialize function, including WebGL construction and failed
module loads. It names the error and offers Reload studio instead of a permanent
"Setting the scene" spinner, with a 20-second import deadline. A failed dynamic
module load was reproduced locally and recovered by Reload studio. The supplied
Chrome screenshot alone does not establish Chrome's exact error or GPU status.

## Natural-language choreography and joint evidence

The camera monitor links **Direct this shot in natural language** to the current
shot's existing AI redesign editor and paid-request gate. It does not submit on
navigation. The model receives staged per-actor head samples in shot-local XYZ,
including constant platform elevation, plus the existing movement/channel catalog.
These are authored positions, not online face/speaker detection. A live listening
camera requires a separately qualified perception and speaker-identification path.

Single-shot provider context includes only that scene's assets and marks; all
movement choices are retained. This avoids a size-limit refusal without raising
the request budget or output cap. Every accepted proposal is still editable and
unapproved; other shots and the selected edit/capture identity are protected.

Movement evidence now prints five named phone-joint and five light-joint ranges
from the solved retained footage, including zeroes. The platform reveal has about
88° phone shoulder-lift/wrist-flex excursion and 12.5° elbow excursion; its light
lift/elbow/flex excursions are roughly 76°/31°/82°. The Dutch shot supplies about
9° wrist roll. No artificial motor wiggle, torque change or hardware run is used
to manufacture these numbers. Lens zoom is labelled separately from arm travel.

Actor XYZ tracks allow a constant standing-surface Z from 0–1.5 m; varying Z,
negative height and unsupported climbing are rejected. Body and face-target
height use the same elevation. Supporting cast following the lead inherit it.
The scene limit is now 12, matching the existing per-scene shot/mark authoring
limits, so separate empty inserts and an elevated setup need not share false cast.

### Live API test and reviewed correction, 2026-09-19

The user authorized one request capped at US$0.15. Job
`8d21c5f2-a6b1-438e-a297-c15f98292865` succeeded with `gpt-5.6-luna`, MAX effort,
27,738 input tokens and 26,209 output tokens. The application's configured cost
estimate was 36,999 micro-USD (US$0.036999), not an invoice measurement. The
earlier request-size refusal happened before a provider call. No paid retry,
physical movement, recording or script approval was performed.

The model returned explicit staged-head target keys, a separate phone rise,
delayed light tracks and a 48→35→48 mm curve. It did **not** return a film-ready
shot: review caught unreachable height/aim, excessive promised travel, incorrect
hold interpolation, contradictory continuous two-person framing and two successive
speakers encoded as alternative lines. Original model provenance remains in history.

A separate manual revision retained the head handoff and five-second timing,
but reduced the rise to 1.25→1.30 m, smoothed the actual transition intervals,
used phase-specific face checks and combined the spoken turns in one selected
line. Simulated framing is now 75→35→85 mm, with each tight value held through
its line. These intermediate/crop choices need physical phone verification;
they are not newly calibrated optical lenses. Cart travel is zero, phone
relative excursion about 7.9 cm with 10.6° rotation, and light relative excursion
about 24.9 cm. Phone pan/lift/elbow/flex ranges are approximately 10.5°/15.3°/1.8°/13.4°;
light ranges approximately 9.9°/34.1°/26.4°/34.1°. Wrist roll is intentionally zero
here; the Dutch shot demonstrates roll separately.

Both speaking windows pass sampled face visibility, size and centering checks.
The full two-person crop advisory remains manual because the non-speaking person
deliberately leaves the frame. No blocked shots or revision-level findings remain
in the full corrected edit. Browser visual checks at 30 s and 33 s confirmed
Alex then Maya centered with distinct lens framing and both dialogue turns shown.
Reverse-angle facade and practical-light dressing were added in a subsequent
world-only revision, preserving every shot. They are still assumed set dressing.

Natural language therefore produces real editable choreography, but generation
is not a guarantee of feasibility. This test required review and correction;
it is not evidence of automatic live speaker detection or hardware qualification.

Live voice retains the complete core robot-direction and rehearsal-review rules,
with concise shot-design coaching instead of the full planner's serialization
examples. This fixes persona construction exceeding its unchanged 16 KiB limit.
Mocked token/session tests cover that boundary; no additional paid voice session
was started. A static-cart template with changing arm/lens keys is now labelled
as custom choreography rather than misleadingly called a locked camera.

## Redesign or customize a shot

In **Director → Shots**, expand a shot and choose **Redesign this shot with AI**.
Enter the change, choose **Review AI request**, then review the separate paid-request
confirmation. Cancelling either step sends no model request. The in-page editor
works in browsers that do not support `window.prompt()`.

The server sends one full shot plus the existing scene/cast/marks and movement
catalog. The model may revise action, lines, composition and movement, but must
preserve the shot ID, edit timing and capture identity. Validation failure retains
the old document. Success creates an unapproved revision and leaves other shots
unchanged. A clip sharing one continuous take with another clip must first be
separated; single-shot redesign cannot silently rewrite shared choreography.

**Edit simulator movement** exposes existing motion settings and channel editing;
Shot Studio's **Draw path** supports custom ground routes. These are editable plans,
not commands to drive the robot. Rehearse and inspect again after changing them.
The Director remains on Luna with MAX reasoning and the existing request budget.
Updated shot-design guidance respects explicit shot count, cast, night setting and
custom movement instead of imposing the shorter default shot count.

## Phone and sync qualification still required

The supplied Blackmagic control URL responded to a read-only probe on 2026-09-19.
It reported an iPhone 17 Pro Max, controllable zoom, no active recording, and 60 fps
with portrait-shaped 1214 × 2160 dimensions. This candidate is landscape 16:9.
Confirm orientation and the changed camera-format fingerprint before a real run;
the probe does not establish optical calibration or hardware readiness.

The control API connection is not a live video stream or footage transfer.
The configured perception source had no selected device/operator confirmation,
and the recording sync inbox contained no clips or matched takes at inspection.
Live preview and recorded-media sync therefore remain unverified. A real video
source and an actual captured/transferred clip are required to close those checks.
Do not label the demo hardware-ready from the simulator or unit tests alone.
