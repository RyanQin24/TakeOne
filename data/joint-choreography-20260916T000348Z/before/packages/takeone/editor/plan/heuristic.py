"""Offline planner: score takes, cut a short film, grade it, and explain each step.

No network, no pixels. Every decision is an EditOperation the reducer already knows.
"""

import uuid

from ..effects import EFFECTS
from ..library import ensure_track_operation, place_clip_operation, video_track
from ..operations import EditOperation, OperationType, Target
from ..state import EPSILON_S

ANALYZER_ID = "heuristic"
ANALYZER_VERSION = 1
MIN_KEEP_S = 0.8
MIN_TAKE_S = 1.2
TRANSITION_S = 0.35
REJECT_SCORE = 0.18

SLOTS = ("Opening", "Setup", "Rise", "Turn", "Landing")


def _id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _clamp(value):
    return max(0.0, min(1.0, float(value)))


def _prompt(state):
    return (state.intent.prompt if state.intent else "").lower()


def _words(*needles, text):
    return any(needle in text for needle in needles)


def score_take(item):
    """Probe-only score in 0..1. Higher means more useful as a picture cut."""
    probe = item.probe
    fps = probe.fps
    duration = probe.duration_s
    megapixels = (probe.width * probe.height) / 1_000_000
    cinema = (
        1.0 if abs(fps - 24.0) < 1.2 or abs(fps - 25.0) < 0.2 else (0.78 if abs(fps - 30.0) < 0.2 else 0.62)
    )
    length = _clamp(duration / 8.0)
    resolution = _clamp(megapixels / 8.0)
    score = _clamp(0.38 * cinema + 0.36 * length + 0.26 * resolution)
    signals = {
        "cinema": round(cinema, 4),
        "duration": round(length, 4),
        "resolution": round(resolution, 4),
    }
    reason = (
        f"{probe.width}×{probe.height} · {fps:.0f} fps · {duration:.1f}s — "
        f"{'cinematic motion' if cinema >= 0.95 else 'usable motion'}."
    )
    return score, signals, reason[:240]


def _palette(prompt):
    """Looks, cuts and extra effects from the written intent."""
    mysterious = _words("myster", "noir", "dark", "shadow", "secret", text=prompt)
    luxury = _words("luxury", "expensive", "premium", "gold", "elegant", "rich", text=prompt)
    powerful = _words("power", "impact", "punch", "epic", "bold", "strong", text=prompt)
    dreamy = _words("dream", "soft", "haze", "romance", "gentle", text=prompt)
    action = _words("action", "fast", "chase", "fight", text=prompt)

    opening = "luxury_warm" if luxury or mysterious else ("dream_reveal" if dreamy else "clean_natural")
    middle = "noir_contrast" if mysterious else ("teal_orange" if action else opening)
    ending = "action_impact" if powerful or action else ("spectrum_entrance" if luxury else opening)
    first_cut = "dip_to_black" if mysterious or luxury else "crossfade"
    last_cut = "flash" if powerful or action else ("whip" if action else "crossfade")
    return {
        "opening_look": opening,
        "middle_look": middle,
        "ending_look": ending,
        "first_cut": first_cut,
        "middle_cut": "crossfade",
        "last_cut": last_cut,
        "fade": True,
    }


def _take_window(duration_s, budget_s):
    """A usable in/out that stays inside the media."""
    take = min(duration_s, max(MIN_TAKE_S, budget_s))
    take = min(take, duration_s)
    if take >= duration_s - EPSILON_S:
        return 0.0, duration_s
    start = min(duration_s - take, duration_s * 0.12)
    return start, start + take


def _placed_media(state):
    found = set()
    for track in state.timeline.tracks:
        for clip in track.clips:
            found.add(clip.media_id)
    return found


def _selected(state):
    items = []
    for item in state.media.values():
        entry = state.selection.get(item.media_id)
        if entry is not None and entry.state == "selected":
            items.append(item)
    return items


