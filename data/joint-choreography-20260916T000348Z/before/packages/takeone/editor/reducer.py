"""The fold. `apply(state, operation)` is pure, total and the only way state changes.

Every handler returns a new `ProjectState`. Nothing here reads a file, starts a process,
calls a model or knows that FFmpeg exists. That is what makes replay, undo and testing
cheap, and it is what lets a template, a human command and an LLM plan share one door.
"""

from dataclasses import replace

from .errors import OperationError, ValidationError
from .operations import EditOperation, OperationType
from .patch import diff
from .state import (
    AudioEvent,
    Clip,
    CreativeIntent,
    EffectInstance,
    Marker,
    MediaItem,
    MediaProbe,
    ProjectState,
    SelectionState,
    Timeline,
    Track,
    TransitionInstance,
)
from .timing.curve import SpeedCurve

MIN_CLIP_S = 0.02


# ---------------------------------------------------------------- helpers


def _require(condition, message, detail=None):
    if not condition:
        raise OperationError(message, detail)


def _clip_of(state, clip_id):
    try:
        return state.timeline.find_clip(clip_id)
    except KeyError:
        raise OperationError(f"Unknown clip '{clip_id}'") from None


def _put_clip(state, track, clip):
    clips = tuple(clip if item.clip_id == clip.clip_id else item for item in track.clips)
    return replace(state, timeline=state.timeline.with_track(track.with_clips(clips)))


def _shift_clips(clips, from_time_s, delta_s, exclude=()):
    """Ripple over a plain list of clips.

    Rippling works on the list, not on a `Track`, because a `Track` validates that its clips
    do not overlap. Lengthening a clip and then moving its neighbours are two halves of one
    change, and constructing a track between them would reject a state that never existed.
    """
    if delta_s == 0.0:
        return list(clips)
    moved = []
    for clip in clips:
        if clip.clip_id in exclude or clip.timeline_start_s < from_time_s - 1e-9:
            moved.append(clip)
            continue
        start = clip.timeline_start_s + delta_s
        _require(start >= -1e-9, "Rippling would move a clip before the start of the film")
        moved.append(replace(clip, timeline_start_s=max(0.0, round(start, 9))))
    return moved


def _shift_after(track, from_time_s, delta_s, exclude=()):
    return track.with_clips(_shift_clips(track.clips, from_time_s, delta_s, exclude))


def _swap(clips, clip_id, replacement):
    return [replacement if item.clip_id == clip_id else item for item in clips]


def _refit_curve(clip, source_span_s):
    if clip.speed_curve is None:
        return None
    return clip.speed_curve.fitted_to_source(source_span_s)


def _media_duration(state, media_id):
    return state.media_item(media_id).probe.duration_s


def _snap_source(state, media_id, time_s):
    """Source in and out points land on the media's own frame grid.

    A cut between two frames does not exist. Snapping here, rather than leaving it to the
    renderer, is what makes the timeline's stated duration and the rendered frame count the
    same number instead of two numbers that are usually close.
    """
    frame = state.media_item(media_id).probe.frame_s
    return round(round(time_s / frame) * frame, 9)


# ---------------------------------------------------------------- understand


def _import_media(state, operation):
    parameters = operation.parameters
    media_id = parameters["media_id"]
    _require(media_id not in state.media, f"Media '{media_id}' is already imported")
    item = MediaItem(
        media_id=media_id,
        name=parameters["name"],
        path=parameters["path"],
        sha256=parameters["sha256"],
        probe=MediaProbe.parse(parameters["probe"]),
        source_space=parameters.get("source_space", "rec709"),
        proxy_path=parameters.get("proxy_path"),
        thumbnail_path=parameters.get("thumbnail_path"),
        waveform_path=parameters.get("waveform_path"),
    )
    return replace(
        state,
        media={**state.media, media_id: item},
        selection={**state.selection, media_id: SelectionState("pending")},
    )


def _analyze_clip(state, operation):
    parameters = operation.parameters
    media_id = parameters["media_id"]
    _require(media_id in state.media, f"Unknown media '{media_id}'")
    existing = dict(state.analysis.get(media_id, {}))
    existing[parameters["analyzer_id"]] = {
        "version": parameters["analyzer_version"],
        "result": parameters["result"],
    }
    selection = dict(state.selection)
    current = selection.get(media_id)
    if current is None or current.state == "pending":
        selection[media_id] = SelectionState("analyzing")
    return replace(
        state,
        analysis={**state.analysis, media_id: existing},
        selection=selection,
    )


