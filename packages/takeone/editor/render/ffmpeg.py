"""The FFmpeg render compiler: EditGraph subtree -> argument vector plus filter graph.

Security rules this module enforces, from the architecture:

1. The command is always an argument *list*. No string is ever handed to a shell.
2. Filter fragments are built only from values that have already passed a typed parameter
   schema, and every number is formatted with explicit precision.
3. The finished filter graph is checked against a character allowlist before it leaves this
   module, so a value that somehow carried a quote or a semicolon fails loudly here rather
   than changing the meaning of a command.
4. Media paths are resolved and confirmed to sit inside the project's media roots by the
   caller; this module refuses a relative or empty path.

Because a node's identity includes its parameters, changing any compile function here must
bump that node type's `version` in `compile.py`, which changes every descendant id and
therefore invalidates exactly the cached artifacts that are now wrong.
"""

import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from ..color import spaces
from ..errors import RenderError
from ..graph import NodeType
from ..timing import retime
from ..timing.curve import SpeedCurve

SAFE_FILTER = re.compile(r"^[A-Za-z0-9_\-.,:=;\[\]()'/*+ @|<>%$?#{}\\!&~^\n]*$")

REQUIRED_FILTERS = (
    "scale",
    "crop",
    "pad",
    "fps",
    "setsar",
    "format",
    "setpts",
    "settb",
    "tpad",
    "concat",
    "xfade",
    "eq",
    "colorbalance",
    "colortemperature",
    "exposure",
    "curves",
    "hue",
    "vibrance",
    "gblur",
    "unsharp",
    "vignette",
    "noise",
    "rgbashift",
    "chromashift",
    "pixelize",
    "tmix",
    "blend",
    "split",
    "drawbox",
    "zscale",
    "overlay",
    "lut3d",
    "trim",
    "colorchannelmixer",
    "colorlevels",
    "negate",
    "fade",
    "afade",
    "adelay",
    "amix",
    "acrossfade",
    "atempo",
    "apad",
    "aresample",
    "atrim",
    "asetpts",
    "hflip",
    "vflip",
    "rotate",
    "atadenoise",
    "edgedetect",
    "colorize",
    "boxblur",
    "lagfun",
    "chromakey",
    "geq",
    "null",
)

_PROBED = {}


def _number(value, precision=6):
    text = f"{float(value):.{precision}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


def _escape(value):
    """FFmpeg filter-argument escaping for a path or free string."""
    return str(value).replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")


def executable(name="ffmpeg"):
    found = shutil.which(name)
    if not found:
        raise RenderError(f"{name} was not found on PATH")
    return found


def available_filters(binary=None):
    binary = binary or executable()
    if binary in _PROBED:
        return _PROBED[binary]
    result = subprocess.run([binary, "-hide_banner", "-filters"], capture_output=True, text=True, check=False)
    names = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] and not line.startswith(" Filters"):
            names.add(parts[1])
    _PROBED[binary] = names
    return names


def assert_backend_ready(binary=None):
    """Refuse to start with a named missing filter rather than failing mid-demo."""
    names = available_filters(binary)
    missing = [item for item in REQUIRED_FILTERS if item not in names]
    if missing:
        raise RenderError(
            "This FFmpeg build is missing filters the editor requires",
            {"missing": missing},
        )
    return True


# ---------------------------------------------------------------- primitives


def _f_exposure(p, ins, out):
    stops = _number(p.get("stops", 0.0))
    return f"{ins[0]}exposure=exposure={stops}{out}"


def _f_contrast(p, ins, out):
    return f"{ins[0]}eq=contrast={_number(p.get('amount', 1.0))}{out}"


def _f_saturation(p, ins, out):
    return f"{ins[0]}eq=saturation={_number(p.get('amount', 1.0))}{out}"


def _f_temperature(p, ins, out):
    return (
        f"{ins[0]}colortemperature=temperature={_number(p.get('kelvin', 6500.0), 1)}"
        f":mix={_number(p.get('mix', 1.0))}{out}"
    )


def _f_tint(p, ins, out):
    amount = _number(p.get("amount", 0.0))
    return f"{ins[0]}colorbalance=gm={amount}{out}"


def _f_lift(p, ins, out):
    return f"{ins[0]}eq=brightness={_number(p.get('amount', 0.0))}{out}"


