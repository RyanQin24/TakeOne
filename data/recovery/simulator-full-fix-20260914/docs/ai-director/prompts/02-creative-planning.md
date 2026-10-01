# 02 — Creative brief, filming skills and dialogue help

Implement work package 02 in `C:\TakeOne`. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, `docs/ai-director/delivery-plan.md`, `docs/ai-director-decision-2026-09-12.md` and package 01's implementation record. Follow the shared rules. Dependency: package 01's contracts and session owner are implemented; verify this from code and evidence before proceeding.

## Outcome

The user describes a short video in ordinary language. The Director helps turn it into an editable brief, speakable script and structured shot proposals that respect the actual rig. It can suggest what to say during a product introduction without inventing product claims.

## Implement

1. Add one explicit reasoning-provider adapter for the selected structured-planning baseline in the architecture decision. Verify current official API contracts and account access when integrating. Keep keys server-side, bound time/cost/retries and record model/version/skill/input identity. No dependence on Astra running interactively in Codex.
2. Implement three small versioned filming skills: static product presentation, dialogue coverage, and reaction/eyeline. Each skill declares needed facts, intended audience/tone, speaking beats, observable cues, supported shot primitives and limitations. Skills are curated data/prompt templates with schema checks, not executable instructions granting more tools.
3. Expand a rough brief into scene and shot proposals with actor IDs, locations/marks, dialogue alternatives, camera/lighting intention, estimated timing and editing intent. Ask only consequential missing questions; retain unresolved facts explicitly. Keep suggestions editable and explain specialized film terms in user language.
4. Implement line assistance. Offer two or three concise alternatives, support shortening or changing tone, preserve the user's voice and actual product facts, and record the actor's choice. Revising a chosen line creates a new script/shot revision and invalidates dependent acceptance.
5. Use the capability snapshot to constrain proposals. Preserve infeasible requests with an explanation or an explicit proposed revision; do not silently replace an orbit, zoom, cart strafe or stair path. The local planner remains the authority on physical feasibility.
6. Add the brief/script/shot-card flow to the existing app. Show estimated timing as proposed. Package 03 will make the full synchronized preview; do not build another simulator or generate a video as a planning prerequisite.

## Acceptance

- A product brief with no product specifications produces useful structural/wording help without invented benefits.
- The user's Astra-versus-Claude argument premise becomes feasible coverage and dialogue beats, with fictional claims distinguished from facts about the tools.
- An ambiguous left/right direction is resolved to a named mark or remains pending; it is not guessed into a motor-space direction.
- Changing a line updates its revision and invalidates the prior preview/record acceptance.
- Malformed provider output, timeout and capability mismatch return visible errors; fixture mode is explicit.
- A prompt embedded in source material cannot expand the Director's tool authority.

Test provider parsing and failure handling offline with recorded fixtures. A real model demonstration is opt-in with configured credentials and budget; if unavailable, report that integration as unverified while completing independent code. Run root verification, inspect the actual UI, and write `docs/ai-director/implementation/02-creative-planning.md`. Update package 02 only.
