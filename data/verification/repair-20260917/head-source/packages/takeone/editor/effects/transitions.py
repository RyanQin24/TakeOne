"""Two-input effects. A transition is an effect with arity two; nothing else differs."""

from ..operations import ParamSpec as P
from .spec import EffectSpec

DURATION = P("duration_s", "seconds", False, 0.04, 5.0, default=0.4)
OFFSET = P("offset_s", "seconds", False, 0.0, 36000.0, default=0.0)


def _transition(identifier, name, mode, description, extra=()):
    return EffectSpec(
        id=identifier,
        version=1,
        name=name,
        category="transition",
        parameters=(DURATION, OFFSET, P("mode", "text", False, maximum=32, default=mode)) + tuple(extra),
        arity=2,
        primitive=True,
        description=description,
        tags=("transition",),
    )


TRANSITIONS = (
    _transition("crossfade", "Crossfade", "fade", "A dissolve between two shots."),
    _transition(
        "dip_to_black",
        "Dip to black",
        "fadeblack",
        "Falls to black and back; a beat of silence between ideas.",
    ),
    _transition("flash", "Flash", "fadewhite", "A white flash on an impact."),
    _transition("whip", "Whip", "hblur", "Horizontal blur carrying a camera whip across the cut."),
    _transition(
        "match_cut",
        "Match cut",
        "dissolve",
        "A short dissolve used where movement or shape continues across the cut.",
    ),
    _transition("wipe_left", "Wipe left", "wipeleft", "The incoming shot wipes in from the right."),
    _transition("wipe_right", "Wipe right", "wiperight", "The incoming shot wipes in from the left."),
    _transition("wipe_up", "Wipe up", "wipeup", "A vertical wipe rising through the frame."),
    _transition("wipe_down", "Wipe down", "wipedown", "A vertical wipe falling through the frame."),
    _transition("slide_left", "Slide left", "slideleft", "The outgoing shot is pushed off to the left."),
    _transition("slide_right", "Slide right", "slideright", "The outgoing shot is pushed off to the right."),
    _transition("slide_up", "Slide up", "slideup", "A vertical slide, incoming from below."),
    _transition("slide_down", "Slide down", "slidedown", "A vertical slide, incoming from above."),
    _transition("circle_open", "Iris open", "circleopen", "The incoming shot opens from the centre."),
    _transition("circle_close", "Iris close", "circleclose", "The outgoing shot closes to a point."),
    _transition("pixelize_cut", "Pixelize", "pixelize", "The cut dissolves through a mosaic."),
    _transition("radial", "Radial", "radial", "A radial wipe around the frame."),
    _transition("zoom_in", "Zoom through", "zoomin", "The incoming shot punches through the cut."),
    _transition("smooth_left", "Smooth wipe left", "smoothleft", "A softened directional wipe."),
    _transition("smooth_right", "Smooth wipe right", "smoothright", "A softened wipe the other way."),
    _transition("cover_left", "Cover left", "coverleft", "The incoming shot covers from the right."),
    _transition("reveal_left", "Reveal left", "revealleft", "The outgoing shot pulls away to the left."),
    _transition("diagonal", "Diagonal", "diagtl", "A diagonal wipe from the top left."),
    _transition("squeeze", "Squeeze", "squeezeh", "The outgoing shot is squeezed out horizontally."),
    _transition(
        "fade_gray", "Fade through grey", "fadegrays", "A dissolve that passes through grey, not black."
    ),
    _transition("distance", "Distance", "distance", "A spatial dissolve that feels like pulling focus."),
    _transition("barn_doors", "Barn doors", "horzopen", "The frame opens from the centre line."),
    _transition("vert_open", "Vertical open", "vertopen", "The frame opens from a vertical split."),
)


def install(registry):
    for spec in TRANSITIONS:
        registry.register(spec)
    return registry