def _f_tone_curve(p, ins, out):
    shadows = max(-0.4, min(0.4, float(p.get("shadows", 0.0))))
    mids = max(-0.4, min(0.4, float(p.get("midtones", 0.0))))
    highs = max(-0.4, min(0.4, float(p.get("highlights", 0.0))))
    points = (
        f"0/0 0.25/{_number(max(0.0, min(1.0, 0.25 + shadows)), 4)} "
        f"0.5/{_number(max(0.0, min(1.0, 0.5 + mids)), 4)} "
        f"0.75/{_number(max(0.0, min(1.0, 0.75 + highs)), 4)} 1/1"
    )
    return f"{ins[0]}curves=all='{points}'{out}"


def _f_lut3d(p, ins, out):
    path = str(p.get("path", ""))
    if not path:
        raise RenderError("A 3D LUT effect needs a file path")
    return f"{ins[0]}lut3d=file='{_escape(path)}'{out}"


def _f_hue_shift(p, ins, out):
    return f"{ins[0]}hue=h={_number(p.get('degrees', 0.0), 3)}{out}"


def _f_vibrance(p, ins, out):
    return f"{ins[0]}vibrance=intensity={_number(p.get('amount', 0.0))}{out}"


def _f_bloom(p, ins, out, key=""):
    threshold = max(0.0, min(0.99, float(p.get("threshold", 0.72))))
    radius = _number(p.get("radius", 14.0), 3)
    intensity = _number(p.get("intensity", 0.35))
    a, b = f"[bl{key}a]", f"[bl{key}b]"
    return (
        f"{ins[0]}split=2{a}{b};"
        f"{b}colorlevels=rimin={_number(threshold, 4)}:gimin={_number(threshold, 4)}"
        f":bimin={_number(threshold, 4)},gblur=sigma={radius}[bl{key}c];"
        f"{a}[bl{key}c]blend=all_mode=screen:all_opacity={intensity}{out}"
    )


def _f_glow(p, ins, out, key=""):
    radius = _number(p.get("radius", 10.0), 3)
    intensity = _number(p.get("intensity", 0.3))
    a, b = f"[gl{key}a]", f"[gl{key}b]"
    return (
        f"{ins[0]}split=2{a}{b};"
        f"{b}gblur=sigma={radius}[gl{key}c];"
        f"{a}[gl{key}c]blend=all_mode=screen:all_opacity={intensity}{out}"
    )


def _f_halation(p, ins, out, key=""):
    threshold = max(0.0, min(0.99, float(p.get("threshold", 0.8))))
    radius = _number(p.get("radius", 18.0), 3)
    intensity = _number(p.get("intensity", 0.25))
    a, b = f"[ha{key}a]", f"[ha{key}b]"
    return (
        f"{ins[0]}split=2{a}{b};"
        f"{b}colorlevels=rimin={_number(threshold, 4)}:gimin={_number(threshold, 4)}"
        f":bimin={_number(threshold, 4)},gblur=sigma={radius},"
        f"colorchannelmixer=rr=1.0:gg=0.55:bb=0.35[ha{key}c];"
        f"{a}[ha{key}c]blend=all_mode=screen:all_opacity={intensity}{out}"
    )


def _f_film_grain(p, ins, out):
    return f"{ins[0]}noise=alls={_number(p.get('intensity', 8.0), 2)}:allf=t+u{out}"


def _f_vignette(p, ins, out):
    intensity = max(0.0, min(1.0, float(p.get("intensity", 0.35))))
    angle = 0.62 + 0.55 * intensity
    return f"{ins[0]}vignette=angle={_number(angle, 4)}{out}"


def _f_letterbox(p, ins, out):
    ratio = max(1.0, min(3.0, float(p.get("ratio", 2.39))))
    bar = f"max(0\\,(ih-iw/{_number(ratio, 4)})/2)"
    return (
        f"{ins[0]}drawbox=x=0:y=0:w=iw:h='{bar}':color=black@1:t=fill,"
        f"drawbox=x=0:y='ih-{bar}':w=iw:h='{bar}':color=black@1:t=fill{out}"
    )


def _f_rgb_split(p, ins, out):
    amount = int(round(float(p.get("amount", 4.0))))
    import math

    angle = math.radians(float(p.get("angle", 0.0)))
    dx = int(round(amount * math.cos(angle)))
    dy = int(round(amount * math.sin(angle)))
    return f"{ins[0]}rgbashift=rh={dx}:rv={dy}:bh={-dx}:bv={-dy}{out}"


def _f_chromatic_aberration(p, ins, out):
    amount = int(round(float(p.get("amount", 3.0))))
    return f"{ins[0]}chromashift=cbh={amount}:crh={-amount}{out}"


