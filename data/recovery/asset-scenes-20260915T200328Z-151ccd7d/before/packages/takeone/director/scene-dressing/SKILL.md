---
name: takeone-scene-dressing
description: Design layered, practical scenes using an installed asset catalog and independent performer blocking.
---

# TAKE ONE: scene dressing and ensemble blocking

This skill is an additive draft. The application must explicitly load it alongside
its existing Director and shot-design skills. Installing the file alone does not
activate it. Use the actual local shot schema; do not invent executable fields.

## Start with story, available space, and available people

Identify the scene's change: what the protagonist wants, what interrupts that
intention, and what the audience learns by the end. Build around that change.
An empty frame can be intentional; complexity is not a score based on prop count.

Read the venue inventory, actor availability, measured room envelope, prohibited
areas, existing film rules, current marks, and current robot capabilities. Maintain
three distinct states for scene elements: physically present, proposed for setup,
and virtual-only visualization. A downloaded 3D model does not establish that its
physical counterpart or an extra performer is available. Never quietly promote
virtual-only props into collision-qualified physical obstacles or available cast.

## Find assets instead of inventing identifiers

Ask the application's asset search tool for a small candidate set using semantic
nouns: chair, desk, cup, person, plant, bag. Inspect the returned source, license,
actual animation clip names, byte cost, and dimension evidence. Resolve a concrete
installed asset_id and sha256 before committing a production. Use existing
procedural objects when explicitly selected, not as a silent replacement for a
missing imported object. Record a missing-asset request when retrieval fails.

Do not request paid endpoints, download during a take, fetch arbitrary URLs,
execute asset scripts, or send the full asset catalog into every model prompt.
The current toolkit's search is lexical, not an embedding model. Use multiple
clear query terms rather than expecting visual semantic retrieval to exist.

## Compose relationships and depth

Describe foreground, action plane, and background only where they help the shot.
Give each hero prop a purpose, owner, support surface, and persistence rule. Give
background dressing a reason to exist in the location. Keep negative space where
it carries meaning or supports an entrance. Avoid filling every available area.

Prefer relationships such as cup on table, chair facing collaborator, bag beneath
chair, performer beside counter, and practical light behind the subject. Then let
the placement/compiler layer resolve transforms. Never guess that the pose solver
also understands those relationships until its executable constraint support is
verified. Keep support heights, center origins, feet anchors, and object dimensions
explicit. Do not place a cup at floor Z=0 or scale a chair to hide a framing error.

## Direct an ensemble, not copies of the lead

For each real performer, specify identity, objective, role, start mark, independent
body orientation, eyeline target, action windows, and end state. Supporting people
may react late, carry an object, wait, sit, enter, or cross a permitted background
route. Their timing must have a cause. Do not copy the lead's gaze, heading,
walking phase, or actor-follow target to every character.

Only choose animation clips actually present or explicitly retargeted and tested.
A clip called Idle does not implement a handoff, seated contact, facial emotion,
lip sync, or an eyeline target. Distinguish actionable crew directions from motion
that the current rig can actually render. Root-motion clips cannot replace the
planner's physical actor trajectory without a tested mapping.

## Build meaningful coverage

Plan what each shot contributes, not a round-robin of movement presets. An example
sequence might establish geography, show the interaction in a two-shot, isolate
a meaningful prop action, hold a reaction, and finish with a changed relationship.
Use cuts on an action or attention shift, varied shot durations, and purposeful
foreground occlusion. Prefer a stable shot when movement adds no information.

Each shot should state the beat being communicated, visible target region,
framing size, motivated motion or hold, intended focus, opening and ending frame,
audio intention, and a reason the cut belongs here. Preserve existing visibility
policies: deliberate reveals are not automatically failed continuous coverage.
Treat focus, phone lens selection, and brightness as manual where the app does.

## Preserve continuity and physical truth

Keep the same object IDs and cast IDs across coverage of a scene. Track prop
ownership, cup positions, screen state, wardrobe, entrances, eyelines, and action
progression. A new shot is not a fresh random scene layout. Save asset revisions
with the production. When changing the location, use a cut and a real setup reset,
not a robot teleport.

Render the same compiled transforms that nominal scene checks consume. Separate
visual meshes from collision proxies. Imported nominal dimensions are not venue
measurements. Request path, occlusion, target visibility, support/contact and
clearance checks actually implemented in this build; label unimplemented checks
as unverified, never passed. Do not enable follow-controller hooks or hardware
execution as part of asset work.

## Review before adding more

Ask whether each prop or person changes story, geography, depth, or interaction.
Remove clutter that hides the intended gesture or makes the physical shoot less
achievable. Check repeatability, shot-to-shot continuity, independent performer
cues, scene resource budgets, and the operator's setup guide. A rich scene can
contain three well-directed people and a few meaningful objects.
