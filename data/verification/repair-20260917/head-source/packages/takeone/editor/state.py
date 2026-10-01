"""The project state. Immutable, derived from the operation log, never edited in place.

Nothing in this module imports a planner, an analyzer or a renderer. The editor core is
AI-independent by construction: an LLM, a template, a human command and the robot director
all reach this state through exactly one door, `reducer.apply`.
"""

import math
from dataclasses import dataclass, field, replace
from typing import ClassVar

from .contracts import (
    boolean,
    choice,
    digest_hex,
    fields,
    integer,
    mapping,
    number,
    seconds,
    slug,
    text,
    unit,
)
from .errors import ValidationError
from .timing.curve import SpeedCurve

TRACK_KINDS = ("video", "overlay", "effect", "audio")
INTERPOLATION_MODES = ("none", "blend", "mci")
SELECTION_STATES = ("pending", "analyzing", "selected", "rejected")
MARKER_KINDS = ("beat", "downbeat", "impact", "slot", "cut")
AUDIO_KINDS = ("music", "dialogue", "ambient", "sfx", "impact", "riser", "whoosh")
ASPECT_RATIOS = ("9:16", "16:9", "1:1", "2.39:1")
PHASES = (
    "understand",
    "select",
    "structure",
    "rhythm",
    "color",
    "effects",
    "audio",
    "finalize",
    "complete",
)
COLOR_SPACES = ("rec709", "srgb", "linear-rec709", "apple-log", "rec2100-pq")
EPSILON_S = 1e-6


def _ratio(value, name):
    parts = str(value).split(":")
    if len(parts) != 2:
        raise ValidationError(f"{name} must look like 16:9")
    return value


# ---------------------------------------------------------------- media


@dataclass(frozen=True, slots=True)
class MediaProbe:
    duration_s: float
    width: int
    height: int
    fps_num: int
    fps_den: int
    has_audio: bool
    video_codec: str
    rotation_deg: int = 0
    pixel_format: str = "yuv420p"

    def __post_init__(self):
        seconds(self.duration_s, "Media duration", EPSILON_S)
        integer(self.width, "Width", 16, 16384)
        integer(self.height, "Height", 16, 16384)
        integer(self.fps_num, "Frame rate numerator", 1)
        integer(self.fps_den, "Frame rate denominator", 1)
        boolean(self.has_audio, "Has audio")
        text(self.video_codec, "Video codec", 32)
        choice(self.rotation_deg, "Rotation", (0, 90, 180, 270))
        text(self.pixel_format, "Pixel format", 32)

    @property
    def fps(self):
        return self.fps_num / self.fps_den

    @property
    def frame_s(self):
        return self.fps_den / self.fps_num

    def wire(self):
        return {
            "duration_s": self.duration_s,
            "width": self.width,
            "height": self.height,
            "fps_num": self.fps_num,
            "fps_den": self.fps_den,
            "fps": self.fps,
            "has_audio": self.has_audio,
            "video_codec": self.video_codec,
            "rotation_deg": self.rotation_deg,
            "pixel_format": self.pixel_format,
        }

    @classmethod
    def parse(cls, value):
        data = dict(
            fields(
                value,
                ("duration_s", "width", "height", "fps_num", "fps_den", "has_audio", "video_codec"),
                ("rotation_deg", "pixel_format", "fps"),
            )
        )
        data.pop("fps", None)
        return cls(**data)


@dataclass(frozen=True, slots=True)
class MediaItem:
    media_id: str
    name: str
    path: str
    sha256: str
    probe: MediaProbe
    source_space: str = "rec709"
    proxy_path: str | None = None
    thumbnail_path: str | None = None
    waveform_path: str | None = None

    def __post_init__(self):
        slug(self.media_id, "Media ID")
        text(self.name, "Media name", 200)
        text(self.path, "Media path", 1024)
        digest_hex(self.sha256, "Media digest")
        if not isinstance(self.probe, MediaProbe):
            raise ValidationError("Media needs a typed probe")
        choice(self.source_space, "Source colour space", COLOR_SPACES)

    def wire(self):
        return {
            "media_id": self.media_id,
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "probe": self.probe.wire(),
            "source_space": self.source_space,
            "proxy_path": self.proxy_path,
            "thumbnail_path": self.thumbnail_path,
            "waveform_path": self.waveform_path,
        }