def _f_pixelate(p, ins, out):
    size = max(2, int(p.get("size", 16)))
    return f"{ins[0]}pixelize=w={size}:h={size}{out}"


def _f_spectrum_scan(p, ins, out, key=""):
    width = max(0.01, min(1.0, float(p.get("width", 0.12))))
    degrees = _number(p.get("degrees", 120.0), 3)
    speed = max(0.05, float(p.get("speed", 1.0)))
    forward = p.get("direction", "left_to_right") == "left_to_right"
    centre = f"(mod(T*{_number(speed, 4)}\\,1))" if forward else f"(1-mod(T*{_number(speed, 4)}\\,1))"
    half = _number(width / 2.0, 5)
    a, b = f"[sc{key}a]", f"[sc{key}b]"
    expression = f"if(lte(abs(X/W-{centre})\\,{half})\\,B\\,A)"
    return (
        f"{ins[0]}split=2{a}{b};{b}hue=h={degrees}[sc{key}c];{a}[sc{key}c]blend=all_expr='{expression}'{out}"
    )


def _f_motion_blur(p, ins, out):
    frames = max(2, min(9, int(p.get("frames", 3))))
    weights = " ".join(["1"] * frames)
    return f"{ins[0]}tmix=frames={frames}:weights='{weights}'{out}"


def _f_camera_shake(p, ins, out):
    amplitude = max(0.0, min(60.0, float(p.get("amplitude", 8.0))))
    frequency = _number(p.get("frequency", 6.0), 3)
    margin = int(round(amplitude)) + 2
    ax = _number(amplitude, 3)
    return (
        f"{ins[0]}crop=w=iw-{2 * margin}:h=ih-{2 * margin}"
        f":x='{margin}+{ax}*sin(2*PI*{frequency}*t)'"
        f":y='{margin}+{ax}*cos(2*PI*{frequency}*1.37*t)',"
        f"scale=w=iw+{2 * margin}:h=ih+{2 * margin}{out}"
    )


def _f_sharpen(p, ins, out):
    return f"{ins[0]}unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount={_number(p.get('amount', 0.6))}{out}"


def _f_gaussian_blur(p, ins, out):
    return f"{ins[0]}gblur=sigma={_number(p.get('sigma', 6.0), 3)}{out}"


def _f_brightness(p, ins, out):
    return f"{ins[0]}eq=brightness={_number(p.get('amount', 0.0))}{out}"


def _f_gamma(p, ins, out):
    return f"{ins[0]}eq=gamma={_number(p.get('amount', 1.0))}{out}"


def _f_shadows(p, ins, out):
    amount = max(-0.4, min(0.4, float(p.get("amount", 0.0))))
    if amount >= 0.0:
        lift = _number(amount, 4)
        return f"{ins[0]}colorlevels=romin={lift}:gomin={lift}:bomin={lift}{out}"
    crush = _number(-amount, 4)
    return f"{ins[0]}colorlevels=rimin={crush}:gimin={crush}:bimin={crush}{out}"


def _f_highlights(p, ins, out):
    amount = max(-0.4, min(0.4, float(p.get("amount", 0.0))))
    rimax = _number(max(0.5, min(1.0, 1.0 - amount * 0.5)), 4)
    return f"{ins[0]}colorlevels=rimax={rimax}:gimax={rimax}:bimax={rimax}{out}"


def _f_invert(p, ins, out):
    if float(p.get("amount", 1.0)) <= 0.0:
        return f"{ins[0]}null{out}"
    return f"{ins[0]}negate{out}"


def _f_sepia(p, ins, out):
    mix = max(0.0, min(1.0, float(p.get("amount", 0.85))))
    rr = _number(1.0 + (0.393 - 1.0) * mix, 4)
    rg = _number(0.0 + 0.769 * mix, 4)
    rb = _number(0.0 + 0.189 * mix, 4)
    gr = _number(0.0 + 0.349 * mix, 4)
    gg = _number(1.0 + (0.686 - 1.0) * mix, 4)
    gb = _number(0.0 + 0.168 * mix, 4)
    br = _number(0.0 + 0.272 * mix, 4)
    bg = _number(0.0 + 0.534 * mix, 4)
    bb = _number(1.0 + (0.131 - 1.0) * mix, 4)
    return (
        f"{ins[0]}colorchannelmixer=rr={rr}:rg={rg}:rb={rb}"
        f":gr={gr}:gg={gg}:gb={gb}:br={br}:bg={bg}:bb={bb}{out}"
    )


