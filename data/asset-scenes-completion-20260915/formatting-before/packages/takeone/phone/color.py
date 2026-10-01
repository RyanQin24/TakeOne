"""LUT file validation and explicit capture-space/monitoring provenance."""

import hashlib
import math
from urllib.parse import quote

from .client import CameraError

SPACES = ("rec709", "apple_log2")


def validate_cube(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 4 * 1024 * 1024:
        raise ValueError("Choose a .cube file smaller than 4 MiB.")
    size, count, domain = None, 0, {}
    for raw in text.splitlines():
        row = raw.split("#", 1)[0].strip().split()
        if not row or row[0] == "TITLE":
            continue
        if row[0] == "LUT_3D_SIZE":
            if size is not None or len(row) != 2 or row[1] not in ("17", "33"):
                raise ValueError("Blackmagic LUTs need one LUT_3D_SIZE of 17 or 33.")
            size = int(row[1])
            continue
        if row[0] in ("DOMAIN_MIN", "DOMAIN_MAX"):
            if row[0] in domain or len(row) != 4:
                raise ValueError("Invalid or duplicate LUT domain.")
            domain[row[0]] = tuple(float(v) for v in row[1:])
            continue
        if size is None or len(row) != 3:
            raise ValueError("LUT data needs a size header and three numeric components per row.")
        values = [float(value) for value in row]
        if any(not math.isfinite(value) or abs(value) > 16 for value in values):
            raise ValueError("LUT values must be finite and between -16 and 16.")
        count += 1
        if count > size ** 3:
            raise ValueError("Too many LUT rows.")
    if size is None or count != size ** 3:
        raise ValueError("LUT row count does not match its cube dimensions.")
    if domain.get("DOMAIN_MIN", (0, 0, 0)) != (0, 0, 0) or domain.get("DOMAIN_MAX", (1, 1, 1)) != (1, 1, 1):
        raise ValueError("This phone workflow requires a normalized 0-1 LUT input domain.")
    return dict(size=size, sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), rows=count)


def color_recipe(value, *, ready=False):
    keys = {"capture_space", "lut_input_space", "lut_name", "mode", "operator_confirmed", "display", "cube_sha256"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Supply the complete capture/LUT recipe.")
    if value["capture_space"] not in SPACES or value["lut_input_space"] not in SPACES:
        raise ValueError("Choose Rec.709 or Apple Log 2 explicitly.")
    if value["capture_space"] != value["lut_input_space"]:
        raise ValueError("LUT input space must match capture: a Rec.709 look is not an Apple Log 2 transform.")
    if value["mode"] not in ("monitor", "bake") or type(value["operator_confirmed"]) is not bool:
        raise ValueError("Choose monitor or bake, with explicit phone setup confirmation.")
    for key in ("lut_name", "display", "cube_sha256"):
        if not isinstance(value[key], str) or len(value[key]) > 160:
            raise ValueError(f"Invalid color field: {key}.")
    digest = value["cube_sha256"]
    if digest and (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
        raise ValueError("LUT hash must identify the exact registered cube file.")
    if ready and (not value["operator_confirmed"] or not value["lut_name"].strip()):
        raise ValueError("Select the matching LUT/capture space on the phone and confirm its setup first.")
    return dict(value)


def apply_color(client, recipe):
    recipe = color_recipe(recipe, ready=True)
    evidence = dict(recipe, selection_source="operator_reported", baked_pixels_verified=False,
                    display_enabled_source="operator_reported")
    if recipe["display"]:
        path = "/monitoring/" + quote(recipe["display"], safe="") + "/displayLUT"
        client.request("PUT", path, {"enabled": True})
        observed = client.request("GET", path)
        if not isinstance(observed, dict) or observed.get("enabled") is not True:
            raise CameraError("The phone did not confirm that its display LUT is enabled.")
        evidence["display_enabled_source"] = "device_reported"
    return evidence