# ---------------------------------------------------------------- colour and effects


@dataclass(frozen=True, slots=True)
class ColorGrade:
    """Technical correction, shot match and creative look, kept separate on purpose."""

    exposure_stops: float = 0.0
    temperature_k: float = 0.0
    tint: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    lift: float = 0.0
    look_id: str | None = None
    look_intensity: float = 0.0
    matched_to: str | None = None

    def __post_init__(self):
        number(self.exposure_stops, "Exposure", -4.0, 4.0)
        number(self.temperature_k, "Temperature shift", -2000.0, 2000.0)
        number(self.tint, "Tint", -1.0, 1.0)
        number(self.contrast, "Contrast", 0.2, 3.0)
        number(self.saturation, "Saturation", 0.0, 3.0)
        number(self.lift, "Lift", -0.5, 0.5)
        if self.look_id is not None:
            slug(self.look_id, "Look ID")
        unit(self.look_intensity, "Look intensity")
        if self.matched_to is not None:
            slug(self.matched_to, "Match reference")

    @property
    def is_identity(self):
        return (
            self.exposure_stops == 0.0
            and self.temperature_k == 0.0
            and self.tint == 0.0
            and self.contrast == 1.0
            and self.saturation == 1.0
            and self.lift == 0.0
            and (self.look_id is None or self.look_intensity == 0.0)
        )

    def wire(self):
        return {
            "exposure_stops": self.exposure_stops,
            "temperature_k": self.temperature_k,
            "tint": self.tint,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "lift": self.lift,
            "look_id": self.look_id,
            "look_intensity": self.look_intensity,
            "matched_to": self.matched_to,
        }

    @classmethod
    def parse(cls, value):
        return cls(**fields(value, (), tuple(cls.__slots__)))


@dataclass(frozen=True, slots=True)
class EffectInstance:
    instance_id: str
    effect_id: str
    effect_version: int
    parameters: dict = field(default_factory=dict)
    start_s: float | None = None
    end_s: float | None = None
    enabled: bool = True

    def __post_init__(self):
        slug(self.instance_id, "Effect instance ID")
        slug(self.effect_id, "Effect ID")
        integer(self.effect_version, "Effect version", 1, 999)
        object.__setattr__(self, "parameters", mapping(self.parameters, "Effect parameters"))
        if (self.start_s is None) != (self.end_s is None):
            raise ValidationError("An effect span needs both ends or neither")
        if self.start_s is not None:
            seconds(self.start_s, "Effect start")
            seconds(self.end_s, "Effect end", self.start_s + EPSILON_S)
        boolean(self.enabled, "Effect enabled")

    def wire(self):
        return {
            "instance_id": self.instance_id,
            "effect_id": self.effect_id,
            "effect_version": self.effect_version,
            "parameters": dict(self.parameters),
            "start_s": self.start_s,
            "end_s": self.end_s,
            "enabled": self.enabled,
        }


# ---------------------------------------------------------------- timeline