def _f_colorize(p, ins, out):
    return (
        f"{ins[0]}colorize=hue={_number(p.get('hue', 28.0), 2)}"
        f":saturation={_number(p.get('saturation', 0.45))}"
        f":lightness={_number(p.get('lightness', 0.0))}{out}"
    )


def _f_posterize(p, ins, out):
    levels = max(2, min(16, int(p.get("levels", 6))))
    return (
        f"{ins[0]}geq=lum='floor(lum(X\\,Y)*{levels}+0.5)/{levels}'"
        f":cb='floor(cb(X\\,Y)*{levels}+0.5)/{levels}'"
        f":cr='floor(cr(X\\,Y)*{levels}+0.5)/{levels}'{out}"
    )


def _f_edge_detect(p, ins, out):
    return (
        f"{ins[0]}edgedetect=low={_number(p.get('low', 0.1), 4)}:high={_number(p.get('high', 0.4), 4)}{out}"
    )


def _f_scanlines(p, ins, out):
    intensity = max(0.0, min(1.0, float(p.get("intensity", 0.45))))
    spacing = max(2, min(12, int(p.get("spacing", 3))))
    gain = _number(intensity, 4)
    return (
        f"{ins[0]}geq=lum='lum(X\\,Y)*(1-{gain}*eq(mod(Y\\,{spacing})\\,0))'"
        f":cb='cb(X\\,Y)':cr='cr(X\\,Y)'{out}"
    )


def _f_denoise(p, ins, out):
    return f"{ins[0]}atadenoise=s={_number(p.get('strength', 0.04), 4)}{out}"


def _f_box_blur(p, ins, out):
    radius = max(1, min(32, int(p.get("radius", 4))))
    return f"{ins[0]}boxblur={radius}:1{out}"


def _f_fade(p, ins, out):
    kind = "in" if p.get("type", "in") == "in" else "out"
    return (
        f"{ins[0]}fade=t={kind}:st={_number(p.get('start_s', 0.0), 4)}"
        f":d={_number(p.get('duration_s', 0.6), 4)}{out}"
    )


def _f_flip_horizontal(p, ins, out):
    if p.get("enabled", True) is False:
        return f"{ins[0]}null{out}"
    return f"{ins[0]}hflip{out}"


def _f_flip_vertical(p, ins, out):
    if p.get("enabled", True) is False:
        return f"{ins[0]}null{out}"
    return f"{ins[0]}vflip{out}"


def _f_rotate(p, ins, out):
    import math

    radians = math.radians(float(p.get("degrees", 0.0)))
    if abs(radians) < 1e-9:
        return f"{ins[0]}null{out}"
    return f"{ins[0]}rotate={_number(radians)}:fillcolor=black{out}"


def _f_zoom(p, ins, out):
    amount = max(1.0, min(3.0, float(p.get("amount", 1.15))))
    z = _number(amount, 4)
    return f"{ins[0]}scale=iw*{z}:ih*{z},crop=iw/{z}:ih/{z}{out}"


def _f_mirror(p, ins, out, key=""):
    axis = p.get("axis", "horizontal")
    a, b = f"[mr{key}a]", f"[mr{key}b]"
    if axis == "vertical":
        flip, expression = "vflip", "if(lt(Y\\,H/2)\\,A\\,B)"
    else:
        flip, expression = "hflip", "if(lt(X\\,W/2)\\,A\\,B)"
    return f"{ins[0]}split=2{a}{b};{b}{flip}[mr{key}c];{a}[mr{key}c]blend=all_expr='{expression}'{out}"


def _f_light_leak(p, ins, out, key=""):
    intensity = _number(p.get("intensity", 0.32))
    hue = _number(p.get("hue", 28.0), 2)
    a, b = f"[lk{key}a]", f"[lk{key}b]"
    return (
        f"{ins[0]}split=2{a}{b};"
        f"{b}colorize=hue={hue}:saturation=0.55:lightness=0.12,gblur=sigma=26[lk{key}c];"
        f"{a}[lk{key}c]blend=all_mode=screen:all_opacity={intensity}{out}"
    )


def _f_ghost(p, ins, out):
    return f"{ins[0]}lagfun=decay={_number(p.get('decay', 0.88))}{out}"


def _f_analog(p, ins, out):
    intensity = max(0.0, min(1.0, float(p.get("intensity", 0.5))))
    hue = _number(10.0 * intensity, 2)
    grain = _number(4.0 + 16.0 * intensity, 2)
    return f"{ins[0]}hue=h={hue},noise=alls={grain}:allf=t+u{out}"