def _set_intent(state, operation):
    return replace(state, intent=CreativeIntent.parse(operation.parameters["intent"]))


# ---------------------------------------------------------------- select


def _select(state, operation, selected):
    parameters = operation.parameters
    media_id = parameters["media_id"]
    _require(media_id in state.media, f"Unknown media '{media_id}'")
    entry = SelectionState(
        state="selected" if selected else "rejected",
        score=parameters.get("score"),
        signals=parameters.get("signals", {}),
        reason=parameters.get("reason"),
    )
    return replace(state, selection={**state.selection, media_id: entry})


# ---------------------------------------------------------------- structure


def _add_track(state, operation):
    track_id = operation.parameters["track_id"]
    _require(
        all(track.track_id != track_id for track in state.timeline.tracks),
        f"Track '{track_id}' already exists",
    )
    track = Track(track_id, operation.parameters["kind"])
    return replace(state, timeline=state.timeline.with_track(track))


def _add_clip(state, operation):
    parameters = operation.parameters
    track_id = operation.target.track_id
    try:
        track = state.timeline.track(track_id)
    except KeyError:
        raise OperationError(f"Unknown track '{track_id}'") from None
    media_id = parameters["media_id"]
    _require(media_id in state.media, f"Unknown media '{media_id}'")
    duration = _media_duration(state, media_id)
    source_start = parameters["source_start_s"]
    source_end = parameters["source_end_s"]
    _require(source_end > source_start, "A clip's source out point must follow its in point")
    _require(source_end <= duration + 1e-6, f"Source out point exceeds the {duration:.3f}s media")
    source_start = max(0.0, _snap_source(state, media_id, source_start))
    source_end = min(_snap_source(state, media_id, source_end), duration)
    _require(source_end - source_start >= MIN_CLIP_S, "A clip must be at least one frame long")
    raw_start = parameters["timeline_start_s"]
    # Nearest-frame rounding can step backward into the previous shot when the
    # source was cut on a different grid than the project (24 fps on a 30 fps
    # timeline is the usual case). Appending must only ever snap forward.
    if raw_start + 1e-6 >= track.duration_s:
        timeline_start = state.quantize_ceil(max(raw_start, track.duration_s))
    else:
        timeline_start = state.quantize(raw_start)
    clip = Clip(
        clip_id=parameters["clip_id"],
        media_id=media_id,
        timeline_start_s=timeline_start,
        source_start_s=source_start,
        source_end_s=source_end,
        label=parameters.get("label"),
    )
    return replace(state, timeline=state.timeline.with_track(track.with_clips(track.clips + (clip,))))


