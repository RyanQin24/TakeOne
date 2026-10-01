# Astra prompt: cinematic movement upgrade

Task prompt for GPT-6 Astra working in `C:\TakeOne`. Written to the guidance in
[Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
(OpenAI, 2026-09-11): short instructions, contextual doc pointers, completion defined up
front, and boundaries stated only where they are real. See §Notes for why this prompt is
much shorter than `ASTRA-ENGINEERING-PROMPT.md`.

---

## The prompt

Make TAKE ONE's camera work cinematic. The rig can already shoot compound curves well; the
shot vocabulary cannot express them. Close that gap.

`docs/cinematic-upgrade-2026-09-14.md` is the audit behind this task. It has the measured
motion envelope, the five structural causes, the proposed four-layer shot schema, and the
work ordered by leverage. Read it first — the rest of the repository you can navigate as
needed.

Implement all eight items in that document's §8. They are ordered so each one makes the
next easier; do them in order, and do not stop after the first working implementation.

### What done means

Done is all eight, each demonstrated in the running app:

1. **Additive aim channels.** `previs/program.py:aim_offsets()` sums contributions instead of
   selecting one. Handheld texture composes with pan, tilt, roll and any route. Prove it by
   compiling a shot that has both an arc and handheld drift, which is impossible today.
2. **Per-channel keyframe lists.** Camera height, aim, lens, light and cart pace each carry
   their own timing. The shared `rise_start`/`rise_end` window is gone. Existing saved
   settings still load and still compile to the same frames — show that, don't assume it.
3. **Compound routes in the catalog.** Spiral, S-curve, arc-into-push, pass-by and the
   three-beat oner become selectable presets that generate their own polylines. A director
   should not have to hand-draw a path to get a curve. Amortise the ~5.5 s arm setup across a
   sequence so shots under 2 s become reachable.
4. **Light arm timeline.** Independent target and independent height keyframes, decoupled
   from the camera's. If the NEEWER BR60 turns out to have no electrical control path, record
   that in `configs/rig.json` evidence and ship position-only.
5. **Cart velocity profiles with breath.** Pre-roll and post-roll holds, S-ramped entry and
   exit, no constant-acceleration plateau. Command quantisation already imposes part of this;
   make it explicit and symmetric.
6. **Route the raised ceilings without raising them.** Pace and arm-rate limits become
   configuration read from the commissioning path rather than constants, so measured evidence
   can lift them later. **Leave every limit at its current value.** Do not raise
   `speed_m_s` past 0.35 or the arm trajectory rate past 0.42 rad/s in this task.
7. **Reposition primitive.** `previs/reposition.py` plans turn-in-place using reverse on a
   cart where `reverse_enabled` is false. Replace it with a forward-only manoeuvre, or report
   inter-shot timing as a lower bound. Either is acceptable; silently optimistic timing is not.
8. **Product-only shot family.** Shots with no human subject: highlight walk, macro pass-by,
   orbit-around, foreground-occlusion reveal, negative-space drift. These need a target that
   is a point or a spline rather than an actor.

For each item, the observable result is a shot a director can select and preview that they
could not select before. A refactor that compiles but changes nothing a user can see is not
that item finished.

### Boundaries

One hard line: **no hardware activation, and no motion limit gets a new number.** Items 4
through 7 touch real motion policy. Build the mechanism, keep the values, and route them
through the existing commissioning gates so they can be lifted later with measured evidence.

Everything else is yours to decide. Choose the schema details, the preset names, the file
layout, and where new modules belong. Where the audit document proposes a design and the
code suggests a better one, follow the code and say why in your summary. If an item turns
out to be wrong — if `aim_offsets` cannot sensibly be additive, or per-channel keyframes
break a contract worth keeping — say so with the evidence and move to the next item rather
than forcing it.

The local suite (`scripts/TakeOne.ps1 -Command test`) uses disposable fixtures and touches
no hardware. Run it, fix what your change breaks, and rerun without checking in at each
step. The compiler is likewise safe to run as much as you want: `mode: "path"` with a
polyline through `compile_path` costs nothing and is the fastest way to test a geometry
idea.

### Two traps from the audit

Keep routes clear of the subject when you test aim quality. An earlier pass of this audit
measured 83° of aim error on a straight line and nearly concluded the solver was broken; the
paths ran through the actor at the origin. Same line with proper standoff: 0.29°.

Budget the 2.2-second curvature slew. Each wheel command may change by 0.01 per 200 ms tick,
so reversing curvature takes 2.2 s during which the cart passes through straight. Design
S-curves around that rather than against it — it is a hardware fact, not a bug.

### Finish with

The shots a director can now select that they could not before, the design decisions you made
that the audit document did not, anything in items 1–8 you found to be wrong, and what
remains blocked on hardware measurement. Update `docs/cinematic-upgrade-2026-09-14.md` §8 to
reflect what actually shipped.

---

## Notes on this prompt

Kept deliberately short, per the article. Three specific choices worth flagging, since the
older `ASTRA-ENGINEERING-PROMPT.md` does the opposite of each:

**Completion is defined before work starts.** The article's clearest warning is that Astra
"can feel more tentative about when to stop" and "may reach a first implementation and come
back for your review while there's still work to do." This prompt names all eight items, says
what observable result each produces, and says explicitly not to stop after the first. It also
avoids requiring a review checkpoint, which the article notes "will pull the model toward an
earlier stopping point."

**Boundaries are stated once, where they are real.** The article notes that strong ask-first
language written for earlier models can make Astra "stop work where you'd actually be happy
for it to continue." So there is exactly one prohibition here — no hardware, no new limit
values — and an explicit grant for the local test suite and the compiler. Schema shape, naming
and file layout are handed over rather than constrained.

**Docs are pointed to contextually.** The article's bad example is "before every edit, read
architecture.md, database.md, and deployment.md." `ASTRA-ENGINEERING-PROMPT.md` opens with
"Read root AGENTS.md, README.md, the relevant architecture and task prompt, and the actual
implementation/tests," which is that pattern. This prompt names one document, because that
document contains the measurements, and lets Astra find the rest.

Also omitted on purpose: instructions to write tests, run verification, and review the diff.
The article states Astra does these unprompted, and `AGENTS.md` already carries the repository
conventions that apply to every change. Repeating them here would spend context without
changing behaviour.

`ASTRA-ENGINEERING-PROMPT.md` is worth re-auditing against the same article — its fifteen
paragraphs of prohibitions were written for a model that needed them.
