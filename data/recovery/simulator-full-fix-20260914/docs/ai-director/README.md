# AI Director delivery pack

Date: 2026-09-12. Status: **package 01 is implemented and verified locally**; package 02 is blocked on live provider acceptance; a narrow offline voice contribution to package 05 is in progress; all other packages and every release profile remain planned. This is not a complete AI filming product or hardware qualification.

This is the implementation handoff for the latest user decisions: time-coded actor/camera/light directions, help writing and rehearsing dialogue, quiet recording, review after every take, TakeOne-owned editing, and optional generated effects. It refines the [architecture decision](../ai-director-decision-2026-09-12.md) and replaces the coarse milestone list in the [earlier build outline](../ai-director-build-plan-2026-09-12.md) for task ordering. Existing software and hardware qualification remain authoritative for what currently works.

## Start here

1. Read the [delivery plan](delivery-plan.md) for scope, dependencies, milestones, release gates and ownership.
2. Read the [implementation rules](implementation-rules.md). Every task prompt incorporates these rules.
3. Use the shared [Astra engineering prompt](../requests/ASTRA-ENGINEERING-PROMPT.md) with one numbered task. [01 - Session foundation](implementation/01-session-foundation.md) and the local software for [02 - Creative planning](implementation/02-creative-planning.md) are implemented. Package 02 still needs live provider acceptance. [05 - Rehearsal voice](implementation/05-rehearsal-voice.md) records a partial offline contribution only; package 03 remains planned.
4. Complete one work package and record its evidence before moving to a dependent package. Do not paste all prompts into one unbounded implementation task.

The prompts instruct the coding agent to implement their package, connect it to the existing application, test it and document real limitations. They do not instruct it to activate hardware, upload media, spend money or deploy the site merely because a document describes those capabilities.

## Work packages

| ID | Implement | Prompt |
|---|---|---|
| 01 | Typed contracts, session state, durable jobs and capability reporting | [Session foundation](prompts/01-session-foundation.md) |
| 02 | Creative brief, filming skills, script and dialogue help | [Creative planning](prompts/02-creative-planning.md) |
| 03 | Time-coded shot timeline and existing 3D simulator integration | [Timeline and previs](prompts/03-timeline-previs.md) |
| 04 | Actual camera input, selected actor and observable scene evidence | [Camera and scene](prompts/04-camera-scene.md) |
| 05 | Rehearsal coaching and conversational voice; partial offline voice slice in progress | [Prompt](prompts/05-rehearsal-voice.md) / [partial evidence](implementation/05-rehearsal-voice.md) |
| 06 | Acknowledged recording and durable original takes | [Recording](prompts/06-recording.md) |
| 07 | Review each recorded take and guide the next attempt | [Take review](prompts/07-take-review.md) |
| 08 | Select, cut, caption and export original footage | [Editing](prompts/08-editing.md) |
| 09 | Selected-shot effects through an explicit provider integration | [Generated effects](prompts/09-generated-effects.md) |
| 10 | Qualified connection to physical cart and arm execution | [Robot integration](prompts/10-robot-integration.md) |
| 11 | Integrated release evaluation, model economics and usability | [Release evaluation](prompts/11-release-evaluation.md) |

Supporting material:

- [Worked timeline and review example](timeline-example.md)
- [Provider research and integration decisions](provider-decisions.md)
- [Machine-readable dependencies and status](work-packages.json)

The first complete product milestone is **brief → preview → rehearsal → real stationary take → review → original edit/export**. It requires 01–08 and the core profile of 11. Generated effects (09) and physical motion (10) each add a separate release profile. Their absence must be visible; it does not prevent completion of the original-footage workflow.

Packages 01, 02 and the partial package 05 contribution have implementation evidence in the manifest. Package 05 remains incomplete because visual coaching, real camera and recorder integration, real take review and live-provider acceptance are outside the verified slice. Update further statuses only from actual implementation evidence. The numbered plans do not provide hardware approval.
