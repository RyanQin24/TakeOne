"""MuJoCo model loading and render serialization, independent of application code."""

import hashlib

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from takeone.config import rig_config
from takeone.paths import MODELS
from takeone.simulation import drive
from takeone.simulation.model import LIGHT_TYPES

MODEL = MODELS / "rig_tall.xml"


def model_hash(path, track_width):
    return hashlib.sha256(path.read_bytes() + f"|track={track_width:.9f}".encode()).hexdigest()


def load_model(light_type="ring", track_width=None):
    if track_width is None:
        track_width = rig_config()["cart"]["track_width_m"]
    m = mujoco.MjModel.from_xml_path(str(model_path(light_type)))
    for side, sign in [("left", -1), ("right", 1)]:
        m.body_pos[m.body("drive_" + side).id, 0] = sign * drive.FORWARD_SIGN * track_width / 2
    return m


def model_path(light_type="ring"):
    if light_type not in LIGHT_TYPES:
        raise ValueError("Unknown light type")
    return MODEL if light_type == "ring" else MODELS / f"rig_{light_type}.xml"


def matrix_quat(mat):
    return Rotation.from_matrix(np.asarray(mat).reshape(3, 3)).as_quat().tolist()


def pose_frame(model, data, q, time_s, drive_frame):
    """One FK/serialization boundary: right-handed Z-up, world poses, xyzw quaternions."""
    data.qpos[:] = q
    data.qvel[:] = 0
    mujoco.mj_forward(model, data)
    tools = {}
    for name, prefix in (("camera", "cam"), ("light", "light")):
        site = model.site(prefix + "_optical").id
        tools[name] = dict(pos=data.site_xpos[site].tolist(), quat=matrix_quat(data.site_xmat[site]))
    return dict(
        time_s=float(time_s),
        q=list(q),
        drive=drive_frame,
        bodies=np.c_[data.xpos, data.xquat[:, 1:], data.xquat[:, 0]].tolist(),
        **tools,
    )


def visual_model(light_type="ring", track_width=None):
    """Export MuJoCo's compiled mesh vertices and geom offsets, including mesh recentering."""
    if track_width is None:
        track_width = rig_config()["cart"]["track_width_m"]
    path = model_path(light_type)
    m = load_model(light_type, track_width)
    meshes = {}
    geoms = []
    for g in range(m.ngeom):
        if m.geom_bodyid[g] == 0 or m.geom_group[g] == 3:
            continue
        mid = int(m.geom_dataid[g])
        if int(m.geom_type[g]) == int(mujoco.mjtGeom.mjGEOM_MESH) and str(mid) not in meshes:
            va, vn = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
            fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
            meshes[str(mid)] = {
                "vertices": m.mesh_vert[va : va + vn].ravel().tolist(),
                "faces": m.mesh_face[fa : fa + fn].ravel().tolist(),
            }
        material = m.geom_matid[g]
        rgba = m.mat_rgba[material] if material >= 0 else m.geom_rgba[g]
        geoms.append(
            dict(
                id=g,
                body=int(m.geom_bodyid[g]),
                name=m.geom(g).name or f"geom_{g}",
                kind=int(m.geom_type[g]),
                mesh=mid,
                size=m.geom_size[g].tolist(),
                pos=m.geom_pos[g].tolist(),
                quat=np.roll(m.geom_quat[g], -1).tolist(),
                color=rgba.tolist(),
            )
        )
    upper = rig_config()["upper"]
    return dict(
        geoms=geoms,
        meshes=meshes,
        bodyNames=[m.body(i).name for i in range(m.nbody)],
        jointNames=[m.joint(i).name for i in range(3, m.njnt)],
        jointLimits=m.jnt_range[3:].tolist(),
        lightType=light_type,
        lightTypes=list(LIGHT_TYPES),
        layout=dict(
            frontAxis="+Y filming side toward subject",
            travelAxis="-X toward powered front wheels",
            poweredWheelEnd="front",
            casterEnd="rear",
            casterType="passive swivel with estimated trail",
            lowerRotationDegrees=upper["lower_rotation_deg"],
            armMountYawDegrees=upper["arm_mount_yaw_deg"],
            phoneMount=upper["phone_mount_m"],
            lightMount=upper["light_mount_m"],
        ),
        drive=dict(
            wheelRadius=drive.WHEEL_RADIUS,
            wheelWidth=drive.WHEEL_WIDTH,
            trackWidth=track_width,
            axleOffset=drive.AXLE_OFFSET,
            casterOffset=drive.CASTER_OFFSET,
            forwardSign=drive.FORWARD_SIGN,
        ),
        dimensions=dict(
            mountHeight=upper["mount_height_m"],
            cartHeight=upper["mount_height_m"],
            workDeckHeight=0.498,
            cartWidth=track_width + 0.06,
            cartLength=0.824,
            measuredMaximumExtendedHeight=upper["maximum_extended_height_m"],
            measuredHorizontalExtension=upper["horizontal_extension_m"],
            approximateOverallHeight=upper["maximum_extended_height_m"],
            armReachUpperBound=0.5350039834991899,
            cameraHeightMin=0.6,
            cameraHeightMax=1.8,
            confirmed=[
                "cartHeight",
                "mountHeight",
                "measuredMaximumExtendedHeight",
                "measuredHorizontalExtension",
                "wheelDiameter",
                "wheelWidth",
            ],
            physicsValidated=False,
        ),
        modelHash=model_hash(path, track_width),
        source="Photo-based cart with complete SO-101 chains yawed at their declared mount origins. Wheel ends swapped: 19 cm diameter / 6 cm powered front tires, passive rear swivel casters. Cart forward is -X; filming side is +Y. Caster dimensions, track and masses estimated.",
    )
