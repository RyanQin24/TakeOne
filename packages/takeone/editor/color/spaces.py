"""Named colour spaces and the transfer stages between them.

This module exists so that swapping the implementation for OpenColorIO later changes one
compiler rather than the graph, the operations or the interface. A LUT is not a colour
management architecture; the named stages are.
"""

from ..errors import ValidationError

INPUT_SPACES = ("rec709", "srgb", "apple-log", "rec2100-pq")
WORKING_SPACES = ("rec709", "linear-rec709")
OUTPUT_SPACES = ("rec709", "srgb")

# Transfer characteristics understood by the current backend. A space that is listed as an
# input but has no entry here is a space we can *describe* but cannot yet *convert*, and the
# compiler must refuse it rather than silently treating it as Rec.709.
TRANSFER = {
    "rec709": "bt709",
    "srgb": "iec61966-2-1",
    "linear-rec709": "linear",
}

PRIMARIES = {
    "rec709": "bt709",
    "srgb": "bt709",
    "linear-rec709": "bt709",
}

# The YUV matrix a space is normally carried in. Linear working space is held as full-range
# planar RGB (`gbr`), because a linear transfer function cannot be combined with a YUV
# matrix: that combination is what "no path between colorspaces" means when it is attempted.
MATRIX = {
    "rec709": "bt709",
    "srgb": "bt709",
    "linear-rec709": "gbr",
}

LINEAR_PIXEL_FORMAT = "gbrpf32le"
NOMINAL_PEAK_LUMINANCE = 100


def validate_space(name, allowed, label):
    if name not in allowed:
        raise ValidationError(f"{label} must be one of {sorted(allowed)}")
    return name


def convertible(name):
    return name in TRANSFER


def require_convertible(name, label):
    if not convertible(name):
        raise ValidationError(
            f"{label} '{name}' is described but has no conversion in this backend. "
            "Add its transfer function before using it; it will not be treated as Rec.709."
        )
    return name


def transfer(name):
    return TRANSFER[require_convertible(name, "Colour space")]


def primaries(name):
    return PRIMARIES[require_convertible(name, "Colour space")]


def matrix(name):
    return MATRIX[require_convertible(name, "Colour space")]


def to_linear(source):
    """Filter chain taking `source` into the linear working space, stated explicitly.

    Every field is named rather than left to be inferred: an unstated matrix is the usual
    cause of a silent or failed conversion, and guessing here would make a grade wrong in a
    way nobody notices until the master render.
    """
    return (
        f"zscale=tin={transfer(source)}:min={matrix(source)}:pin={primaries(source)}"
        f":t=linear:m={matrix('linear-rec709')}:p={primaries(source)}"
        f":npl={NOMINAL_PEAK_LUMINANCE},format={LINEAR_PIXEL_FORMAT}"
    )


def from_linear(destination, pixel_format="yuv420p"):
    return (
        f"zscale=tin=linear:min={matrix('linear-rec709')}:pin={primaries(destination)}"
        f":t={transfer(destination)}:m={matrix(destination)}:p={primaries(destination)}"
        f",format={pixel_format}"
    )
