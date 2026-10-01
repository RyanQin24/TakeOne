"""Reproducible independent audit of the current illustrative model (no hardware).

Run with the neighboring validation bundle's Python environment. Outputs JSON.
This deliberately reports limitations; a numeric agreement is not hardware validation.
"""
import json
import hashlib
import math
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation, Slerp
from takeone.simulation.robot import MODEL
from takeone.planning.compiler import compile_shot


def vector(element, key, default):
    return np.fromstring(element.get(key, default), sep=' ')


def transform(p, r):
    t = np.eye(4)
    t[:3, :3] = r
    t[:3, 3] = p
    return t


def quaternion(element):
    wxyz = vector(element, 'quat', '1 0 0 0')
    return Rotation.from_quat(np.roll(wxyz, -1)).as_matrix()


def independent_fk(q, joint_index, root):
    """Compose raw XML transforms, not MuJoCo forward-kinematics outputs."""
    bodies, sites = {}, {}

    def visit(body, parent):
        t = parent @ transform(vector(body, 'pos', '0 0 0'), quaternion(body))
        for joint in body.findall('joint'):
            axis = vector(joint, 'axis', '0 0 1')
            axis /= np.linalg.norm(axis)
            value = q[joint_index[joint.get('name')]]
            pivot = vector(joint, 'pos', '0 0 0')
            if joint.get('type', 'hinge') == 'slide':
                t = t @ transform(value * axis, np.eye(3))
            else:
                r = Rotation.from_rotvec(axis * value).as_matrix()
                t = t @ transform(pivot - r @ pivot, r)
        bodies[body.get('name')] = t
        for site in body.findall('site'):
            sites[site.get('name')] = t @ transform(vector(site, 'pos', '0 0 0'), quaternion(site))
        for child in body.findall('body'):
            visit(child, t)

    for body in root.find('worldbody').findall('body'):
        visit(body, np.eye(4))
    return bodies, sites


def reach_upper_bound(root, prefix):
    """Triangle inequality: a rigorous loose bound, not an achievable reach."""
    mount = root.find(f".//body[@name='{prefix}_base']")
    node = mount
    lengths = []
    while node.find('body') is not None:
        node = node.find('body')
        lengths.append(float(np.linalg.norm(vector(node, 'pos', '0 0 0'))))
    lengths.append(float(np.linalg.norm(vector(node.find("site"), 'pos', '0 0 0'))))
    return dict(segmentNorms_m=lengths, opticalDistanceUpperBound_m=sum(lengths))