@dataclass(frozen=True, slots=True)
class Clip:
    clip_id: str
    media_id: str
    timeline_start_s: float
    source_start_s: float
    source_end_s: float
    speed_curve: SpeedCurve | None = None
    interpolation: str = "none"
    effects: tuple[EffectInstance, ...] = ()
    color: ColorGrade = field(default_factory=ColorGrade)
    enabled: bool = True
    label: str | None = None

    def __post_init__(self):
        slug(self.clip_id, "Clip ID")
        slug(self.media_id, "Media ID")
        choice(self.interpolation, "Speed interpolation", INTERPOLATION_MODES)
        seconds(self.timeline_start_s, "Clip timeline start")
        seconds(self.source_start_s, "Clip source start")
        seconds(self.source_end_s, "Clip source end", self.source_start_s + EPSILON_S)
        object.__setattr__(self, "effects", tuple(self.effects))
        if len(self.effects) > 32:
            raise ValidationError("A clip is limited to 32 effects")
        seen = set()
        for item in self.effects:
            if not isinstance(item, EffectInstance):
                raise ValidationError("Clip effects must be typed instances")
            if item.instance_id in seen:
                raise ValidationError("Duplicate effect instance on a clip")
            seen.add(item.instance_id)
        if not isinstance(self.color, ColorGrade):
            raise ValidationError("Clip colour must be a typed grade")
        if self.speed_curve is not None:
            if not isinstance(self.speed_curve, SpeedCurve):
                raise ValidationError("Clip speed must be a typed curve")
            drift = abs(self.speed_curve.source_duration_s - self.source_span_s)
            if drift > 1e-3:
                raise ValidationError(
                    f"Speed curve consumes {self.speed_curve.source_duration_s:.4f}s of source "
                    f"but the clip spans {self.source_span_s:.4f}s"
                )
        boolean(self.enabled, "Clip enabled")
        if self.label is not None:
            text(self.label, "Clip label", 80)

    @property
    def source_span_s(self):
        return self.source_end_s - self.source_start_s

    @property
    def timeline_duration_s(self):
        return self.speed_curve.duration_s if self.speed_curve else self.source_span_s

    @property
    def timeline_end_s(self):
        return self.timeline_start_s + self.timeline_duration_s

    def source_time_at(self, timeline_time_s):
        """Source time for a timeline time inside the clip."""
        local = min(self.timeline_duration_s, max(0.0, timeline_time_s - self.timeline_start_s))
        if self.speed_curve is None:
            return self.source_start_s + local
        return self.source_start_s + self.speed_curve.source_offset_at(local)

    def wire(self):
        return {
            "clip_id": self.clip_id,
            "media_id": self.media_id,
            "timeline_start_s": self.timeline_start_s,
            "timeline_end_s": self.timeline_end_s,
            "timeline_duration_s": self.timeline_duration_s,
            "source_start_s": self.source_start_s,
            "source_end_s": self.source_end_s,
            "speed_curve": self.speed_curve.wire() if self.speed_curve else None,
            "interpolation": self.interpolation,
            "effects": [item.wire() for item in self.effects],
            "color": self.color.wire(),
            "enabled": self.enabled,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class Track:
    track_id: str
    kind: str
    clips: tuple[Clip, ...] = ()

    def __post_init__(self):
        slug(self.track_id, "Track ID")
        choice(self.kind, "Track kind", TRACK_KINDS)
        clips = tuple(sorted(self.clips, key=lambda clip: clip.timeline_start_s))
        seen = set()
        for clip in clips:
            if not isinstance(clip, Clip):
                raise ValidationError("Track contents must be typed clips")
            if clip.clip_id in seen:
                raise ValidationError("Duplicate clip on a track")
            seen.add(clip.clip_id)
        object.__setattr__(self, "clips", clips)

    @property
    def duration_s(self):
        return max((clip.timeline_end_s for clip in self.clips), default=0.0)

    def overlaps(self):
        """Adjacent pairs that overlap, with the overlap in seconds.

        A track cannot judge whether an overlap is legitimate: a transition is exactly an
        overlap, and transitions live on the timeline. So the track reports; the timeline
        decides."""
        found = []
        for previous, current in zip(self.clips, self.clips[1:]):
            overlap = previous.timeline_end_s - current.timeline_start_s
            if overlap > EPSILON_S:
                found.append((previous.clip_id, current.clip_id, overlap))
        return found

    def clip(self, clip_id):
        for clip in self.clips:
            if clip.clip_id == clip_id:
                return clip
        raise KeyError(clip_id)

    def with_clips(self, clips):
        return replace(self, clips=tuple(clips))

    def wire(self):
        return {
            "track_id": self.track_id,
            "kind": self.kind,
            "duration_s": self.duration_s,
            "clips": [clip.wire() for clip in self.clips],
        }


@dataclass(frozen=True, slots=True)
class TransitionInstance:
    transition_id: str
    effect_id: str
    effect_version: int
    from_clip_id: str
    to_clip_id: str
    duration_s: float
    parameters: dict = field(default_factory=dict)

    def __post_init__(self):
        slug(self.transition_id, "Transition ID")
        slug(self.effect_id, "Transition effect ID")
        integer(self.effect_version, "Transition effect version", 1, 999)
        slug(self.from_clip_id, "Outgoing clip")
        slug(self.to_clip_id, "Incoming clip")
        seconds(self.duration_s, "Transition duration", 0.04, 5.0)
        object.__setattr__(self, "parameters", mapping(self.parameters, "Transition parameters"))

    def wire(self):
        return {
            "transition_id": self.transition_id,
            "effect_id": self.effect_id,
            "effect_version": self.effect_version,
            "from_clip_id": self.from_clip_id,
            "to_clip_id": self.to_clip_id,
            "duration_s": self.duration_s,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class Marker:
    marker_id: str
    time_s: float
    kind: str
    label: str | None = None
    strength: float = 1.0

    def __post_init__(self):
        slug(self.marker_id, "Marker ID")
        seconds(self.time_s, "Marker time")
        choice(self.kind, "Marker kind", MARKER_KINDS)
        if self.label is not None:
            text(self.label, "Marker label", 80)
        unit(self.strength, "Marker strength")

    def wire(self):
        return {
            "marker_id": self.marker_id,
            "time_s": self.time_s,
            "kind": self.kind,
            "label": self.label,
            "strength": self.strength,
        }


@dataclass(frozen=True, slots=True)
class Timeline:
    tracks: tuple[Track, ...] = ()
    transitions: tuple[TransitionInstance, ...] = ()
    markers: tuple[Marker, ...] = ()

    def __post_init__(self):
        tracks = tuple(self.tracks)
        seen = set()
        for track in tracks:
            if not isinstance(track, Track):
                raise ValidationError("Timeline contents must be typed tracks")
            if track.track_id in seen:
                raise ValidationError("Duplicate track")
            seen.add(track.track_id)
        object.__setattr__(self, "tracks", tracks)
        object.__setattr__(self, "transitions", tuple(self.transitions))
        object.__setattr__(self, "markers", tuple(sorted(self.markers, key=lambda m: m.time_s)))
        declared = {(item.from_clip_id, item.to_clip_id): item.duration_s for item in self.transitions}
        for track in tracks:
            for outgoing, incoming, overlap in track.overlaps():
                expected = declared.get((outgoing, incoming))
                if expected is None:
                    raise ValidationError(
                        f"Clips {outgoing} and {incoming} overlap by {overlap:.4f}s on track "
                        f"{track.track_id} with no transition to account for it"
                    )
                if abs(expected - overlap) > 1e-3:
                    raise ValidationError(
                        f"Transition between {outgoing} and {incoming} lasts {expected:.4f}s "
                        f"but the clips overlap by {overlap:.4f}s"
                    )

    @property
    def duration_s(self):
        """Programme duration: the last frame minus the time transitions overlap away."""
        end = max((track.duration_s for track in self.tracks), default=0.0)
        return round(end, 9)

    def track(self, track_id):
        for track in self.tracks:
            if track.track_id == track_id:
                return track
        raise KeyError(track_id)

    def find_clip(self, clip_id):
        for track in self.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    return track, clip
        raise KeyError(clip_id)

    def with_track(self, track):
        tracks = tuple(track if item.track_id == track.track_id else item for item in self.tracks)
        if all(item.track_id != track.track_id for item in self.tracks):
            tracks = self.tracks + (track,)
        return replace(self, tracks=tracks)

    def wire(self):
        return {
            "duration_s": self.duration_s,
            "tracks": [track.wire() for track in self.tracks],
            "transitions": [item.wire() for item in self.transitions],
            "markers": [item.wire() for item in self.markers],
        }


# ---------------------------------------------------------------- audio, selection, intent


@dataclass(frozen=True, slots=True)
class AudioEvent:
    event_id: str
    kind: str
    asset_id: str
    timeline_start_s: float
    duration_s: float
    source_start_s: float = 0.0
    gain_db: float = 0.0
    fade_in_s: float = 0.0
    fade_out_s: float = 0.0
    ducks: bool = False

    def __post_init__(self):
        slug(self.event_id, "Audio event ID")
        choice(self.kind, "Audio kind", AUDIO_KINDS)
        slug(self.asset_id, "Audio asset ID")
        seconds(self.timeline_start_s, "Audio start")
        seconds(self.duration_s, "Audio duration", EPSILON_S)
        seconds(self.source_start_s, "Audio source start")
        number(self.gain_db, "Audio gain", -60.0, 12.0)
        seconds(self.fade_in_s, "Audio fade in", 0.0, self.duration_s)
        seconds(self.fade_out_s, "Audio fade out", 0.0, self.duration_s)
        boolean(self.ducks, "Audio ducking")

    def wire(self):
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "asset_id": self.asset_id,
            "timeline_start_s": self.timeline_start_s,
            "duration_s": self.duration_s,
            "source_start_s": self.source_start_s,
            "gain_db": self.gain_db,
            "fade_in_s": self.fade_in_s,
            "fade_out_s": self.fade_out_s,
            "ducks": self.ducks,
        }


@dataclass(frozen=True, slots=True)
class SelectionState:
    state: str
    score: float | None = None
    signals: dict = field(default_factory=dict)
    reason: str | None = None

    def __post_init__(self):
        choice(self.state, "Selection state", SELECTION_STATES)
        if self.score is not None:
            unit(self.score, "Selection score")
        object.__setattr__(self, "signals", mapping(self.signals, "Selection signals"))
        for key, value in self.signals.items():
            unit(value, f"Signal {key}")
        if self.reason is not None:
            text(self.reason, "Selection reason", 240)

    def wire(self):
        return {
            "state": self.state,
            "score": self.score,
            "signals": dict(self.signals),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CreativeIntent:
    prompt: str
    target_duration_s: float
    aspect_ratio: str = "16:9"
    genre: str | None = None
    emotion: str | None = None
    pacing: str = "measured"
    style: str | None = None

    def __post_init__(self):
        text(self.prompt, "Creative prompt", 2000)
        seconds(self.target_duration_s, "Target duration", 1.0, 600.0)
        choice(self.aspect_ratio, "Aspect ratio", ASPECT_RATIOS)
        for value, name in ((self.genre, "Genre"), (self.emotion, "Emotion"), (self.style, "Style")):
            if value is not None:
                text(value, name, 80)
        choice(self.pacing, "Pacing", ("slow", "measured", "fast", "frantic"))

    def wire(self):
        return {
            "prompt": self.prompt,
            "target_duration_s": self.target_duration_s,
            "aspect_ratio": self.aspect_ratio,
            "genre": self.genre,
            "emotion": self.emotion,
            "pacing": self.pacing,
            "style": self.style,
        }

    @classmethod
    def parse(cls, value):
        return cls(
            **fields(
                value,
                ("prompt", "target_duration_s"),
                ("aspect_ratio", "genre", "emotion", "pacing", "style"),
            )
        )


@dataclass(frozen=True, slots=True)
class RenderSettings:
    fps_num: int = 30
    fps_den: int = 1
    master_width: int = 1920
    master_height: int = 1080
    preview_long_edge: int = 960
    master_crf: int = 17
    preview_crf: int = 26

    def __post_init__(self):
        integer(self.fps_num, "Frame rate numerator", 1)
        integer(self.fps_den, "Frame rate denominator", 1)
        integer(self.master_width, "Master width", 16, 8192)
        integer(self.master_height, "Master height", 16, 8192)
        integer(self.preview_long_edge, "Preview long edge", 240, 3840)
        integer(self.master_crf, "Master CRF", 0, 51)
        integer(self.preview_crf, "Preview CRF", 0, 51)

    @property
    def fps(self):
        return self.fps_num / self.fps_den

    @property
    def frame_s(self):
        return self.fps_den / self.fps_num

    def wire(self):
        return {
            "fps_num": self.fps_num,
            "fps_den": self.fps_den,
            "fps": self.fps,
            "master_width": self.master_width,
            "master_height": self.master_height,
            "preview_long_edge": self.preview_long_edge,
            "master_crf": self.master_crf,
            "preview_crf": self.preview_crf,
        }

    @classmethod
    def parse(cls, value):
        data = dict(fields(value, (), tuple(cls.__slots__) + ("fps",)))
        data.pop("fps", None)
        return cls(**data)


# ---------------------------------------------------------------- project state


@dataclass(frozen=True, slots=True)
class ProjectState:
    schema_version: ClassVar[int] = 1
    project_id: str
    version: int = 0
    phase: str = "understand"
    intent: CreativeIntent | None = None
    media: dict = field(default_factory=dict)
    analysis: dict = field(default_factory=dict)
    selection: dict = field(default_factory=dict)
    timeline: Timeline = field(default_factory=Timeline)
    audio: tuple[AudioEvent, ...] = ()
    render_settings: RenderSettings = field(default_factory=RenderSettings)
    finalized: bool = False

    def __post_init__(self):
        slug(self.project_id, "Project ID")
        integer(self.version, "Project version")
        choice(self.phase, "Phase", PHASES)
        if self.intent is not None and not isinstance(self.intent, CreativeIntent):
            raise ValidationError("Project intent must be typed")
        if not isinstance(self.timeline, Timeline):
            raise ValidationError("Project timeline must be typed")
        object.__setattr__(self, "audio", tuple(self.audio))
        boolean(self.finalized, "Finalized")

    # -- lookups -----------------------------------------------------------

    def media_item(self, media_id):
        try:
            return self.media[media_id]
        except KeyError:
            raise KeyError(f"Unknown media '{media_id}'") from None

    def frame_s(self):
        return self.render_settings.frame_s

    def quantize(self, time_s):
        """Snap a time to the project's frame grid. Timeline positions are always on frames."""
        frame = self.render_settings.frame_s
        return round(round(time_s / frame) * frame, 9)

    def quantize_ceil(self, time_s):
        """The next legal start at or after `time_s`.

        Nearest-frame rounding can step *backward*. Appending a shot that way lands inside
        the previous clip when the source was cut on a different frame grid than the
        project (24 fps takes on a 30 fps timeline, for example).
        """
        if time_s <= 0.0:
            return 0.0
        frame = self.render_settings.frame_s
        return round(math.ceil((time_s / frame) - 1e-9) * frame, 9)

    # -- wire --------------------------------------------------------------

    def wire(self):
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "version": self.version,
            "phase": self.phase,
            "intent": self.intent.wire() if self.intent else None,
            "media": {key: item.wire() for key, item in sorted(self.media.items())},
            "analysis": {key: dict(value) for key, value in sorted(self.analysis.items())},
            "selection": {key: value.wire() for key, value in sorted(self.selection.items())},
            "timeline": self.timeline.wire(),
            "audio": [item.wire() for item in self.audio],
            "render_settings": self.render_settings.wire(),
            "finalized": self.finalized,
        }


def empty(project_id, render_settings=None):
    return ProjectState(
        project_id=project_id,
        render_settings=render_settings or RenderSettings(),
    )
