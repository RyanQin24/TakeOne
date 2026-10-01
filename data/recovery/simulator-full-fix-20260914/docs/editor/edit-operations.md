# Edit operations

An operation is a **decision**, not an effect. It says what should change and why, in terms
the product can explain out loud. `reducer.apply` is the only thing that turns an operation
into state, and it is pure: no file is read, no process starts, no model is called.

```
EditOperation  ──►  reducer.apply(state, op)  ──►  (ProjectState', JsonPatch)
```

## Shape

```python
EditOperation(
    operation_id,        # canonical UUID
    type,                # OperationType, a closed set
    target,              # typed discriminated reference
    parameters,          # validated against this type's schema at construction
    public_explanation,  # <= 180 chars, shown in the interface
    metadata,            # provenance: planner, model, analysis digests
    sequence,            # assigned on append
    phase,               # derived from the type unless stated
    status,              # PLANNED | EXECUTING | COMPLETED | FAILED | CANCELLED
    created_utc, executed_utc,
)
```

Parameters are validated **when the operation is constructed**, against `SCHEMAS[type]`.
An operation with an unknown parameter, a missing required one, or a value outside its
range cannot be built, so it can never be appended, persisted or replayed. This is the
split the whole system rests on:

- **`ValidationError`** — the request is malformed. Wrong parameters, wrong ranges, wrong
  target kind. Over HTTP this is `400`.
- **`OperationError`** — the request is well formed but does not fit *this* state. The clip
  would overlap, the trim would leave the media, the transition is longer than its clip.
  Over HTTP this is `409`.

## Targets

`Target` is a discriminated reference, never a free string:

| kind | requires | used by |
| --- | --- | --- |
| `project` | — | imports, intent, markers, audio, templates, finalize |
| `media` | `media_id` | analysis, selection |
| `track` | `track_id` | adding clips, transitions, beat alignment |
| `clip` | `clip_id` | trims, retiming, colour, effects |
| `effect` | `clip_id`, `instance_id` | effect updates and removal |
| `audio` | `event_id` | volume, ducking |

`TARGET_KIND_FOR` pins each operation type to exactly one target kind, checked at
construction. The reducer then checks that the referent actually exists.

## The closed set

| Phase | Types |
| --- | --- |
| understand | `IMPORT_MEDIA` `ANALYZE_CLIP` `SET_INTENT` |
| select | `SELECT_CLIP` `REJECT_CLIP` |
| structure | `ADD_TRACK` `ADD_CLIP` `REMOVE_CLIP` `MOVE_CLIP` `SPLIT_CLIP` |
| rhythm | `TRIM_CLIP` `APPLY_SPEED_CURVE` `FREEZE_FRAME` `APPLY_TRANSITION` `ALIGN_CUT_TO_BEAT` |
| color | `APPLY_COLOR_CORRECTION` `MATCH_COLOR` `APPLY_CREATIVE_LOOK` |
| effects | `ADD_EFFECT` `UPDATE_EFFECT` `REMOVE_EFFECT` `APPLY_TEMPLATE` |
| audio | `ADD_MARKERS` `ADD_MUSIC` `ADD_SFX` `SET_VOLUME` `APPLY_AUDIO_DUCK` |
| finalize | `SET_PHASE` `FINALIZE_TIMELINE` |

## Rules the reducer enforces

These are the ones worth knowing before writing a planner, because they are why a plan gets
rejected.

**Frame grids, twice.** Timeline positions snap to the project's frame grid. Source in and
out points snap to the *media's* frame grid, because a cut between two frames does not
exist. This is why `run_milestone1.py` can assert the rendered frame count *exactly* rather
than within a frame.

**Ripple is the default.** Trimming, removing or retiming a clip moves everything after it,
so a timeline never grows a gap it did not ask for. Pass `ripple: false` to leave the rest
alone.

**A speed curve is fitted, not applied.** `APPLY_SPEED_CURVE` takes a *shape*. The reducer
scales it so it consumes exactly the clip's source span, then the clip's timeline duration
follows from that. `∫rate dt == source span` is an invariant of the state, checked in
`Clip.__post_init__`, not a hope.

**A freeze is one frame played slowly.** `FREEZE_FRAME` splits the clip and inserts a
one-frame clip whose curve rate is `frame / hold`. There is no special "still" state, so
trimming, rippling, grading and rendering need no special case.

**A transition is an overlap.** `APPLY_TRANSITION` pulls the incoming clip and everything
after it back by the transition's duration. `Track` therefore permits overlap, and
`Timeline` requires that every overlap be accounted for by a transition of exactly that
length. The rule lives on the timeline because only the timeline knows about transitions.

**Beat alignment is a roll edit.** `ALIGN_CUT_TO_BEAT` moves the cut and holds the
programme length: the outgoing clip's out point and the incoming clip's in point move
together. It is refused on a retimed clip — on a curve, the source consumed by an extra
second of timeline depends on *where* that second sits, so a roll would either change the
length or silently reshape the ramp. Align cuts before retiming; that is the order the
rhythm phase works in anyway.

**A template applies nothing by itself.** `APPLY_TEMPLATE` is an annotation in the log. A
template's effect is the operations it emits, which follow it.

## Replay, undo and the patch contract

`reducer.fold(empty, operations)` is the film. Nothing else is.

- **Replay** is folding a prefix of the log.
- **Undo** is truncating the log and refolding — not an inverse-operation table.
- **The patch** returned beside each new state is the structural difference between the two
  wire documents. It is what the interface applies to its mirror.

`run_milestone1.py` asserts that applying the published patches to an empty project
reproduces the folded state byte for byte. That test is the reason the interface can claim
its animation reflects a real project mutation.
