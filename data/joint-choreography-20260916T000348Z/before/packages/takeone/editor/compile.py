"""ProjectState -> EditGraph. Pure, deterministic, and the only place the two meet.

The graph is *derived*. It is never edited, never stored as the truth, and never able to
disagree with the timeline, because it is recomputed from the timeline every time. That is
what makes "the UI animates a real project mutation" true rather than aspirational.
"""

from dataclasses import dataclass
from typing import ClassVar

from .color import spaces
from .contracts import choice, integer
from .effects import EFFECTS
from .errors import CompileError
from .graph import EditGraph, NodeType, TimeRange, node

TARGETS = ("preview", "master")


@dataclass(frozen=True, slots=True)
class RenderTarget:
    schema_version: ClassVar[int] = 1
    kind: str = "preview"
    width: int = 960
    height: int = 540
    fps_num: int = 30
    fps_den: int = 1
    crf: int = 26
    use_proxy: bool = True

    def __post_init__(self):
        choice(self.kind, "Render target", TARGETS)
        integer(self.width, "Target width", 16, 8192)
        integer(self.height, "Target height", 16, 8192)
        integer(self.fps_num, "Frame rate numerator", 1)
        integer(self.fps_den, "Frame rate denominator", 1)
        integer(self.crf, "CRF", 0, 51)

    @property
    def fps(self):
        return self.fps_num / self.fps_den

    def wire(self):
        return {
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
            "fps_num": self.fps_num,
            "fps_den": self.fps_den,
            "crf": self.crf,
            "use_proxy": self.use_proxy,
        }


def preview_target(state):
    settings = state.render_settings
    long_edge = settings.preview_long_edge
    width, height = settings.master_width, settings.master_height
    scale = long_edge / max(width, height)
    return RenderTarget(
        kind="preview",
        width=_even(width * scale),
        height=_even(height * scale),
        fps_num=settings.fps_num,
        fps_den=settings.fps_den,
        crf=settings.preview_crf,
        use_proxy=True,
    )


def master_target(state):
    settings = state.render_settings
    return RenderTarget(
        kind="master",
        width=settings.master_width,
        height=settings.master_height,
        fps_num=settings.fps_num,
        fps_den=settings.fps_den,
        crf=settings.master_crf,
        use_proxy=False,
    )


def _even(value):
    return max(16, int(round(value / 2.0)) * 2)


def _media_path(media, target):
    if target.use_proxy and media.proxy_path:
        return media.proxy_path
    return media.path


# ---------------------------------------------------------------- clip chain


def _clip_chain(state, clip, target, nodes):
    """Source -> trim -> conform -> timing -> colour -> look -> effects. Returns the tail id."""
    media = state.media_item(clip.media_id)
    spaces.require_convertible(media.source_space, "Media source space")

    # A source node is a decoded media *segment*: the file and the in/out points together.
    # Two clips cut differently from one file are therefore two different nodes, which is
    # both true and what lets the content address deduplicate only genuinely identical reads.
    source = node(
        NodeType.SOURCE,
        1,
        (),
        {
            "path": _media_path(media, target),
            "media_id": media.media_id,
            "sha256": media.sha256,
            "proxy": bool(target.use_proxy and media.proxy_path),
            "in_s": round(clip.source_start_s, 6),
            "out_s": round(clip.source_end_s, 6),
        },
        metadata={"clip_id": clip.clip_id},
    )
    nodes.append(source)

    conform = node(
        NodeType.TRANSFORM,
        1,
        (source.node_id,),
        {
            "width": target.width,
            "height": target.height,
            "fit": "cover",
            "fps_num": target.fps_num,
            "fps_den": target.fps_den,
        },
        metadata={"clip_id": clip.clip_id},
    )
    nodes.append(conform)
    current = conform.node_id

    if clip.speed_curve is not None:
        segments = clip.speed_curve.segments()
        timing = node(
            NodeType.TIMING,
            1,
            (current,),
            {
                "segments": [
                    {"start_s": round(a, 6), "end_s": round(b, 6), "rate": round(r, 6)}
                    for a, b, r in segments
                ],
                "interpolation": clip.interpolation,
                "source_duration_s": round(clip.source_span_s, 6),
                "timeline_duration_s": round(clip.timeline_duration_s, 6),
                "fps_num": target.fps_num,
                "fps_den": target.fps_den,
            },
            metadata={"clip_id": clip.clip_id},
        )
        nodes.append(timing)
        current = timing.node_id

    grade = clip.color
    technical = (
        grade.exposure_stops != 0.0
        or grade.temperature_k != 0.0
        or grade.tint != 0.0
        or grade.contrast != 1.0
        or grade.saturation != 1.0
        or grade.lift != 0.0
    )
    if technical:
        color = node(
            NodeType.COLOR,
            1,
            (current,),
            {
                "input_space": media.source_space,
                "working_space": "linear-rec709" if grade.exposure_stops != 0.0 else "rec709",
                "output_space": "rec709",
                "exposure_stops": round(grade.exposure_stops, 6),
                "temperature_k": round(grade.temperature_k, 3),
                "tint": round(grade.tint, 6),
                "contrast": round(grade.contrast, 6),
                "saturation": round(grade.saturation, 6),
                "lift": round(grade.lift, 6),
                "matched_to": grade.matched_to,
            },
            metadata={"clip_id": clip.clip_id, "stage": "technical"},
        )
        nodes.append(color)
        current = color.node_id

    if grade.look_id and grade.look_intensity > 0.0:
        spec = EFFECTS.latest(grade.look_id)
        built, current = spec.build(
            (current,), {"intensity": grade.look_intensity}, None, {"clip_id": clip.clip_id}
        )
        nodes.extend(built)

    for instance in clip.effects:
        if not instance.enabled:
            continue
        spec = EFFECTS.get(instance.effect_id, instance.effect_version)
        if spec.arity != 1:
            raise CompileError(f"Effect '{spec.id}' takes two inputs and cannot be attached to a single clip")
        span = None
        if instance.start_s is not None:
            span = TimeRange(instance.start_s, instance.end_s)
        built, current = spec.build(
            (current,),
            instance.parameters,
            span,
            {"clip_id": clip.clip_id, "instance_id": instance.instance_id},
        )
        nodes.extend(built)

    return current, clip.timeline_duration_s