def run():
    root = ET.parse(MODEL).getroot()
    model = mujoco.MjModel.from_xml_path(str(MODEL))
    data = mujoco.MjData(model)
    joint_index = {model.joint(i).name: model.jnt_qposadr[i] for i in range(model.njnt)}
    rng = np.random.default_rng(20260911)
    errors = dict(position_m=0., rotation_matrix=0., jacobian=0.)
    for _ in range(100):
        q = np.r_[rng.uniform(-2, 2, 3), rng.uniform(model.jnt_range[3:, 0], model.jnt_range[3:, 1])]
        bodies, sites = independent_fk(q, joint_index, root)
        data.qpos[:] = q
        mujoco.mj_forward(model, data)
        for name, t in sites.items():
            sid = model.site(name).id
            errors['position_m'] = max(errors['position_m'], float(np.max(abs(t[:3, 3] - data.site_xpos[sid]))))
            errors['rotation_matrix'] = max(errors['rotation_matrix'], float(np.max(abs(t[:3, :3] - data.site_xmat[sid].reshape(3, 3)))))
        for name in ['cam_optical', 'light_optical']:
            jp, jr = np.zeros((3, model.nv)), np.zeros((3, model.nv))
            mujoco.mj_jacSite(model, data, jp, jr, model.site(name).id)
            for k in range(model.nq):
                delta = np.zeros(model.nq); delta[k] = 1e-6
                plus = independent_fk(q + delta, joint_index, root)[1][name][:3, 3]
                minus = independent_fk(q - delta, joint_index, root)[1][name][:3, 3]
                errors['jacobian'] = max(errors['jacobian'], float(np.max(abs(jp[:, k] - (plus - minus) / 2e-6))))

    shot = compile_shot()
    q = np.array([f['q'] for f in shot['frames']])
    duration = shot['settings']['duration']
    # Reconstruct the exact compiler spline from the exported original knots.
    spline = CubicSpline(np.linspace(0, duration, 81), q[::4], bc_type=((1, np.zeros(13)), (1, np.zeros(13))))
    t = np.linspace(0, duration, 3201)
    positions, velocities, accelerations = spline(t), spline(t, 1), spline(t, 2)
    omega = velocities[:, 2]
    yaw = positions[:, 2]
    lateral_center = -np.sin(yaw) * velocities[:, 0] + np.cos(yaw) * velocities[:, 1]
    # XML wheels are centered at x=+/-0.16, not at the origin assumed by a rear-axle bicycle model.
    rear_lateral = lateral_center - .16 * omega
    nominal = dict(
        radiusError_m=float(np.max(abs(np.linalg.norm(positions[:, :2], axis=1) - shot['settings']['radius']))),
        maxCenterLateralSpeed_m_s=float(np.max(abs(lateral_center))),
        maxRearWheelLateralSpeed_m_s=float(np.max(abs(rear_lateral))),
        maxYawRate_rad_s=float(np.max(abs(omega))),
        maxCartSpeed_m_s=float(np.max(np.linalg.norm(velocities[:, :2], axis=1))),
        analyticMaxCartSpeed_m_s=shot['settings']['radius'] * math.radians(shot['settings']['orbit']) * 1.875 / duration,
        maxArmSpeed_rad_s=float(np.max(abs(velocities[:, 3:]))),
        maxArmAcceleration_rad_s2=float(np.max(abs(accelerations[:, 3:]))),
        maxArmJerk_rad_s3=float(np.max(abs(spline(t, 3)[:, 3:]))),
        maxAccelerationAtEndpoints_rad_s2=float(np.max(abs(spline([0, duration], 2)[:, 3:]))),
    )
    # Verify inverse dynamics against the documented equation including passive/contact forces.
    inverse_error = 0.
    max_contacts = 0
    interpolation_position_error = 0.
    interpolation_rotation_error = 0.
    for i in range(0, 320, 8):
        ti = (i + .5) * duration / 320
        data.qpos[:] = spline(ti)
        data.qvel[:] = spline(ti, 1)
        data.qacc[:] = spline(ti, 2)
        mujoco.mj_inverse(model, data)
        matrix = np.empty((model.nv, model.nv))
        mujoco.mj_fullM(model, data, matrix)
        expected = matrix @ data.qacc + data.qfrc_bias - data.qfrc_passive - data.qfrc_constraint
        inverse_error = max(inverse_error, float(np.max(abs(expected - data.qfrc_inverse))))
        max_contacts = max(max_contacts, data.ncon)
        # Browser interpolates separate rigid body poses; compare against FK of interpolated joints.
        data.qpos[:] = .5 * (q[i] + q[i + 1])
        mujoco.mj_forward(model, data)
        aa, bb = shot['frames'][i]['bodies'], shot['frames'][i + 1]['bodies']
        for bid in range(1, model.nbody):
            p = .5 * (np.array(aa[bid][:3]) + np.array(bb[bid][:3]))
            r = Slerp([0, 1], Rotation.from_quat([aa[bid][3:], bb[bid][3:]]))([.5]).as_matrix()[0]
            interpolation_position_error = max(interpolation_position_error, float(np.linalg.norm(p - data.xpos[bid])))
            delta = r.T @ data.xmat[bid].reshape(3, 3)
            interpolation_rotation_error = max(interpolation_rotation_error, float(np.linalg.norm(Rotation.from_matrix(delta).as_rotvec())))

    cart = root.find(".//geom[@name='cart_box']")
    assert errors['position_m'] < 1e-12, errors
    assert errors['rotation_matrix'] < 1e-12, errors
    assert errors['jacobian'] < 1e-7, errors
    assert inverse_error < 1e-9, inverse_error
    assert abs(nominal['maxCartSpeed_m_s']-nominal['analyticMaxCartSpeed_m_s']) < 1e-6
    result = dict(
        planId=shot['planId'], modelSHA256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        seed=20260911, randomConfigurations=100, independentFKAndJacobianMaxErrors=errors,
        currentGeometry=dict(cartBodySize_m=(2*vector(cart, 'size', '0 0 0')).tolist(),
                             cartBodyTop_m=float(vector(cart, 'pos', '0 0 0')[2]+vector(cart, 'size', '0 0 0')[2]),
                             armMountHeight_m=float(model.body_pos[model.body('cam_base').id, 2]),
                             upperDeckTop_m=float(model.geom_pos[model.geom('cart_deck').id,2]+model.geom_size[model.geom('cart_deck').id,2]),
                             totalModelMass_kg=float(sum(model.body_mass)),
                             cameraReach=reach_upper_bound(root, 'cam')),
        nominalMotion=nominal,
        inverseDynamicsEquationMaxError=inverse_error, maxContactsInCheckedNominalFrames=int(max_contacts),
        browserMidpointInterpolation=dict(maxPositionError_m=interpolation_position_error, maxRotationError_rad=interpolation_rotation_error),
        declaredScreens=shot['checks'], hardwareReady=False,
    )
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
