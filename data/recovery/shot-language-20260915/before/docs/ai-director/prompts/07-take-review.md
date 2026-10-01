# 07 — Review every take and guide the next attempt

Implement work package 07 in `C:\TakeOne`. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, `docs/ai-director/timeline-example.md`, and implementation records 02/04/05/06. Follow shared rules. Dependencies: 02, 04, 05 and 06.

## Outcome

After every completed take, the Director reviews what was actually recorded, gives useful limited feedback and offers accept, retake or revise. The actor receives feedback after recording, not interruptions during the performance. The Director can also help rewrite a difficult line for the next take.

## Implement

1. Trigger a review only after confirmed stop and validated original media. Capture observations can prepare evidence during recording, but review output belongs to the completed take. Assign review jobs take/media/plan IDs, versions and cancellation identity.
2. Align the accepted beats to actual media and transcript timing. Compare observable requirements with intervals and tolerances instead of requiring pixel-perfect reproduction of the animation. Do not use the intended script as proof that the actor said it.
3. Produce local checks for things the evidence supports: framing/visibility, intended direction or mark, timing, audible delivery and file/audio problems. Return UNKNOWN for unreliable views or synchronization. Attribute actor, staging, camera and system causes separately.
4. Use the selected visual reasoning backend for bounded contextual review of relevant frames or supported clip input plus transcript and observations. Follow its actual media input capabilities; do not label sampled-frame analysis as continuous-video understanding. Assert factual findings only with supporting timestamps and evidence references.
5. Present one evidenced strength when available and at most two actionable improvements, with jump-to-evidence playback. Distinguish technical findings from optional performance advice. Do not assign an emotion diagnosis or an objective good/bad actor score from facial appearance.
6. Connect accept/retake/revise choices to the supervisor. Acceptance preserves the selected original. Retakes have new IDs. Changing wording, staging or camera intent creates a revision and requires updated preview/readiness; old review results cannot attach to a new attempt. An unavailable semantic provider leaves its review component visibly unavailable, with any independently completed checks labeled accurately.

## Acceptance

- Each valid take receives its own review job; corrupt media never reaches successful review.
- The product example can identify a supported label-orientation problem and show the exact evidence interval.
- A planned exit is not flagged as tracking failure; occlusion or an uncertain head view remains unknown.
- A framing error caused by the camera is not blamed on an actor who met the agreed beat.
- A delayed review after a retake remains linked to the old take.
- The actor can accept, request a shorter line or try again without losing any original footage.

Evaluate on permissioned labeled clips and human usefulness ratings. Report precision, recall, unknown coverage and first-useful-review latency. The proposed ten-second target begins when a short clip is locally available; include transfer latency separately. Run root verification, demonstrate actual recorded-media review and leave `docs/ai-director/implementation/07-take-review.md`. Update package 07 only.