# ---------------------------------------------------------------- track and project


def _video_track_chain(state, track, target, nodes):
    clips = [clip for clip in track.clips if clip.enabled]
    if not clips:
        return None, 0.0
    transitions = {item.to_clip_id: item for item in state.timeline.transitions}
    current, duration = _clip_chain(state, clips[0], target, nodes)
    for clip in clips[1:]:
        tail, clip_duration = _clip_chain(state, clip, target, nodes)
        transition = transitions.get(clip.clip_id)
        if transition is not None:
            spec = EFFECTS.get(transition.effect_id, transition.effect_version)
            if spec.arity != 2:
                raise CompileError(f"Effect '{spec.id}' is not a transition")
            offset = max(0.0, duration - transition.duration_s)
            built, current = spec.build(
                (current, tail),
                {**transition.parameters, "duration_s": transition.duration_s, "offset_s": round(offset, 6)},
                None,
                {"transition_id": transition.transition_id},
            )
            nodes.extend(built)
            duration = duration + clip_duration - transition.duration_s
        else:
            joined = node(
                NodeType.SEQUENCE,
                1,
                (current, tail),
                {"mode": "concat"},
                metadata={"clip_id": clip.clip_id},
            )
            nodes.append(joined)
            current = joined.node_id
            duration += clip_duration
    return current, duration


def project_graph(state, target=None):
    """Compile the project's timeline to a render graph for one target."""
    target = target or preview_target(state)
    if not isinstance(target, RenderTarget):
        raise CompileError("Compilation needs a typed render target")
    video_tracks = [track for track in state.timeline.tracks if track.kind == "video"]
    if not video_tracks:
        raise CompileError("The project has no video track to render")
    nodes = []
    tails = []
    for track in video_tracks:
        tail, duration = _video_track_chain(state, track, target, nodes)
        if tail is not None:
            tails.append((track.track_id, tail, duration))
    if not tails:
        raise CompileError("The timeline has no enabled clips")
    if len(tails) == 1:
        current = tails[0][1]
        duration = tails[0][2]
    else:
        current = tails[0][1]
        duration = max(item[2] for item in tails)
        for _, tail, _ in tails[1:]:
            layered = node(NodeType.COMPOSITE, 1, (current, tail), {"mode": "over", "opacity": 1.0})
            nodes.append(layered)
            current = layered.node_id
    output = node(
        NodeType.OUTPUT,
        1,
        (current,),
        {
            "target": target.kind,
            "width": target.width,
            "height": target.height,
            "fps_num": target.fps_num,
            "fps_den": target.fps_den,
            "crf": target.crf,
            "duration_s": round(duration, 6),
        },
        metadata={"project_id": state.project_id, "project_version": state.version},
    )
    nodes.append(output)
    unique = {}
    for item in nodes:
        unique.setdefault(item.node_id, item)
    return EditGraph(tuple(unique.values()), output.node_id)