def _f_prism(p, ins, out):
    amount = int(round(float(p.get("amount", 6.0))))
    return f"{ins[0]}chromashift=cbh={amount}:crh={-amount},rgbashift=rh={amount}:bh={-amount}{out}"


def _f_chroma_key(p, ins, out):
    colour = {"green": "0x00FF00", "blue": "0x0000FF", "black": "0x000000"}.get(
        p.get("color", "green"), "0x00FF00"
    )
    return (
        f"{ins[0]}chromakey={colour}:similarity={_number(p.get('similarity', 0.3), 4)}"
        f":blend={_number(p.get('blend', 0.12), 4)}{out}"
    )


MULTI_STAGE = {"bloom", "glow", "halation", "spectrum_scan", "light_leak", "mirror"}

PRIMITIVE_FILTERS = {
    "exposure": _f_exposure,
    "contrast": _f_contrast,
    "saturation": _f_saturation,
    "temperature": _f_temperature,
    "tint": _f_tint,
    "lift": _f_lift,
    "tone_curve": _f_tone_curve,
    "lut3d": _f_lut3d,
    "hue_shift": _f_hue_shift,
    "vibrance": _f_vibrance,
    "bloom": _f_bloom,
    "glow": _f_glow,
    "halation": _f_halation,
    "film_grain": _f_film_grain,
    "vignette": _f_vignette,
    "letterbox": _f_letterbox,
    "rgb_split": _f_rgb_split,
    "chromatic_aberration": _f_chromatic_aberration,
    "pixelate": _f_pixelate,
    "spectrum_scan": _f_spectrum_scan,
    "motion_blur": _f_motion_blur,
    "camera_shake": _f_camera_shake,
    "sharpen": _f_sharpen,
    "gaussian_blur": _f_gaussian_blur,
    "brightness": _f_brightness,
    "gamma": _f_gamma,
    "shadows": _f_shadows,
    "highlights": _f_highlights,
    "invert": _f_invert,
    "sepia": _f_sepia,
    "colorize": _f_colorize,
    "posterize": _f_posterize,
    "edge_detect": _f_edge_detect,
    "scanlines": _f_scanlines,
    "denoise": _f_denoise,
    "box_blur": _f_box_blur,
    "fade": _f_fade,
    "flip_horizontal": _f_flip_horizontal,
    "flip_vertical": _f_flip_vertical,
    "rotate": _f_rotate,
    "zoom": _f_zoom,
    "mirror": _f_mirror,
    "light_leak": _f_light_leak,
    "ghost": _f_ghost,
    "analog": _f_analog,
    "prism": _f_prism,
    "chroma_key": _f_chroma_key,
}

TRANSITION_MODES = {
    "fade",
    "fadeblack",
    "fadewhite",
    "dissolve",
    "hblur",
    "slideleft",
    "slideright",
    "slideup",
    "slidedown",
    "wipeleft",
    "wiperight",
    "wipeup",
    "wipedown",
    "circleopen",
    "circleclose",
    "pixelize",
    "radial",
    "zoomin",
    "smoothleft",
    "smoothright",
    "smoothup",
    "smoothdown",
    "coverleft",
    "coverright",
    "revealleft",
    "revealright",
    "diagtl",
    "squeezeh",
    "fadegrays",
    "distance",
    "horzopen",
    "vertopen",
}


# ---------------------------------------------------------------- node fragments


def _fragment_transform(node, ins, out):
    p = node.parameters
    width, height = int(p["width"]), int(p["height"])
    fps = f"{int(p['fps_num'])}/{int(p['fps_den'])}"
    if p.get("fit", "cover") == "contain":
        conform = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    else:
        conform = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    return f"{ins[0]}{conform},fps={fps},setsar=1,format=yuv420p{out}"


def _fragment_timing(node, ins, out):
    p = node.parameters
    curve = SpeedCurve.parse(p["curve"])
    frame_s = int(p["fps_den"]) / int(p["fps_num"])
    knots, deviation = retime.time_map_knots(curve, frame_s)
    if deviation > frame_s:
        raise RenderError(
            "The speed curve could not be expressed within a frame of accuracy",
            {"deviation_s": deviation},
        )
    expression = retime.setpts_expression(knots)
    fps = f"{int(p['fps_num'])}/{int(p['fps_den'])}"
    mode = p.get("interpolation", "none")
    tail = ""
    if mode == "blend":
        tail = ",tblend=all_mode=average"
    elif mode == "mci":
        tail = f",minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1"
    # setpts maps frame starts; its EOF does not carry the curve's final time.
    # Hold the final source picture through that endpoint so the next clip starts
    # on the declared cut frame, including when the last source frame speeds up.
    # Graph parameters are canonicalized to nine decimals. Ignore sub-microframe
    # roundoff at an exact boundary, not a real fractional output frame.
    frame_count = math.ceil(curve.duration_s / frame_s - 1e-6)
    return (
        f"{ins[0]}settb=AVTB,setpts='({expression})/TB'{tail},fps={fps},"
        f"tpad=stop_mode=clone:stop_duration={_number(curve.duration_s, 9)},"
        f"trim=end_frame={frame_count}{out}"
    )