def _look_for(palette, index, count):
    if index == 0:
        return palette["opening_look"]
    if index == count - 1:
        return palette["ending_look"]
    return palette["middle_look"]


def _cut_for(palette, index, count):
    if index == 0:
        return palette["first_cut"]
    if index == count - 2:
        return palette["last_cut"]
    return palette["middle_cut"]


def _slot_name(index, count):
    if count == 1:
        return SLOTS[0]
    if index == 0:
        return SLOTS[0]
    if index == count - 1:
        return SLOTS[-1]
    if count == 3 and index == 1:
        return SLOTS[2]
    return SLOTS[min(index, len(SLOTS) - 2)]


class HeuristicPlanner:
    """One operation at a time, always from the current folded state."""

    def next_operation(self, state):
        if state.finalized or not state.media:
            return None

        unanalyzed = [
            item for item in state.media.values() if ANALYZER_ID not in state.analysis.get(item.media_id, {})
        ]
        if unanalyzed:
            if state.phase != "understand":
                return self._phase("understand", "Reading the new takes.")
            return self._analyze(unanalyzed[0])

        undecided = [
            item
            for item in state.media.values()
            if state.selection.get(item.media_id) is None
            or state.selection[item.media_id].state in ("pending", "analyzing")
        ]
        if undecided:
            if state.phase != "select":
                return self._phase("select", "Choosing which takes belong in the film.")
            return self._decide(state, undecided[0])

        selected = _selected(state)
        if not selected:
            return self._phase("complete", "Nothing usable to cut.") if state.phase != "complete" else None

        if video_track(state) is None:
            if state.phase != "structure":
                return self._phase("structure", "Opening a picture track.")
            return ensure_track_operation()

        missing = [item for item in selected if item.media_id not in _placed_media(state)]
        if missing:
            if state.phase != "structure":
                return self._phase("structure", "Laying the selected takes on the timeline.")
            return self._place(state, missing[0], selected)

        track = video_track(state)
        clips = list(track.clips) if track else []
        if state.phase == "structure":
            return self._phase("rhythm", "Setting the cuts and the pace.")

        if state.phase == "rhythm":
            pending = self._next_transition(state, clips)
            if pending:
                return pending
            if not any(item.kind == "slot" for item in state.timeline.markers) and clips:
                return self._markers(clips)
            return self._phase("color", "Grading the picture to the intent.")

        if state.phase in ("understand", "select"):
            return self._phase("structure", "Laying the selected takes on the timeline.")

        if state.phase == "color":
            pending = self._next_grade(state, clips)
            if pending:
                return pending
            return self._phase("effects", "Adding the last picture finishes.")

        if state.phase == "effects":
            pending = self._next_effect(state, clips)
            if pending:
                return pending
            return self._phase("finalize", "Checking the cut holds together.")

        if state.phase == "finalize":
            return self._phase("complete", "The cut is ready to watch.")

        return None

    def _phase(self, phase, explanation):
        return EditOperation(
            operation_id=str(uuid.uuid4()),
            type=OperationType.SET_PHASE,
            target=Target.project(),
            parameters={"phase": phase},
            public_explanation=explanation,
            metadata={"source": "heuristic"},
        )

    def _analyze(self, item):
        score, signals, reason = score_take(item)
        return EditOperation(
            operation_id=str(uuid.uuid4()),
            type=OperationType.ANALYZE_CLIP,
            target=Target("media", media_id=item.media_id),
            parameters={
                "media_id": item.media_id,
                "analyzer_id": ANALYZER_ID,
                "analyzer_version": ANALYZER_VERSION,
                "result": {
                    "score": score,
                    "signals": signals,
                    "reason": reason,
                    "duration_s": item.probe.duration_s,
                    "width": item.probe.width,
                    "height": item.probe.height,
                    "fps": item.probe.fps,
                },
            },
            public_explanation=f"Read {item.name[:60]} — {reason}"[:180],
            metadata={"source": "heuristic"},
        )

    def _decide(self, state, item):
        analysis = state.analysis.get(item.media_id, {}).get(ANALYZER_ID, {}).get("result", {})
        score = float(analysis.get("score") or score_take(item)[0])
        signals = analysis.get("signals") or score_take(item)[1]
        reason = analysis.get("reason") or score_take(item)[2]
        keep = item.probe.duration_s >= MIN_KEEP_S and score >= REJECT_SCORE
        others = [media for media in state.media.values() if media.media_id != item.media_id]
        if not keep and not others:
            keep = True
            reason = "Only take on the bench — keeping it so there is a picture."
        if keep:
            return EditOperation(
                operation_id=str(uuid.uuid4()),
                type=OperationType.SELECT_CLIP,
                target=Target("media", media_id=item.media_id),
                parameters={
                    "media_id": item.media_id,
                    "score": _clamp(score),
                    "signals": {key: _clamp(value) for key, value in signals.items()},
                    "reason": reason[:240],
                },
                public_explanation=f"Kept {item.name[:40]} — {reason}"[:180],
                metadata={"source": "heuristic"},
            )
        return EditOperation(
            operation_id=str(uuid.uuid4()),
            type=OperationType.REJECT_CLIP,
            target=Target("media", media_id=item.media_id),
            parameters={
                "media_id": item.media_id,
                "score": _clamp(score),
                "signals": {key: _clamp(value) for key, value in signals.items()},
                "reason": f"Too thin to cut: {reason}"[:240],
            },
            public_explanation=f"Held {item.name[:40]} out of the cut."[:180],
            metadata={"source": "heuristic"},
        )

    def _place(self, state, item, selected):
        index = [media.media_id for media in selected].index(item.media_id)
        count = len(selected)
        target = state.intent.target_duration_s if state.intent else 12.0
        budget = max(MIN_TAKE_S, target / max(count, 1))
        source_start, source_end = _take_window(item.probe.duration_s, budget)
        slot = _slot_name(index, count)
        label = slot
        explanation = {
            0: f"Opened on {item.name[:40]} as a slow hold.",
            count - 1: f"Landed on {item.name[:40]} so the ending hits.",
        }.get(index, f"Cut {item.name[:40]} as the {slot.lower()}.")
        return place_clip_operation(
            state,
            item.media_id,
            name=label,
            source_start_s=source_start,
            source_end_s=source_end,
            explanation=explanation[:180],
        )

    def _next_transition(self, state, clips):
        if len(clips) < 2:
            return None
        declared = {(item.from_clip_id, item.to_clip_id) for item in state.timeline.transitions}
        palette = _palette(_prompt(state))
        track = video_track(state)
        for index, (outgoing, incoming) in enumerate(zip(clips, clips[1:])):
            if (outgoing.clip_id, incoming.clip_id) in declared:
                continue
            duration = TRANSITION_S
            if (
                outgoing.timeline_duration_s <= duration + 0.08
                or incoming.timeline_duration_s <= duration + 0.08
            ):
                continue
            gap = incoming.timeline_start_s - outgoing.timeline_end_s
            if gap < -1e-6 or gap > state.frame_s() + 1e-6:
                continue
            effect_id = _cut_for(palette, index, len(clips))
            spec = EFFECTS.latest(effect_id)
            names = {
                "dip_to_black": "Dipped to black so the next idea arrives as a reveal.",
                "flash": "Flashed the cut so the ending feels like an impact.",
                "whip": "Whipped across the cut to carry motion.",
                "crossfade": "Dissolved the join so the cut does not click.",
            }
            return EditOperation(
                operation_id=str(uuid.uuid4()),
                type=OperationType.APPLY_TRANSITION,
                target=Target("track", track_id=track.track_id),
                parameters={
                    "transition_id": _id("tr"),
                    "effect_id": spec.id,
                    "effect_version": spec.version,
                    "from_clip_id": outgoing.clip_id,
                    "to_clip_id": incoming.clip_id,
                    "duration_s": duration,
                },
                public_explanation=names.get(effect_id, f"Joined the shots with {spec.name}.")[:180],
                metadata={"source": "heuristic"},
            )
        return None

    def _markers(self, clips):
        markers = []
        for index, clip in enumerate(clips):
            markers.append(
                {
                    "time_s": clip.timeline_start_s,
                    "strength": 1.0,
                    "label": clip.label or _slot_name(index, len(clips)),
                }
            )
        return EditOperation(
            operation_id=str(uuid.uuid4()),
            type=OperationType.ADD_MARKERS,
            target=Target.project(),
            parameters={"markers": markers, "kind": "slot"},
            public_explanation="Marked the story beats on the timeline.",
            metadata={"source": "heuristic"},
        )

    def _next_grade(self, state, clips):
        palette = _palette(_prompt(state))
        for index, clip in enumerate(clips):
            if clip.color.look_id:
                continue
            look_id = _look_for(palette, index, len(clips))
            spec = EFFECTS.latest(look_id)
            intensity = 0.82 if index in (0, len(clips) - 1) else 0.7
            names = {
                "luxury_warm": "Warmed the shot so it feels expensive, not bright.",
                "noir_contrast": "Dropped the colour so the mystery sits in the shadows.",
                "action_impact": "Pushed contrast so the ending hits.",
                "dream_reveal": "Lifted the blacks for a soft reveal.",
            }
            return EditOperation(
                operation_id=str(uuid.uuid4()),
                type=OperationType.APPLY_CREATIVE_LOOK,
                target=Target("clip", clip_id=clip.clip_id),
                parameters={"look_id": spec.id, "intensity": intensity},
                public_explanation=names.get(look_id, f"Applied {spec.name}.")[:180],
                metadata={"source": "heuristic"},
            )
        reference = clips[0] if clips else None
        if reference:
            for clip in clips[1:]:
                if clip.color.matched_to:
                    continue
                return EditOperation(
                    operation_id=str(uuid.uuid4()),
                    type=OperationType.MATCH_COLOR,
                    target=Target("clip", clip_id=clip.clip_id),
                    parameters={
                        "reference_clip_id": reference.clip_id,
                        "exposure_stops": 0.04,
                        "temperature_k": 40.0,
                        "tint": 0.02,
                        "contrast": 1.02,
                    },
                    public_explanation="Matched this shot to the opening so the grade holds.",
                    metadata={"source": "heuristic"},
                )
        return None

    def _next_effect(self, state, clips):
        if not clips:
            return None
        palette = _palette(_prompt(state))
        first, last = clips[0], clips[-1]
        if palette["fade"] and not any(item.effect_id == "fade" for item in first.effects):
            spec = EFFECTS.latest("fade")
            return EditOperation(
                operation_id=str(uuid.uuid4()),
                type=OperationType.ADD_EFFECT,
                target=Target("clip", clip_id=first.clip_id),
                parameters={
                    "instance_id": _id("fx"),
                    "effect_id": spec.id,
                    "effect_version": spec.version,
                    "parameters": {"type": "in", "duration_s": 0.7, "start_s": 0.0},
                },
                public_explanation="Faded the opening in from black.",
                metadata={"source": "heuristic"},
            )
        if first is not last and not any(item.effect_id == "fade" for item in last.effects):
            spec = EFFECTS.latest("fade")
            local = max(0.0, last.timeline_duration_s - 0.55)
            return EditOperation(
                operation_id=str(uuid.uuid4()),
                type=OperationType.ADD_EFFECT,
                target=Target("clip", clip_id=last.clip_id),
                parameters={
                    "instance_id": _id("fx"),
                    "effect_id": spec.id,
                    "effect_version": spec.version,
                    "parameters": {"type": "out", "duration_s": 0.5, "start_s": local},
                },
                public_explanation="Faded the landing out so the ending resolves.",
                metadata={"source": "heuristic"},
            )
        return None
