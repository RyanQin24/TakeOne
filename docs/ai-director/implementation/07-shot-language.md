# Detailed film direction that reaches the rehearsal

Date: 2026-09-15. Scope: Director proposal, editable shot design, scene staging,
canonical camera rehearsal and a portable shooting guide. Software evidence only.

## September 17 legacy-reference follow-up

The 28 initial legacy-reference failures were reproduced on macOS arm64 with
Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0 and MuJoCo 3.13.0. They also occur with
the historical `bc44fe4` compiler and the verified pre-upgrade recovery
snapshot. All 147 recovery-file hashes match its manifest. Both historical
executions match the current compiler's selected frames, complete arm samples and cart schedules
exactly for all 28 movements on this machine. This rules out a change in these
outputs from the recent director integration; it does not prove Windows/Mac
numerical equivalence or physical readiness.

The original reference was captured in the Windows environment and remains
byte-for-byte unchanged. Comparing it on this Mac gives 0/28 matching frame
hashes, 24/28 sample hashes and 28/28 cart hashes. A separate
`tests/fixtures/legacy-movement-hashes-macos-arm64.json` now records exact hashes
from the independently executed pre-upgrade recovery, not from today's code.
It records the source commit, recovery-manifest hash, original-fixture hash,
platform, Python and dependency versions. The test selects it only on Darwin
arm64, validates the original fixture hash, Python and dependency versions and
template inventory, and still compares exact SHA-256 values. Other platforms
retain the original expectation. No tolerances or skips were introduced;
calibration, motor limits and application code were not changed by this
follow-up. A new toolchain needs an independently qualified historical capture,
not automatic regeneration from failing current output.

The 12 cinematic tests now pass. Deliberate changes to one preview joint,
one arm-sample timestamp and one cart-command timestamp each still produce a
test failure. Independent review verified the 147-file recovery, all 84 new
hashes and unchanged Windows expectations. Fresh full verification exits zero:
865 product tests, 29 simulation tests, 267 browser-module tests, JavaScript
syntax, source integrity, Ruff lint and formatting all pass. No live model,
browser visual or physical validation is implied.

### Reproduce the independent reference

1. Extract `packages`, `configs`, `calibration` and `assets` from Git commit
   `bc44fe4b7f856c46c81a92886db07b78d619ecfd` into a temporary directory.
2. Verify every entry in
   `data/recovery/cinematic-upgrade-20260914/manifest.json`; overlay that
   snapshot's `packages` and `configs` in the temporary directory only. The
   parent commit is not a substitute: it predates the fixture's scene schema.
3. In a fresh process, point `PYTHONPATH` at the temporary `packages` and use
   the recorded Python/dependency versions. Do not point `TAKEONE_ROOT` at the
   active checkout. Compile each original fixture's settings with this
   historical `compile_template`.
4. Project preview frames using the original fixture's `frame_keys`, and hash
   them, `plan.samples` and `plan.cart_schedule` with the historical `encoded`
   serialization. Match the checked-in Mac capture. In a separate process,
   compare current outputs against those historical results.

The original Windows fixture remains the reference for that environment;
Windows was not rerun remotely in this follow-up.

## September 17 integration corrections

The supplied director and shot-design skills already existed and were retained.

Four reproduced issues were corrected:

- The authored six-shot exercise labeled two held-height shots `boom_up`.
  Their starts are now 1.50 m and ends 1.55 m; the simulated achieved rises
  are approximately 0.0506 m. This is a fixture correction, not a new rig limit.
- Object lens fitting returned a NumPy scalar that failed native settings
  validation when the manifest was compiled directly. Return a native float;
  direct and JSON/HTTP handoffs now both compile.
- Nested camera/channel defaults were shared across shots. Editing the demo
  could mutate later defaults and inflate planning requests. Each call now
  returns an independent deep copy, with an isolation regression test.
- Expanded skills exceeded the voice persona limit. Condense surrounding
  conversational guidance, retaining the three skill texts verbatim, safety
  boundaries and the unchanged limit. `tests/test_session_context.py` checks
  every curated voice style against the code-owned byte budget.