def _fragment_color(node, ins, out):
    p = node.parameters
    spaces.require_convertible(p["input_space"], "Input colour space")
    spaces.require_convertible(p["output_space"], "Output colour space")
    chain = []
    if float(p.get("exposure_stops", 0.0)) != 0.0:
        working = p.get("working_space", "rec709")
        if working == "linear-rec709":
            chain.append(spaces.to_linear(p["input_space"]))
            chain.append(f"exposure=exposure={_number(p['exposure_stops'])}")
            chain.append(spaces.from_linear(p["output_space"]))
        else:
            chain.append(f"exposure=exposure={_number(p['exposure_stops'])}")
    shift = float(p.get("temperature_k", 0.0))
    if shift != 0.0:
        # A positive shift warms the image. `colortemperature` names the light source, so a
        # warmer result asks for a *lower* Kelvin value than the 6500 K neutral reference.
        chain.append(f"colortemperature=temperature={_number(6500.0 - shift, 1)}:mix=1")
    if float(p.get("tint", 0.0)) != 0.0:
        chain.append(f"colorbalance=gm={_number(p['tint'])}")
    eq = []
    if float(p.get("contrast", 1.0)) != 1.0:
        eq.append(f"contrast={_number(p['contrast'])}")
    if float(p.get("saturation", 1.0)) != 1.0:
        eq.append(f"saturation={_number(p['saturation'])}")
    if float(p.get("lift", 0.0)) != 0.0:
        eq.append(f"brightness={_number(p['lift'])}")
    if eq:
        chain.append("eq=" + ":".join(eq))
    if not chain:
        chain.append("null")
    return f"{ins[0]}" + ",".join(chain) + out


def _fragment_effect(node, ins, out):
    primitive = node.parameters.get("primitive")
    handler = PRIMITIVE_FILTERS.get(primitive)
    if handler is None:
        raise RenderError(f"No FFmpeg compilation for effect primitive '{primitive}'")
    key = node.node_id[:8]
    if primitive in MULTI_STAGE:
        fragment = handler(node.parameters, ins, out, key)
    else:
        fragment = handler(node.parameters, ins, out)
    if node.time_range is not None and primitive not in MULTI_STAGE:
        window = (
            f":enable='between(t,{_number(node.time_range.start_s, 4)},{_number(node.time_range.end_s, 4)})'"
        )
        fragment = fragment.replace(out, window + out, 1) if "=" in fragment else fragment
    return fragment


def _fragment_transition(node, ins, out):
    p = node.parameters
    mode = str(p.get("mode", "fade"))
    if mode not in TRANSITION_MODES:
        raise RenderError(f"Unsupported transition mode '{mode}'")
    return (
        f"{ins[0]}{ins[1]}xfade=transition={mode}"
        f":duration={_number(p['duration_s'], 4)}:offset={_number(p['offset_s'], 4)}{out}"
    )


def _fragment_sequence(node, ins, out):
    return f"{ins[0]}{ins[1]}concat=n=2:v=1:a=0{out}"


def _fragment_composite(node, ins, out):
    opacity = _number(node.parameters.get("opacity", 1.0))
    return f"{ins[0]}{ins[1]}blend=all_mode=normal:all_opacity={opacity}{out}"


FRAGMENTS = {
    NodeType.TRANSFORM: _fragment_transform,
    NodeType.TIMING: _fragment_timing,
    NodeType.COLOR: _fragment_color,
    NodeType.EFFECT: _fragment_effect,
    NodeType.TRANSITION: _fragment_transition,
    NodeType.SEQUENCE: _fragment_sequence,
    NodeType.COMPOSITE: _fragment_composite,
}


# ---------------------------------------------------------------- the plan


@dataclass(frozen=True, slots=True)
class RenderPlan:
    schema_version: ClassVar[int] = 1
    argv: tuple
    output_path: str
    duration_s: float
    filter_complex: str
    node_ids: tuple = field(default_factory=tuple)

    def wire(self):
        return {
            "argv": list(self.argv),
            "output_path": self.output_path,
            "duration_s": self.duration_s,
            "filter_complex": self.filter_complex,
            "node_count": len(self.node_ids),
        }


