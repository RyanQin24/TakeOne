# 03 — Time-coded timeline and 3D rehearsal

Implement work package 03 in `C:\TakeOne`. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, `docs/ai-director/timeline-example.md`, `docs/arm-movement-design.md`, `docs/architecture-review-2026-09-12.md`, and package 01/02 records. Follow shared rules. Dependencies: 01 and 02.

## Outcome

One accepted shot timeline explains what happens at 0:01–0:04 and drives the existing 3D rehearsal. Actor action, spoken line, camera framing, derived phone-arm movement, cart movement and light aim agree. The user can scrub and revise it without generating a video or rebuilding the robot model.

## Implement

1. Extend the shot contract with synchronized actor, dialogue, camera, cart, light, recording-handle and edit/effect tracks. Use half-open integer-time ranges, explicit time domains, semantic triggers and timing tolerances. Validate references, overlapping incompatible goals and duration constraints. Keep per-shot time separate from production edit time.
2. Replace the relevant hard-coded actor target/cue assumptions with scene/beat inputs through the existing planning pipeline. Represent simple actor proxies and named marks. Preserve presets through explicit data where useful; do not keep a second hidden planning path.
3. Translate framing/lighting intent into geometry and bounded IK using existing model/tool transforms. Distinguish desired from achieved pose. Add acceptance for full tool-position residuals as well as aim, joint continuity and trajectory constraints; the existing review documents why a playable preview alone is insufficient. Tolerances belong to declared shot intent and qualification, not values loosened just to make a test pass.
4. Preserve the base's corrected orientation, phone-front/light-rear arrangement, original upper model and named wrist-roll identities. Favor feasible arm motion before base turning. A rear light mount does not give arbitrary backlight placement; differential drive cannot strafe.
5. Render synchronized timeline lanes, actor instructions, camera preview and an overhead view using the existing app/assets. Show plain-language infeasibility and explicit revisions. Include preview-affecting optics/tool/configuration in plan identity rather than leaving hidden view settings outside the accepted plan.
6. Compile offline when intent changes and cache by revision/input hashes. Do not call full-shot IK on every camera frame. Simulate starting, settling, continuous motion and ending; a shot cut cannot teleport the rig to its next setup.

## Acceptance

- Scrubbing a boundary time selects the correct half-open beat with consistent actor/dialogue/camera/light views.
- The product example can render a stationary profile and a separately accepted arm-follow profile.
- A stair example requires path height and transforms; the arm's tilt follows geometry, not a rule that downstairs means tilt up.
- Unreachable positions produce visible achieved residuals and cannot become physically executable.
- Multi-shot setup changes include explicit reposition/settle requirements rather than discontinuous physical motion.
- Recompiling the same accepted input gives equivalent results and provenance; editing an input invalidates its cached acceptance.

Use meaningful geometric regression fixtures, run root verification and inspect the served simulator. Do not change active cart commissioning configuration or enable physical replay. Record work and evidence in `docs/ai-director/implementation/03-timeline-previs.md`, then update package 03.