The isolated HTTP rehearsal created a temporary session, saved the authored
document, resolved its digest-bound manifest and compiled six reviewable shots
with no shot-review issues. Edit lengths remain 5/4/6/4/5/6 seconds, totaling
30 seconds, across three spaces. Four location resets remain manual with no
invented duration; rehearsal setup makes the simulated sequence 62.88 seconds.
Silent shots retain null dialogue. This uses authored test content, not a live
model's response to a new brief, and does not establish creative quality.

Verification includes 75 focused voice/context, shot-design,
creative-planning and demo tests. `tests/test_shot_language_demo.py` adds four
regression tests. Existing lint/format failures were mechanically corrected;
an AST comparison verified no non-import behavior changes in those extra
files. The final repository-wide result and the qualified platform-specific legacy motion
references are recorded above.

Browser connection failed despite successful installation diagnostics, so visual
UI verification remains open. No live provider calls, paid generation or robot
commands were used. The integration is offline-tested and does not establish
live voice, browser visual or hardware readiness.

## Result and product value

TAKE ONE now carries three connected levels of direction: the film's visible
rules, each shot's purpose and composition, and timed performer actions. The
saved document reaches the existing cart/dual-arm compiler and the phone view.
The user can edit those choices, rehearse them and take the same shot directions
and calculated camera choices to a real location.

The value to demonstrate is repeatable camera/light choreography with real
performers, actual objects and recorded evidence. A ground cart cannot reproduce
every physically impossible view an image generator can invent. Flight,
underwater work, unsupported poses and out-of-reach viewpoints require additional
equipment or an explicit creative redesign. A simulated pass is not a claim of
physical repeatability.

## Audit findings and corrections