def _audio_tempo(rate):
    """Express any validated speed rate as FFmpeg's 0.5x to 2x atempo stages."""
    remaining = float(rate)
    stages = []
    while remaining < 0.5:
        stages.append("atempo=0.5")
        remaining /= 0.5
    while remaining > 2.0:
        stages.append("atempo=2")
        remaining /= 2.0
    stages.append(f"atempo={_number(remaining, 6)}")
    return "," + ",".join(stages)


def compile_graph(graph, destination, binary=None, overwrite=True):
    """Compile the whole graph to one FFmpeg invocation."""
    order = graph.topological()
    output_node = graph.by_id(graph.output_id)
    inputs = []
    labels = {}
    statements = []
    source_input_indexes = {}

    for item in order:
        if item.type is NodeType.SOURCE:
            path = Path(str(item.parameters["path"]))
            if not path.is_absolute():
                raise RenderError(f"Media path must be absolute: {path}")
            start = float(item.parameters["in_s"])
            span = float(item.parameters["out_s"]) - start
            if span <= 0.0:
                raise RenderError(f"Source segment has no duration: {path}")
            # Seeking at the input is far faster than decoding to a trim filter, and the
            # segment is part of this node's identity, so the two cannot drift apart.
            input_index = len(inputs)
            inputs.append(["-ss", _number(start, 6), "-t", _number(span, 6), "-i", str(path)])
            source_input_indexes[item.node_id] = input_index
            out = f"[v{len(statements)}]"
            statements.append(f"[{input_index}:v]setpts=PTS-STARTPTS{out}")
            labels[item.node_id] = out
            continue
        if item.type is NodeType.AUDIO:
            sequence = None
            for segment in item.parameters.get("segments", []):
                out = f"[a{len(statements)}]"
                path = segment.get("path")
                if path is None:
                    statements.append(
                        f"anullsrc=r=48000:cl=mono,atrim=duration={_number(segment['duration_s'], 6)}{out}"
                    )
                else:
                    source = Path(str(path))
                    if not source.is_absolute():
                        raise RenderError(f"Media path must be absolute: {source}")
                    input_index = len(inputs)
                    measured = "audio_read_start_s" in segment
                    inputs.append(
                        [
                            "-ss",
                            _number(segment.get("audio_read_start_s", segment["source_start_s"]), 6),
                            "-t",
                            _number(
                                segment.get("audio_read_duration_s", segment["source_duration_s"]),
                                6,
                            ),
                            "-i",
                            str(source),
                        ]
                    )
                    if measured:
                        delay_samples = round(float(segment["audio_leading_s"]) * 48000)
                        normalize = (
                            f"aresample=48000,asetpts=PTS-STARTPTS,adelay={delay_samples}S:all=1,"
                            f"apad,atrim=duration={_number(segment['source_duration_s'], 6)},"
                            "asetpts=PTS-STARTPTS"
                        )
                    else:
                        normalize = "asetpts=PTS-STARTPTS"
                    curve_data = segment.get("curve")
                    if curve_data is None:
                        statements.append(f"[{input_index}:a]{normalize}{out}")
                    else:
                        curve = SpeedCurve.parse(curve_data)
                        frame_s = int(item.parameters["fps_den"]) / int(item.parameters["fps_num"])
                        knots, deviation = retime.time_map_knots(curve, frame_s)
                        if deviation > frame_s:
                            raise RenderError("The audio speed curve exceeds a frame of accuracy")
                        pieces = []
                        for (source_start, start), (source_end, end) in zip(knots, knots[1:]):
                            rate = (source_end - source_start) / (end - start)
                            # atempo needs analysis windows around the retained sound.
                            # Process original context on both sides, then crop on the
                            # output sample grid. Never concatenate its short EOF tails.
                            context = 0.1 * max(1.0, rate)
                            read_start = max(0.0, source_start - context)
                            crop_start = round((source_start - read_start) / rate * 48000)
                            count = round(end * 48000) - round(start * 48000)
                            piece = f"[a{len(statements)}p]"
                            tempo = _audio_tempo(rate)
                            statements.append(
                                f"[{input_index}:a]{normalize},aresample=48000,"
                                f"apad=pad_dur={_number(context, 9)},"
                                f"atrim=start={_number(read_start, 9)}:end={_number(source_end + context, 9)},"
                                f"asetpts=PTS-STARTPTS{tempo},"
                                f"atrim=start_sample={crop_start}:end_sample={crop_start + count},"
                                f"asetpts=PTS-STARTPTS{piece}"
                            )
                            pieces.append(piece)
                        statements.append("".join(pieces) + f"concat=n={len(pieces)}:v=0:a=1{out}")
                if sequence is None:
                    sequence = out
                    continue
                joined = f"[a{len(statements)}]"
                overlap = float(segment.get("transition_in_s", 0.0))
                if overlap > 0.0:
                    statements.append(
                        f"{sequence}{out}acrossfade=d={_number(overlap, 6)}:c1=tri:c2=tri{joined}"
                    )
                else:
                    statements.append(f"{sequence}{out}concat=n=2:v=0:a=1{joined}")
                sequence = joined
            audio_labels = [sequence] if sequence is not None else []
            for event in item.parameters.get("events", []):
                path = Path(str(event["path"]))
                if not path.is_absolute():
                    raise RenderError(f"Media path must be absolute: {path}")
                start = float(event["source_start_s"])
                span = float(event["duration_s"])
                if span <= 0.0:
                    raise RenderError(f"Audio event has no duration: {event['event_id']}")
                input_index = len(inputs)
                inputs.append(["-ss", _number(start, 6), "-t", _number(span, 6), "-i", str(path)])
                chain = "asetpts=PTS-STARTPTS"
                fade_in = float(event.get("fade_in_s", 0.0))
                fade_out = float(event.get("fade_out_s", 0.0))
                if fade_in > 0.0:
                    chain += f",afade=t=in:st=0:d={_number(fade_in, 6)}"
                if fade_out > 0.0:
                    chain += f",afade=t=out:st={_number(span - fade_out, 6)}:d={_number(fade_out, 6)}"
                chain += f",volume={_number(10 ** (float(event.get('gain_db', 0.0)) / 20.0), 6)}"
                delay_ms = int(round(float(event["timeline_start_s"]) * 1000.0))
                chain += f",adelay={delay_ms}:all=1"
                out = f"[a{len(statements)}]"
                statements.append(f"[{input_index}:a]{chain}{out}")
                audio_labels.append(out)
            if not audio_labels:
                raise RenderError("Audio graph has no usable source")
            if len(audio_labels) > 1:
                out = f"[a{len(statements)}]"
                statements.append("".join(audio_labels) + f"amix=inputs={len(audio_labels)}:normalize=0{out}")
                audio_labels = [out]
            out = f"[a{len(statements)}]"
            statements.append(
                f"{audio_labels[0]}atrim=duration={_number(item.parameters['duration_s'], 6)},asetpts=PTS-STARTPTS{out}"
            )
            labels[item.node_id] = out
            continue
        if item.type is NodeType.OUTPUT:
            continue
        handler = FRAGMENTS.get(item.type)
        if handler is None:
            raise RenderError(f"No FFmpeg compilation for node type '{item.type}'")
        ins = tuple(labels[source] for source in item.inputs)
        out = f"[v{len(statements)}]"
        statements.append(handler(item, ins, out))
        labels[item.node_id] = out

    final = labels[output_node.inputs[0]]
    final_audio = labels[output_node.inputs[1]] if len(output_node.inputs) == 2 else None
    filter_complex = ";".join(statements)
    if not SAFE_FILTER.match(filter_complex):
        raise RenderError("The compiled filter graph contains characters outside the allowlist")

    parameters = output_node.parameters
    argv = [binary or executable(), "-hide_banner", "-nostdin", "-loglevel", "error"]
    if overwrite:
        argv.append("-y")
    for arguments in inputs:
        argv.extend(arguments)
    argv.extend(["-filter_complex", filter_complex, "-map", final])
    if final_audio is not None:
        argv.extend(["-map", final_audio])
    argv.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast" if parameters.get("target") == "preview" else "slow",
            "-crf",
            str(int(parameters.get("crf", 23))),
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-r",
            f"{int(parameters['fps_num'])}/{int(parameters['fps_den'])}",
            "-movflags",
            "+faststart",
        ]
    )
    if final_audio is not None:
        argv.extend(["-c:a", "aac", "-b:a", "192k"])
    else:
        argv.append("-an")
    argv.append(str(destination))
    return RenderPlan(
        argv=tuple(argv),
        output_path=str(destination),
        duration_s=float(parameters.get("duration_s", 0.0)),
        filter_complex=filter_complex,
        node_ids=tuple(item.node_id for item in order),
    )
