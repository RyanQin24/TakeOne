"""Photo-based cart and original SO-101 chains with interchangeable lights.

Confirmed: 1.23 m mount height, 19 cm drive-wheel diameter, 6 cm tire width.
Local +Y is filming front. Powered wheels face -X. Each complete arm chain
uses the separately declared mount yaw; the lower-cart rotation is independent.
"""

import math
import xml.etree.ElementTree as ET
from pathlib import Path

from takeone.config import LIGHT_TYPES, rig_config
from takeone.paths import MODELS as ROOT
from takeone.paths import REFERENCE
from takeone.simulation.drive import (
    AXLE_OFFSET,
    CASTER_OFFSET,
    CASTER_RADIUS,
    CASTER_TRACK,
    CASTER_TRAIL,
    CASTER_WIDTH,
    FORWARD_SIGN,
    WHEEL_RADIUS,
    WHEEL_WIDTH,
)

SOURCE = REFERENCE / "rig_5dof.xml"
DESTINATION = ROOT / "rig_tall.xml"
MOUNT_HEIGHT = rig_config()["upper"]["mount_height_m"]
ARM_MOUNT_YAW_DEG = rig_config()["upper"]["arm_mount_yaw_deg"]
BLACK = ".055 .06 .065 1"
GRAY = ".48 .49 .50 1"
SILVER = ".58 .62 .65 1"


def geom(parent, name, kind, pos, size, color=BLACK, mass=0, **kwargs):
    return ET.SubElement(
        parent,
        "geom",
        name=name,
        type=kind,
        pos=" ".join(map(str, pos)),
        size=" ".join(map(str, size)),
        rgba=color,
        mass=str(mass),
        **kwargs,
    )


def annulus(path, outer=0.15, inner=0.122, depth=0.016, segments=64):
    """Watertight visual ring; separate convex segments model collisions."""
    vertices, faces = [], []
    for z in [-depth / 2, depth / 2]:
        for r in [outer, inner]:
            for i in range(segments):
                a = 2 * math.pi * i / segments
                vertices.append((r * math.cos(a), r * math.sin(a), z))
    for i in range(segments):
        j = (i + 1) % segments
        n = segments
        for quad in [
            (i, j, n + j, n + i),
            (2 * n + i, 3 * n + i, 3 * n + j, 2 * n + j),
            (i, 2 * n + i, 2 * n + j, j),
            (n + i, n + j, 3 * n + j, 3 * n + i),
        ]:
            faces.extend([(quad[0], quad[2], quad[1]), (quad[0], quad[3], quad[2])])
    path.write_text(
        "\n".join(
            ["v " + " ".join(map(str, v)) for v in vertices]
            + ["f " + " ".join(str(k + 1) for k in f) for f in faces]
        )
        + "\n"
    )