def _remove_clip(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    remaining = tuple(item for item in track.clips if item.clip_id != clip.clip_id)
    track = track.with_clips(remaining)
    if operation.parameters.get("ripple", True):
        track = _shift_after(track, clip.timeline_end_s, -clip.timeline_duration_s)
    transitions = tuple(
        item
        for item in state.timeline.transitions
        if clip.clip_id not in (item.from_clip_id, item.to_clip_id)
    )
    timeline = replace(state.timeline.with_track(track), transitions=transitions)
    return replace(state, timeline=timeline)


def _move_clip(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    destination = operation.parameters.get("track_id", track.track_id)
    start = state.quantize(operation.parameters["timeline_start_s"])
    if destination == track.track_id:
        return _put_clip(state, track, replace(clip, timeline_start_s=start))
    try:
        target_track = state.timeline.track(destination)
    except KeyError:
        raise OperationError(f"Unknown track '{destination}'") from None
    source_track = track.with_clips(tuple(i for i in track.clips if i.clip_id != clip.clip_id))
    moved = replace(clip, timeline_start_s=start)
    timeline = state.timeline.with_track(source_track).with_track(
        target_track.with_clips(target_track.clips + (moved,))
    )
    return replace(state, timeline=timeline)


def _split_clip(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    at = state.quantize(operation.parameters["time_s"])
    _require(
        clip.timeline_start_s + MIN_CLIP_S <= at <= clip.timeline_end_s - MIN_CLIP_S,
        "A split must leave at least one frame on each side",
    )
    source_at = clip.source_time_at(at)
    left_span = source_at - clip.source_start_s
    right_span = clip.source_end_s - source_at
    left = replace(
        clip,
        source_end_s=source_at,
        speed_curve=_refit_curve(clip, left_span),
    )
    right = Clip(
        clip_id=operation.parameters["new_clip_id"],
        media_id=clip.media_id,
        timeline_start_s=at,
        source_start_s=source_at,
        source_end_s=clip.source_end_s,
        speed_curve=_refit_curve(clip, right_span),
        effects=clip.effects,
        color=clip.color,
        enabled=clip.enabled,
        label=clip.label,
    )
    clips = tuple(item for item in track.clips if item.clip_id != clip.clip_id) + (left, right)
    return replace(state, timeline=state.timeline.with_track(track.with_clips(clips)))


# ---------------------------------------------------------------- rhythm


def _trim_clip(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    parameters = operation.parameters
    edge = parameters["edge"]
    source_start = clip.source_start_s
    source_end = clip.source_end_s
    if edge in ("in", "both"):
        _require("source_start_s" in parameters, "Trimming the in point needs source_start_s")
        source_start = parameters["source_start_s"]
    if edge in ("out", "both"):
        _require("source_end_s" in parameters, "Trimming the out point needs source_end_s")
        source_end = parameters["source_end_s"]
    source_start = _snap_source(state, clip.media_id, source_start)
    source_end = _snap_source(state, clip.media_id, source_end)
    duration = _media_duration(state, clip.media_id)
    _require(0.0 <= source_start < source_end <= duration + 1e-6, "Trim leaves the media")
    _require(source_end - source_start >= MIN_CLIP_S, "A trim must leave at least one frame")
    span = source_end - source_start
    trimmed = replace(
        clip,
        source_start_s=source_start,
        source_end_s=source_end,
        speed_curve=_refit_curve(clip, span),
    )
    delta = trimmed.timeline_duration_s - clip.timeline_duration_s
    clips = _swap(track.clips, clip.clip_id, trimmed)
    if parameters.get("ripple", True) and delta != 0.0:
        clips = _shift_clips(clips, clip.timeline_end_s, delta, exclude=(clip.clip_id,))
    return replace(state, timeline=state.timeline.with_track(track.with_clips(clips)))


def _apply_speed_curve(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    curve = SpeedCurve.parse(operation.parameters["curve"]).fitted_to_source(clip.source_span_s)
    updated = replace(
        clip, speed_curve=curve, interpolation=operation.parameters.get("interpolation", "none")
    )
    delta = updated.timeline_duration_s - clip.timeline_duration_s
    clips = _swap(track.clips, clip.clip_id, updated)
    if operation.parameters.get("ripple", True) and delta != 0.0:
        clips = _shift_clips(clips, clip.timeline_end_s, delta, exclude=(clip.clip_id,))
    return replace(state, timeline=state.timeline.with_track(track.with_clips(clips)))


def _freeze_frame(state, operation):
    """A freeze is one frame played very slowly. Representing it that way keeps the model
    honest: the timeline still derives its duration from a speed curve over a real source
    span, so trimming, rippling and rendering need no special case."""
    track, clip = _clip_of(state, operation.target.clip_id)
    at = state.quantize(operation.parameters["time_s"])
    hold = operation.parameters["hold_s"]
    frame = state.render_settings.frame_s
    _require(
        clip.timeline_start_s + frame <= at <= clip.timeline_end_s - frame,
        "A freeze needs a frame on each side inside the clip",
    )
    source_at = clip.source_time_at(at)
    _require(source_at + frame <= clip.source_end_s, "A freeze needs a frame of source after it")
    rate = frame / hold
    _require(rate >= 0.01, f"Holding one frame for {hold:.2f}s is below the slowest supported rate")

    left_span = source_at - clip.source_start_s
    left = replace(clip, source_end_s=source_at, speed_curve=_refit_curve(clip, left_span))
    still = Clip(
        clip_id=f"{clip.clip_id}-freeze",
        media_id=clip.media_id,
        timeline_start_s=at,
        source_start_s=source_at,
        source_end_s=source_at + frame,
        speed_curve=SpeedCurve.constant(hold, rate),
        effects=clip.effects,
        color=clip.color,
        label=clip.label,
    )
    tail_start = source_at + frame
    remaining = []
    if clip.source_end_s - tail_start >= MIN_CLIP_S:
        remaining.append(
            Clip(
                clip_id=f"{clip.clip_id}-resume",
                media_id=clip.media_id,
                timeline_start_s=at + hold,
                source_start_s=tail_start,
                source_end_s=clip.source_end_s,
                speed_curve=_refit_curve(clip, clip.source_end_s - tail_start),
                effects=clip.effects,
                color=clip.color,
                label=clip.label,
            )
        )
    others = [item for item in track.clips if item.clip_id != clip.clip_id]
    pieces = [left, still, *remaining]
    tail_end = at + hold + (remaining[0].timeline_duration_s if remaining else 0.0)
    clips = _shift_clips(
        others + pieces,
        clip.timeline_end_s,
        tail_end - clip.timeline_end_s,
        exclude=tuple(item.clip_id for item in pieces),
    )
    return replace(state, timeline=state.timeline.with_track(track.with_clips(clips)))


def _apply_transition(state, operation):
    parameters = operation.parameters
    track = state.timeline.track(operation.target.track_id)
    outgoing = track.clip(parameters["from_clip_id"])
    incoming = track.clip(parameters["to_clip_id"])
    duration = parameters["duration_s"]
    gap = incoming.timeline_start_s - outgoing.timeline_end_s
    if 0.0 < gap <= state.frame_s() + 1e-6:
        incoming = replace(incoming, timeline_start_s=outgoing.timeline_end_s)
        track = track.with_clips(
            tuple(incoming if item.clip_id == incoming.clip_id else item for item in track.clips)
        )
        gap = 0.0
    _require(
        abs(gap) < 1e-6,
        "A transition joins two adjacent clips",
    )
    for clip in (outgoing, incoming):
        _require(
            clip.timeline_duration_s > duration + MIN_CLIP_S,
            f"Clip '{clip.clip_id}' is too short for a {duration:.2f}s transition",
        )
    instance = TransitionInstance(
        transition_id=parameters["transition_id"],
        effect_id=parameters["effect_id"],
        effect_version=parameters["effect_version"],
        from_clip_id=outgoing.clip_id,
        to_clip_id=incoming.clip_id,
        duration_s=duration,
        parameters=parameters.get("parameters", {}),
    )
    _require(
        all(item.transition_id != instance.transition_id for item in state.timeline.transitions),
        f"Transition '{instance.transition_id}' already exists",
    )
    # The overlap and the transition that explains it are one change. Building the timeline
    # in two steps would briefly describe an overlap nothing accounts for, and the timeline
    # would rightly refuse it.
    shifted = track.with_clips(_shift_clips(track.clips, incoming.timeline_start_s, -duration))
    tracks = tuple(shifted if item.track_id == track.track_id else item for item in state.timeline.tracks)
    timeline = Timeline(tracks, state.timeline.transitions + (instance,), state.timeline.markers)
    return replace(state, timeline=timeline)


def _align_cut_to_beat(state, operation):
    """A roll edit: the cut point moves, the total duration does not."""
    parameters = operation.parameters
    track = state.timeline.track(operation.target.track_id)
    incoming = track.clip(parameters["clip_id"])
    index = track.clips.index(incoming)
    _require(index > 0, "The first clip has no incoming cut to align")
    outgoing = track.clips[index - 1]
    # A roll moves the cut while holding the programme length. On a retimed clip the source
    # consumed by an extra second of timeline depends on where in the curve that second sits,
    # so rolling would either change the length or silently reshape the ramp. Align cuts
    # before retiming; the rhythm phase does exactly that.
    for clip in (outgoing, incoming):
        _require(
            clip.speed_curve is None,
            f"Clip '{clip.clip_id}' is retimed; align this cut before applying its speed curve",
        )
    limit = parameters.get("max_shift_s", 0.25)
    delta = state.quantize(parameters["beat_time_s"]) - incoming.timeline_start_s
    delta = max(-limit, min(limit, delta))
    delta = state.quantize(delta)
    if delta == 0.0:
        return state
    new_out = outgoing.source_end_s + delta
    new_in = incoming.source_start_s + delta
    _require(
        new_out - outgoing.source_start_s >= MIN_CLIP_S and incoming.source_end_s - new_in >= MIN_CLIP_S,
        "Aligning to this beat would leave a clip shorter than a frame",
    )
    _require(new_out <= _media_duration(state, outgoing.media_id) + 1e-6, "Roll leaves the media")
    _require(new_in >= 0.0, "Roll leaves the media")
    rolled_out = replace(outgoing, source_end_s=new_out)
    rolled_in = replace(
        incoming,
        timeline_start_s=round(incoming.timeline_start_s + delta, 9),
        source_start_s=new_in,
    )
    clips = tuple(
        rolled_out
        if item.clip_id == outgoing.clip_id
        else rolled_in
        if item.clip_id == incoming.clip_id
        else item
        for item in track.clips
    )
    return replace(state, timeline=state.timeline.with_track(track.with_clips(clips)))


def _add_markers(state, operation):
    kind = operation.parameters["kind"]
    markers = list(state.timeline.markers)
    existing = {item.marker_id for item in markers}
    for index, entry in enumerate(operation.parameters["markers"]):
        if isinstance(entry, dict):
            time_s = entry.get("time_s")
            strength = entry.get("strength", 1.0)
            label = entry.get("label")
        else:
            time_s, strength, label = entry, 1.0, None
        marker_id = f"{kind}-{index:04d}"
        if marker_id in existing:
            continue
        markers.append(Marker(marker_id, time_s, kind, label, strength))
    return replace(state, timeline=replace(state.timeline, markers=tuple(markers)))


# ---------------------------------------------------------------- colour


def _apply_color_correction(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    grade = replace(clip.color, **operation.parameters)
    return _put_clip(state, track, replace(clip, color=grade))


def _match_color(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    parameters = dict(operation.parameters)
    reference = parameters.pop("reference_clip_id")
    _clip_of(state, reference)
    grade = replace(clip.color, matched_to=reference, **parameters)
    return _put_clip(state, track, replace(clip, color=grade))


def _apply_creative_look(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    grade = replace(
        clip.color,
        look_id=operation.parameters["look_id"],
        look_intensity=operation.parameters["intensity"],
    )
    return _put_clip(state, track, replace(clip, color=grade))


# ---------------------------------------------------------------- effects


def _add_effect(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    parameters = operation.parameters
    instance = EffectInstance(
        instance_id=parameters["instance_id"],
        effect_id=parameters["effect_id"],
        effect_version=parameters["effect_version"],
        parameters=parameters.get("parameters", {}),
        start_s=parameters.get("start_s"),
        end_s=parameters.get("end_s"),
    )
    _require(
        all(item.instance_id != instance.instance_id for item in clip.effects),
        f"Effect instance '{instance.instance_id}' already exists on this clip",
    )
    return _put_clip(state, track, replace(clip, effects=clip.effects + (instance,)))


def _update_effect(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    instance_id = operation.target.instance_id
    found = [item for item in clip.effects if item.instance_id == instance_id]
    _require(found, f"Unknown effect instance '{instance_id}'")
    updated = replace(found[0], **operation.parameters)
    effects = tuple(updated if item.instance_id == instance_id else item for item in clip.effects)
    return _put_clip(state, track, replace(clip, effects=effects))


def _remove_effect(state, operation):
    track, clip = _clip_of(state, operation.target.clip_id)
    instance_id = operation.target.instance_id
    effects = tuple(item for item in clip.effects if item.instance_id != instance_id)
    _require(len(effects) != len(clip.effects), f"Unknown effect instance '{instance_id}'")
    return _put_clip(state, track, replace(clip, effects=effects))


def _apply_template(state, operation):
    """A template's effect is the operations it emits. This entry marks the log for replay
    and explanation; the state change arrives with the operations that follow it."""
    return state


# ---------------------------------------------------------------- audio


def _add_audio(state, operation, kind=None):
    parameters = operation.parameters
    event = AudioEvent(
        event_id=parameters["event_id"],
        kind=kind or parameters["kind"],
        asset_id=parameters["asset_id"],
        timeline_start_s=state.quantize(parameters["timeline_start_s"]),
        duration_s=parameters["duration_s"],
        source_start_s=parameters.get("source_start_s", 0.0),
        gain_db=parameters.get("gain_db", 0.0),
        fade_in_s=parameters.get("fade_in_s", 0.0),
        fade_out_s=parameters.get("fade_out_s", 0.0),
    )
    _require(
        all(item.event_id != event.event_id for item in state.audio),
        f"Audio event '{event.event_id}' already exists",
    )
    return replace(state, audio=state.audio + (event,))


def _update_audio(state, operation, **changes):
    event_id = operation.target.event_id
    found = [item for item in state.audio if item.event_id == event_id]
    _require(found, f"Unknown audio event '{event_id}'")
    updated = replace(found[0], **changes)
    return replace(
        state,
        audio=tuple(updated if item.event_id == event_id else item for item in state.audio),
    )


# ---------------------------------------------------------------- lifecycle


def _set_phase(state, operation):
    return replace(state, phase=operation.parameters["phase"])


def _finalize(state, operation):
    _require(state.timeline.duration_s > 0.0, "Cannot finalize an empty timeline")
    for track in state.timeline.tracks:
        for clip in track.clips:
            _require(
                clip.media_id in state.media,
                f"Clip '{clip.clip_id}' references missing media '{clip.media_id}'",
            )
    return replace(state, finalized=True, phase="complete")


HANDLERS = {
    OperationType.IMPORT_MEDIA: _import_media,
    OperationType.ANALYZE_CLIP: _analyze_clip,
    OperationType.SET_INTENT: _set_intent,
    OperationType.SELECT_CLIP: lambda s, o: _select(s, o, True),
    OperationType.REJECT_CLIP: lambda s, o: _select(s, o, False),
    OperationType.ADD_TRACK: _add_track,
    OperationType.ADD_CLIP: _add_clip,
    OperationType.REMOVE_CLIP: _remove_clip,
    OperationType.MOVE_CLIP: _move_clip,
    OperationType.SPLIT_CLIP: _split_clip,
    OperationType.TRIM_CLIP: _trim_clip,
    OperationType.APPLY_SPEED_CURVE: _apply_speed_curve,
    OperationType.FREEZE_FRAME: _freeze_frame,
    OperationType.APPLY_TRANSITION: _apply_transition,
    OperationType.ALIGN_CUT_TO_BEAT: _align_cut_to_beat,
    OperationType.ADD_MARKERS: _add_markers,
    OperationType.APPLY_COLOR_CORRECTION: _apply_color_correction,
    OperationType.MATCH_COLOR: _match_color,
    OperationType.APPLY_CREATIVE_LOOK: _apply_creative_look,
    OperationType.ADD_EFFECT: _add_effect,
    OperationType.UPDATE_EFFECT: _update_effect,
    OperationType.REMOVE_EFFECT: _remove_effect,
    OperationType.APPLY_TEMPLATE: _apply_template,
    OperationType.ADD_MUSIC: lambda s, o: _add_audio(s, o, "music"),
    OperationType.ADD_SFX: _add_audio,
    OperationType.SET_VOLUME: lambda s, o: _update_audio(s, o, gain_db=o.parameters["gain_db"]),
    OperationType.APPLY_AUDIO_DUCK: lambda s, o: _update_audio(s, o, ducks=o.parameters["ducks"]),
    OperationType.SET_PHASE: _set_phase,
    OperationType.FINALIZE_TIMELINE: _finalize,
}

assert set(HANDLERS) == set(OperationType), "Every operation type needs exactly one handler"


def apply(state, operation):
    """Fold one operation into the project. Returns `(new_state, patch)`.

    Raises `OperationError` if the operation cannot be applied to this state. The caller
    decides whether that is a rejection or a fault; the reducer never guesses.
    """
    if not isinstance(state, ProjectState):
        raise ValidationError("Reducer input must be a ProjectState")
    if not isinstance(operation, EditOperation):
        raise ValidationError("Reducer input must be an EditOperation")
    if state.finalized and operation.type is not OperationType.SET_PHASE:
        raise OperationError("The timeline is finalized; reopen it before editing")
    before = state.wire()
    try:
        result = HANDLERS[operation.type](state, operation)
    except OperationError:
        raise
    except (ValueError, KeyError) as error:
        # Parameters were validated when the operation was constructed. A failure here means
        # valid parameters do not fit *this* state, which is a rejection, not a bad request.
        raise OperationError(f"{operation.type} rejected: {error}") from error
    result = replace(result, version=state.version + 1)
    return result, diff(before, result.wire())


def fold(state, operations):
    """Replay. The film is `fold(empty_project, operation_log)` and nothing else."""
    patches = []
    for operation in operations:
        state, patch = apply(state, operation)
        patches.append(patch)
    return state, patches
