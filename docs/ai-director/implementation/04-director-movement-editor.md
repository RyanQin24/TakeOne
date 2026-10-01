# Director movement authoring and handoff — 14 September 2026

The Director writes a readable creative script and a structured movement object for
every shot. The model selects cinematography; deterministic code resolves the
current template catalog, validates settings and calls the existing simulator.
The script's saved document digest identifies the exact revision to rehearse.

## User flow

1. Open `/director.html` and enter a brief, or open the **A serious entrance**
   editorial sample. Samples are explicitly labelled; they are not AI responses.
2. Generate a script with the configured OpenAI API connection, or edit the sample.
3. In **Shots**, expand a shot and choose **Edit simulator movement**. All 28
   presets come from the same catalog used by the compiler. Angles appear in
   degrees and progress in percent; saved values remain radians and fractions.
4. Edit production notes to position named floor marks in metres and set their
   facing. These are assumed staging coordinates, not room measurements.
5. **Rehearse in studio** opens the saved script in the existing sequence player.
   The cart, both arms, scripted actor and lens cues follow the compiled settings.
   Setup and simulated repositioning remain separate from proposed edit timing.

The cinematic sample requests a low-to-high orbit, an actor walking with a side
tracking shot, and a Dolly Zoom out. Its 32-second edit currently rehearses in
about 49.64 seconds including setup and repositioning. The opening camera rises
from 1.255 m to 1.590 m and its upward pitch eases from 10.1 degrees to nearly
level. The compiler reports an 18.5-degree maximum aiming offset as an advisory
note; the example remains playable. A successful handoff is not proof that every
requested pose or edit duration is reproduced exactly.

## API connection

`configs/director-planning.json` selects `gpt-5.6-luna`, reasoning `max`, Responses
API structured output and separate API billing. Set `OPENAI_API_KEY` in the
environment of the process launching the server, then restart that server.
Do not put the key in the browser, a script document, source control or chat.
The connection panel reports missing-key state without substituting a sample
or another model. Current estimates cap a request at $0.15 and a production at
$1.00. These are local reservations, not provider-enforced billing limits.

Live provider authentication, account access and billed generation require a
real configured key and were not exercised in this verification. Offline tests
drive a labelled provider fixture through the normal asynchronous result-saving
path and then retrieve its exact rehearsal manifest.

## Changes and preservation

| Before | After | Implementation |
|---|---|---|
| Creative camera descriptions without an editable exact movement | Per-shot catalog selector and numeric editor | `dist/director-movement.js`, `dist/director.js` |
| Stage marks edited as descriptions only | Shared X/Y positions and facing | `dist/director.js` |
| Coarse camera direction could retain stale movement settings | Changing direction clears the old movement; contradictory unsupported requests remain unresolved | `director.js`, `director/studio.py` |
| Repair result could include an unrequested known shot | Only requested shot IDs can be repaired | `director/planning.py` |
| Three editorial samples without a full cinematic example | Fourth sample with three explicit movements | `director/skills.py` |
| Rehearsal handoff depended on a new window | Same-tab navigation to exact saved revision | `dist/director.html` |
| Script rehearsal could display unrelated editable lens defaults | Active shot's starting focal length; editing remains in Director | `dist/orbit.js` |
| Bright shot cards had poor contrast in the dark studio | Cards follow the studio palette | `dist/orbit.css` |
| Rising shots compared achieved end height against requested start height | Compare matching opening heights to avoid a false shortfall | `previs/diagnostics.py` |

The existing `previs/sequence.py`, template compiler, FK/IK and calibration are
reused. No second motion engine, hardware activation or global skill installation
is introduced. Earlier Director recovery copies remain in
`data/recovery/director-studio-20260913/`. Concurrent staged changes to the UI,
motion and sequence implementation are preserved; this continuation does not
replace their implementation record.

Verification logs and the compiled example outline are in
`data/verification/director-studio-20260914/`.