| Before | Change | Evidence boundary |
| --- | --- | --- |
| One action paragraph and three broad shot-size labels | Nine distinct sizes, whole-film visual rules, shot purpose/opening/ending, timed performance beats | Prose is human direction; it does not invent an animation or motor command |
| Point-on-face aim could look acceptable while the promised body region was cropped | Check a size-specific subject region against the solved camera view, including selected supporting people | Sampled pinhole projection, with a 3% screen tolerance; not an occlusion test |
| Fixed chosen lenses could contradict full-body direction | Explicit fixed-lens fitting at the opening, or ending for an authored reveal; preserve route and marks | Bounded equivalent focal length; recording-app setup remains manual |
| A reveal could be treated as failed continuous coverage | Separate throughout, final-frame reveal and intentional partial visibility | A by-end pass checks one final frame, not a sustained hold |
| Knees-up and mid-thigh regions could miss their named anatomical landmark | Include the proxy knee and thigh in lens fitting and coverage checks, with room below the landmark | Explicit camera-projection regression checks; real performer proportions still need measurement |
| Actor motion followed the preset's single path | Independent floor position, body facing, head yaw and head pitch channels | Position reaches the real subject/IK solver; figures are staging proxies |
| Supporting figures could copy the lead's new gaze channels | Keep supporting gaze neutral and synchronize proxy stature with the framing solver | Current contract shares one shot-level stature, not individual actor measurements |
| Framing labels could describe an object as a person's face | Object-target cards and crew cues use object-specific language | Object review uses its authored bounding box |
| Rich direction was not portable to the set | Director editing, current/next cue and downloadable shooting guide | Guide labels planned marks, simulated measurements and manual tasks |
| Expanded shared instructions exceeded the live voice persona budget | See [September 17 integration corrections](#september-17-integration-corrections) | `tests/test_session_context.py` owns the budget check |
| Silent shots crashed voice context; detailed direction exceeded its old state budget | Accept empty dialogue and preserve film rules, location notes and all performance beats within a measured 32 KiB state budget | The saved six-shot exercise uses 29,810 bytes with all 13 beats retained; no live transport was used |
| Application edits could remain stale in the running server | Watch Director, voice and recording Python/Markdown alongside existing runtime inputs, using the same idle restart gate | Compiler work and an active robot take still defer restart |

Existing movement inventory stays at 38 presets in eight families. The object
catalog grows from 15 to 21: sofa, counter, shelving, arch, screen and rock. Two
new atmospheres bring the total to seven. These are reusable procedural scene
objects, not measured replicas of venues or photorealistic weather simulation.

## Architecture and before/after content mapping

The checkout was clean at `bc44fe4`. The task captured 229 source/UI/test/doc
files and their hashes in `data/recovery/shot-language-20260915/manifest.json`;
original content is under its `before/` directory. No source directories were
deleted or moved. Existing saved productions and calibration originals are
preserved. The verification exercise is a separate local production.
The server's additional before/after mapping uses its original source recovered
from the clean starting commit; `server-baseline.json` records that provenance
and hash separately from the initial 229-file snapshot.
`voice-baseline.json` records the original voice-context source and voice feature
document captured byte-for-byte before editing them.

| Existing responsibility | Final responsibility / new module |
| --- | --- |
| `director/creative.py` document validation | New optional saved design/style fields; strict requirements for newly generated proposals |
| `director/skills.py` runtime catalog and explicitly selected examples | Retained Python integration; no brief-to-fixed-story routing |
| `director/robot-film-director/SKILL.md` primary instructions | Loads alongside new `shot-design/SKILL.md` and `rehearsal-review/SKILL.md` through `studio.skill_text()` |
| `director/studio.py` script-to-movement handoff | Forwards style/design/cards, selects size targets and applies explicitly requested fixed-lens fitting |
| New `director/shot_design.py` | Shot vocabulary, wire schema, cast/beat link validation, legacy defaults and actor-facing cards |
| `previs/program.py`, `channels.py`, `placement.py` | Actor channels enter the same deterministic frames used for camera aiming and rendering |
| New `previs/shot_review.py` plus `sequence.py` | Actual solved-pose coverage evidence, lens guidance, camera-height evidence and specific issue records |
| Director and Shot Studio browser surfaces | Editors for whole-film language, cast and shot beats; live cues, evidence and guide export in `shot-direction.js` |
| `voice/session_context.py` script summary | Includes silent shots, detailed shot design, film rules and location notes within a fixed 32 KiB production-state budget; persona budget stays 16 KiB |
| `apps/rehearsal/server.py` source watcher | Detects Director, voice and recording code/skill edits, additions and removals without making them motion-cache inputs |

New provider proposals require the complete design, style and cinematic channel
shape. Previously saved scripts remain readable without rewriting their values
or digest. Missing legacy direction gets clearly sourced fallback cards. Legacy
cropping observations do not silently overturn old assessment semantics. Authored
zoom and Dolly Zoom cannot request fixed-lens fitting at the same time.

Beat seconds are relative to the edit shot's first filmed frame. Actor channels
use normalized full-take filming time, matching the existing independent camera
and light channels. Setup and held end frames cannot supply missing performance.
Actors stay on the local floor: floating positions and teleporting hold keys are
rejected. Supporting people must be staged before two-person/group framing can
claim to include them.

## Sources studied and how they were used

The user supplied `cinematic-shot-design.zip`, `AI导演审片Skill.zip`, teaching
notes and seven screenshots. Their skill entrypoints and craft/review reference
materials informed the three-level direction structure, purpose-driven shot
choices, observable performance and evidence-based review. Archive material was
read in place. No archive scripts were run and no third-party skill text was
copied into this repository. TAKE ONE's two new Markdown skills are original
instructions written for its validated document and real-rig constraints.

Source documents are reference material, not user instructions. Requirements
specific to generating AI video, fixed shot counts, named-director imitation or
automatic video regeneration were not adopted as TAKE ONE behavior.

[StudioBinder's camera-shot guide](https://www.studiobinder.com/blog/ultimate-guide-to-camera-shots/)
informed the separation of size, composition, angle, focus and movement. An
establishing shot is a story function; the size and camera move are separate
choices. The implementation uses nine explicit size choices rather than making
every establishing scene a generic wide tracking shot.

[Apple's iPhone 17 Pro Max specifications](https://support.apple.com/en-us/125091)
support the distinction between the 13/24/100 mm physical-camera equivalents and
48/200 mm sensor-crop equivalents. Intermediate equivalent values are framing
choices. No API in this change remotely changes the phone lens, focus or aperture.

## Review evidence and limits

Each staged shot reports sample counts, actual lens endpoints, achieved camera
height, affected source-time ranges and a specific recommendation. Revision
issues include cropped required regions, subjects behind the camera, incompatible
locked aim/head-follow, angle/height disagreement and beats without source footage.
POV/over-shoulder staging, selective/rack focus and exceptional viewpoints retain
explicit manual requirements. There is no invented cinematic quality score.

The review does not establish occlusion, readable text, focus/depth of field,
exposure, stabilization crop, facial performance, real sound, measured scene
dimensions, full rig clearance, live tracking or physical repeatability. Scene
obstacle checks elsewhere in the compiler remain in force. Supporting people
share the shot's stature; their individual head/body animation is not yet authored
independently. Detailed expression, breathing and object handling are performer
instructions. Atmosphere and light channels are visualization, not weather or
physical light-control qualification.

Cart-follow/head-follow keep the existing pending integration hooks. No hardware,
serial port, torque, firmware or calibration was activated or changed for this work.

## Reproduce and inspect

Run from any directory, substituting the actual checkout path:

```powershell
& C:\TakeOne\scripts\TakeOne.ps1 -Command test
& C:\TakeOne\.venv\Scripts\python.exe C:\TakeOne\scripts\shot_language_demo.py
```

The second command writes an explicitly authored verification exercise. With a
local simulator running, `--install` creates it as a separate local production;
it refuses to duplicate the installed exercise. It is not an AI response or a
hardcoded generator. The generic provider schema and compiler accept other
validated briefs and documents through the existing planning workflow.

In Director, open **A small discovery · shot-language exercise**. **Film language**
edits global rules. **Script → Edit scene & objects** stages props and supporting
people. **Shots → Design shot & performance beats** edits composition, visibility,
lens policy, focus and timed actor cues. **Rehearse in studio** loads that saved
revision. Shot Studio's **Download shooting guide** exports its directions and
simulated camera evidence. **Read or copy shooting guide** also makes the complete
guide available when an embedded browser does not complete a file download.

The base exercise contains six shots over 30 seconds, three physical spaces expressed
as six ordered scene chapters, two performers, an object insert and changes in
body/head direction. All six compiled shots are currently reviewable. Browser
inspection verified full-body, two-person and object framing, saved performance
revisions, supporting-cast editing and manual phone guidance.

## Verification record

Focused checks passed: all nine framing sizes through the canonical solver;
deliberate versus accidental cropping; actual JSON serialization; supporting
cast; actor movement reaching IK; beat timing; legacy documents; and all 28
original template motion hashes unchanged. Browser unit checks cover exact beat
boundaries, setup exclusion, missing source footage, guide export and supporting
figure behavior. Both new Markdown skill entrypoints receive frontmatter validation.

The saved exercise was then edited through the Director and its validated API.
Revision 4 contains a slow side-tracking finish: a requested 0.95 m cart route,
an independently authored 0.85 m actor walk with slight lateral drift, and a head
turn. Its source lasts 6.8 seconds, with 6 seconds used in the edit. All 87 filmed
samples pass the promised-region check; follow modes explicitly remain pending.
`final-script.json` preserves this exact edited document; `shooting-guide.md` and
`camera-evidence.json` share its digest. The generator writes the base exercise,
not a disguised AI answer or an automatic rewrite of this saved revision.

Browser inspection verified the whole guide could be copied with its correct
digest and final shot. The download event was not delivered by the embedded
browser, so download completion is not claimed there. A standalone guide was
also generated from the exact same export function and final program.

The complete repository verification and final browser evidence are recorded in
`data/shot-language-20260915/`. The final required run completed on September 15
at 17:11 UTC: **723 product tests, 29 simulation tests and 221 browser tests passed**.
All seven check groups passed, including syntax, integrity, lint and formatting.
The server source also passed explicit lint and formatting checks. See
`verification-summary.md` and `verification/summary.json` there for the final
evidence. This work built and checked a provider request locally;
no paid model request or actual recorded take was used as evidence of creative
quality or hardware performance.