def build(light_type="ring"):
    if light_type not in LIGHT_TYPES:
        raise ValueError("Unknown light type")
    tree = ET.parse(SOURCE)
    root = tree.getroot()
    root.set("model", f"TAKE_ONE_photo_cart_front_phone_rear_{light_type}")
    root.find("compiler").set("meshdir", ".")
    for m in root.findall("./asset/mesh"):
        m.set("name", Path(m.get("file")).stem)
        m.set("file", "../reference/upstream/assets/" + m.get("file"))
    for material in root.findall("./asset/material"):
        if "sts3215" not in material.get("name"):
            material.set("rgba", GRAY)
    cart = root.find(".//body[@name='cart']")
    for g in list(cart.findall("geom")):
        cart.remove(g)
    # Open trolley: low equipment shelf, work deck, corner legs.
    geom(cart, "cart_box", "box", (0, 0, 0.13), (0.26, 0.40, 0.018), mass=2)
    geom(cart, "cart_work_deck", "box", (0, 0, 0.48), (0.26, 0.40, 0.018), mass=1)
    for z in [0.15, 0.49]:
        for x in [-0.25, 0.25]:
            geom(cart, f"frame_side_{x}_{z}", "box", (x, 0, z), (0.022, 0.41, 0.024))
        for y in [-0.39, 0.39]:
            geom(cart, f"frame_end_{y}_{z}", "box", (0, y, z), (0.26, 0.022, 0.024))
    for x in [-0.24, 0.24]:
        for y in [-0.38, 0.38]:
            geom(cart, f"corner_leg_{x}_{y}", "box", (x, y, 0.31), (0.023, 0.023, 0.17))
            geom(cart, f"corner_cap_{x}_{y}", "box", (x, y, 0.518), (0.029, 0.029, 0.003), SILVER)
    for x in [-0.29, 0.29]:
        geom(
            cart,
            f"drive_tire_{x}",
            "cylinder",
            (x, AXLE_OFFSET, WHEEL_RADIUS),
            (WHEEL_RADIUS, WHEEL_WIDTH / 2),
            mass=0.12,
            quat=".70710678 0 .70710678 0",
        )
        geom(
            cart,
            f"drive_hub_{x}",
            "cylinder",
            (x + math.copysign(0.031, x), AXLE_OFFSET, WHEEL_RADIUS),
            (0.064, 0.003),
            SILVER,
            quat=".70710678 0 .70710678 0",
        )
        geom(
            cart,
            f"drive_axle_{x}",
            "cylinder",
            (x + math.copysign(0.035, x), AXLE_OFFSET, WHEEL_RADIUS),
            (0.024, 0.004),
            BLACK,
            quat=".70710678 0 .70710678 0",
        )
        geom(
            cart,
            f"drive_marker_{x}",
            "box",
            (x + math.copysign(0.036, x), AXLE_OFFSET + 0.036, WHEEL_RADIUS),
            (0.002, 0.026, 0.008),
            ".15 .20 .24 1",
            group="2",
            contype="0",
            conaffinity="0",
        )
        caster_x = math.copysign(CASTER_TRACK / 2, x)
        contact_y = CASTER_OFFSET - FORWARD_SIGN * CASTER_TRAIL
        geom(
            cart,
            f"caster_bearing_{x}",
            "cylinder",
            (caster_x, CASTER_OFFSET, 0.112),
            (0.021, 0.01),
            SILVER,
        )
        for fork_side in (-1, 1):
            geom(
                cart,
                f"caster_fork_{fork_side}_{x}",
                "box",
                (caster_x + fork_side * (CASTER_WIDTH / 2 + 0.005), (CASTER_OFFSET + contact_y) / 2, 0.081),
                (0.004, CASTER_TRAIL / 2 + 0.015, 0.025),
                SILVER,
            )
        geom(
            cart,
            f"caster_tire_{x}",
            "cylinder",
            (caster_x, contact_y, CASTER_RADIUS),
            (CASTER_RADIUS, CASTER_WIDTH / 2),
            quat=".70710678 0 .70710678 0",
            mass=0.04,
        )
    # Twin uprights support the front phone and rear light. Their 0.51 m
    # lower attachment is preserved while the measured platform sets the top.
    upright_bottom = 0.51
    deck_half_height = 0.01
    upright_top = MOUNT_HEIGHT - 2 * deck_half_height
    upright_half_height = (upright_top - upright_bottom) / 2
    upright_center = upright_bottom + upright_half_height
    for name, y in [("front", 0.23), ("rear", -0.23)]:
        geom(
            cart,
            f"upright_{name}",
            "box",
            (0, y, upright_center),
            (0.047, 0.047, upright_half_height),
            mass=0.25,
        )
        geom(
            cart,
            f"mast_cable_{name}",
            "box",
            (0.049, y, upright_center),
            (0.002, 0.003, upright_half_height - 0.015),
            ".3 .09 .07 1",
        )
    geom(
        cart,
        "cart_deck",
        "box",
        (0, 0, MOUNT_HEIGHT - deck_half_height),
        (0.115, 0.34, deck_half_height),
        mass=0.5,
    )
    for name, y in [("phone", 0.23), ("light", -0.23)]:
        geom(
            cart,
            f"mount_plate_{name}",
            "box",
            (0, y, MOUNT_HEIGHT - 0.003),
            (0.075, 0.085, 0.003),
            SILVER,
        )
    # Simplified equipment silhouettes from the supplied photos.
    geom(cart, "battery", "box", (-0.12, -0.23, 0.215), (0.085, 0.11, 0.065))
    geom(cart, "battery_label", "box", (-0.12, -0.341, 0.215), (0.062, 0.002, 0.032), ".58 .7 .13 1")
    geom(cart, "electronics_box", "box", (0, 0.285, 0.23), (0.18, 0.087, 0.075), ".49 .62 .59 .38")
    geom(cart, "electronics_board", "box", (0, 0.28, 0.20), (0.14, 0.066, 0.008), ".07 .35 .24 1")
    geom(cart, "status_led", "box", (0.12, 0.374, 0.22), (0.009, 0.002, 0.012), ".1 1 .3 1")
    geom(cart, "laptop_keyboard", "box", (0.06, -0.20, 0.51), (0.135, 0.095, 0.006), ".25 .27 .29 1")
    geom(cart, "laptop_lid", "box", (0.06, -0.30, 0.602), (0.135, 0.006, 0.095), BLACK, euler="-.18 0 0")
    geom(
        cart,
        "laptop_screen",
        "box",
        (0.06, -0.291, 0.603),
        (0.123, 0.002, 0.081),
        ".09 .22 .32 1",
        euler="-.18 0 0",
    )
    geom(cart, "controller_board", "box", (0.15, 0.19, 0.507), (0.04, 0.03, 0.006), ".06 .46 .61 1")
    # Rotate ONLY the lower cart. Upper geoms and arm bodies retain exact transforms.
    lower = ET.SubElement(cart, "body", name="lower_cart", quat=".7071067811865476 0 0 -.7071067811865476")
    for g in list(cart.findall("geom")):
        if g.get("name") == "cart_deck" or g.get("name").startswith(
            ("upright_", "mast_cable_", "mount_plate_")
        ):
            continue
        cart.remove(g)
        lower.append(g)
    for side, x in [("left", -FORWARD_SIGN * 0.29), ("right", FORWARD_SIGN * 0.29)]:
        wheel = ET.SubElement(lower, "body", name=f"drive_{side}", pos=f"{x} {AXLE_OFFSET} {WHEEL_RADIUS}")
        for prefix in ["drive_tire", "drive_hub", "drive_axle", "drive_marker"]:
            g = lower.find(f"geom[@name='{prefix}_{x}']")
            p = list(map(float, g.get("pos").split()))
            g.set("pos", f"{p[0] - x} {p[1] - AXLE_OFFSET} {p[2] - WHEEL_RADIUS}")
            lower.remove(g)
            wheel.append(g)
        caster_x = math.copysign(CASTER_TRACK / 2, x)
        caster = ET.SubElement(
            lower, "body", name=f"caster_{side}", pos=f"{caster_x} {CASTER_OFFSET} {CASTER_RADIUS}"
        )
        for prefix in ["caster_fork_-1", "caster_fork_1", "caster_tire"]:
            g = lower.find(f"geom[@name='{prefix}_{x}']")
            p = list(map(float, g.get("pos").split()))
            g.set("pos", f"{p[0] - caster_x} {p[1] - CASTER_OFFSET} {p[2] - CASTER_RADIUS}")
            lower.remove(g)
            caster.append(g)
    ET.SubElement(
        cart,
        "site",
        name="drive_axle_midpoint",
        pos=f"{AXLE_OFFSET} 0 {WHEEL_RADIUS}",
        size=".004",
        group="3",
    )
    for name, y in [("cam_base", 0.23), ("light_base", -0.23)]:
        arm_base = cart.find(f"body[@name='{name}']")
        arm_base.set("pos", f"0 {y} {MOUNT_HEIGHT}")
        half_yaw = math.radians(ARM_MOUNT_YAW_DEG) / 2
        arm_base.set("quat", f"{math.cos(half_yaw)} 0 0 {math.sin(half_yaw)}")
    phone = root.find(".//body[@name='cam_tool_carrier']")
    phone.find("geom[@name='cam_payload']").set("rgba", ".09 .095 .10 1")
    geom(phone, "phone_wrist_adapter", "box", (0, -0.012, -0.011), (0.020, 0.036, 0.012))
    # Decorative parts are massless; phone retains the assumed .30 kg payload.
    geom(phone, "phone_screen", "box", (0, 0, -0.037), (0.036, 0.075, 0.001), ".06 .16 .23 1")
    geom(phone, "phone_clamp", "box", (0, -0.035, -0.026), (0.049, 0.018, 0.008))
    for x in [-0.043, 0.043]:
        geom(phone, f"phone_clamp_jaw_{x}", "box", (x, -0.035, -0.043), (0.004, 0.02, 0.019))
    for y in [0.05, 0.027, 0.004]:
        geom(phone, f"phone_lens_{y}", "cylinder", (0.025, y, -0.055), (0.009, 0.004), SILVER)
        geom(phone, f"phone_glass_{y}", "cylinder", (0.025, y, -0.0595), (0.0065, 0.0005), ".02 .05 .08 1")
    light = root.find(".//body[@name='light_tool_carrier']")
    light.remove(light.find("geom[@name='light_payload']"))
    # Original optical transform and unscaled arm chain. Local -Z emits light.
    center = (0.025, 0.05, -0.06)
    geom(light, "light_adapter", "box", (0.0125, 0.015, -0.022), (0.024, 0.045, 0.013))
    if light_type == "ring":
        geom(light, "ring_yoke", "box", (0.025, -0.036, -0.022), (0.016, 0.065, 0.009))
        geom(light, "ring_rim_bracket", "box", (0.025, -0.092, -0.046), (0.014, 0.014, 0.024))
        assets = ROOT / "assets"
        assets.mkdir(exist_ok=True)
        annulus(assets / "ring_housing.obj")
        annulus(assets / "ring_diffuser.obj", 0.146, 0.125, 0.003)
        for name in ["ring_housing", "ring_diffuser"]:
            ET.SubElement(root.find("asset"), "mesh", name=name, file=f"assets/{name}.obj")
        ET.SubElement(
            light,
            "geom",
            name="light_payload",
            type="mesh",
            mesh="ring_housing",
            pos=" ".join(map(str, center)),
            rgba=BLACK,
            mass="0",
            group="2",
            contype="0",
            conaffinity="0",
        )
        ET.SubElement(
            light,
            "geom",
            name="light_emitter",
            type="mesh",
            mesh="ring_diffuser",
            pos=".025 .05 -.069",
            rgba="1 .95 .83 1",
            mass="0",
            group="2",
            contype="0",
            conaffinity="0",
        )
        for i in range(24):
            a = 2 * math.pi * i / 24
            geom(
                light,
                f"light_ring_collision_{i}",
                "box",
                (0.025 + 0.136 * math.cos(a), 0.05 + 0.136 * math.sin(a), -0.06),
                (0.015, 0.018, 0.010),
                group="3",
                euler=f"0 0 {a}",
            )
        mass = 0.30
        inertia = ".003 .003 .0056"
    elif light_type == "panel":
        geom(light, "panel_wrist_bracket", "box", (0.025, 0.05, -0.040), (0.018, 0.02, 0.019))
        geom(light, "light_payload", "box", center, (0.10, 0.075, 0.014))
        geom(light, "light_emitter", "box", (0.025, 0.05, -0.075), (0.093, 0.068, 0.002), "1 .95 .83 1")
        mass = 0.22
        inertia = ".00045 .00077 .00115"
    else:
        geom(light, "tube_wrist_clamp", "box", (0.025, 0.05, -0.039), (0.024, 0.020, 0.018))
        geom(light, "light_payload", "cylinder", center, (0.019, 0.15), quat=".70710678 .70710678 0 0")
        geom(light, "light_emitter", "box", (0.025, 0.05, -0.078), (0.013, 0.14, 0.003), "1 .95 .83 1")
        for y in [-0.104, 0.204]:
            geom(
                light,
                f"tube_cap_{y}",
                "cylinder",
                (0.025, y, -0.06),
                (0.022, 0.005),
                quat=".70710678 .70710678 0 0",
            )
        mass = 0.18
        inertia = ".00137 .00005 .00137"
    ET.SubElement(light, "inertial", pos=".025 .05 -.06", mass=str(mass), diaginertia=inertia)
    destination = DESTINATION if light_type == "ring" else ROOT / f"rig_{light_type}.xml"
    ET.indent(tree)
    tree.write(destination, encoding="unicode")
    return destination


if __name__ == "__main__":
    for variant in LIGHT_TYPES:
        print(build(variant))
