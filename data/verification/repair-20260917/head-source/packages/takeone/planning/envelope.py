"""Conservative geometry screens over the existing FK; all dimensions remain nominal.

Signed distances are bounded between samples using an upper speed bound for each
rigid geometry. Same welded assembly and directly adjacent joint assemblies are
excluded as intentional attachment/contact pairs, and listed in the report.
"""

import math

import mujoco
import numpy as np

from takeone.simulation import drive


class EnvelopeScreen:
    def __init__(self, model, curve, trace, scene, settings):
        self.model, self.scene, self.settings = model, scene, settings
        self.times = []
        self.minimum = float("inf")
        self.worst_pair = None
        self.support_margin = float("inf")
        self.gravity = np.zeros(10)
        self.geom_ids = [
            g for g in range(model.ngeom) if model.geom_bodyid[g] != 0 and model.geom_group[g] != 2
        ]
        low, high = curve.extrema(1)
        speeds = np.maximum(abs(np.array(low)), abs(np.array(high)))
        wheel_bound = np.max(abs(np.array([r["target"] for r in trace["records"]])), axis=0)
        linear = sum(wheel_bound) / 2
        yaw = (
            0.0
            if all(r["target"][0] == r["target"][1] for r in trace["records"])
            else sum(wheel_bound) / settings["trackWidth"]
        )
        self.velocity = []
        for g in self.geom_ids:
            body = int(model.geom_bodyid[g])
            lever = float(np.linalg.norm(model.geom_pos[g]) + model.geom_rbound[g])
            v = linear
            while body != 0:
                for j in range(model.njnt):
                    if model.jnt_bodyid[j] == body and model.jnt_qposadr[j] >= 3:
                        v += speeds[model.jnt_qposadr[j] - 3] * (lever + np.linalg.norm(model.jnt_pos[j]))
                lever += np.linalg.norm(model.body_pos[body])
                body = int(model.body_parentid[body])
            self.velocity.append(float(v + yaw * (lever + abs(drive.AXLE_OFFSET))))
        self.velocity = np.array(self.velocity)
        self.radii = model.geom_rbound[self.geom_ids]
        self.pairs = []
        excluded = set()
        for a, ga in enumerate(self.geom_ids):
            wa = int(model.body_weldid[model.geom_bodyid[ga]])
            for b in range(a + 1, len(self.geom_ids)):
                gb = self.geom_ids[b]
                wb = int(model.body_weldid[model.geom_bodyid[gb]])
                if (
                    wa == wb
                    or model.body_weldid[model.body_parentid[wa]] == wb
                    or model.body_weldid[model.body_parentid[wb]] == wa
                ):
                    excluded.add(tuple(sorted((model.body(wa).name, model.body(wb).name))))
                else:
                    self.pairs.append((a, b))
        self.excluded = sorted(excluded)
        self.pairs = np.array(self.pairs, dtype=int)
        self.max_relative_speed = float(max(2 * max(self.velocity), 0.0))
        b = settings["trackWidth"] / 2
        rear = drive.CASTER_OFFSET - abs(drive.CASTER_TRAIL)
        c = drive.CASTER_TRACK / 2 - abs(drive.CASTER_TRAIL)
        self.support = np.array([(drive.AXLE_OFFSET, -b), (rear, -c), (rear, c), (drive.AXLE_OFFSET, b)])

    def observe(self, data, q, t):
        self.times.append(float(t))
        positions = data.geom_xpos[self.geom_ids]
        # Evaluate only pairs whose bounding spheres can improve the current
        # capped minimum. This pruning cannot hide a closer geometry pair.
        a, b = self.pairs[:, 0], self.pairs[:, 1]
        lower = np.linalg.norm(positions[a] - positions[b], axis=1) - self.radii[a] - self.radii[b]
        candidate = np.where(lower < min(self.minimum, 0.5))[0]
        for index in candidate:
            ga, gb = self.geom_ids[a[index]], self.geom_ids[b[index]]
            distance = mujoco.mj_geomDistance(self.model, data, ga, gb, 0.5, None)
            if distance < self.minimum:
                self.minimum = float(distance)
                self.worst_pair = [
                    self.model.geom(g).name or f"{self.model.body(self.model.geom_bodyid[g]).name}/geom-{g}"
                    for g in (ga, gb)
                ]
        if not math.isfinite(self.minimum):
            self.minimum = 0.5
        for box in self.scene["boxes"]:
            d = abs(positions - np.array(box["center_m"])) - np.array(box["size_m"]) / 2
            distances = (
                np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(np.max(d, axis=1), 0) - self.radii
            )
            self._scene_min(distances, box["name"])
        actor = self.scene["actor"]
        radius = actor["radius_at_1_72m"] * self.settings["actorHeight"] / actor["height_reference_m"]
        # A vertical cylinder contains the rendered actor through its yaw turn.
        delta = positions - np.array(actor["origin_m"])
        radial = np.linalg.norm(delta[:, :2], axis=1) - radius
        height = (
            actor["height_envelope_at_1_72m"] * self.settings["actorHeight"] / actor["height_reference_m"]
        )
        vertical = abs(delta[:, 2] - height / 2) - height / 2
        d = np.c_[radial, vertical]
        distances = np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(np.max(d, axis=1), 0) - self.radii
        self._scene_min(distances, "actor_envelope")
        ground = np.array(
            [
                positions[i, 2] - self.radii[i]
                if self.model.body(self.model.geom_bodyid[g]).name.startswith(("cam_", "light_"))
                else float("inf")
                for i, g in enumerate(self.geom_ids)
            ]
        )
        self._scene_min(ground, "ground_for_arms_payloads")
        com = data.subtree_com[self.model.body("cart").id][:2] - np.array(q[:2])
        c, s = math.cos(q[2]), math.sin(q[2])
        com = np.array([c * com[0] + s * com[1], -s * com[0] + c * com[1]])
        for p0, p1 in zip(self.support, np.roll(self.support, -1, axis=0)):
            edge = p1 - p0
            relative = com - p0
            margin = (edge[0] * relative[1] - edge[1] * relative[0]) / np.linalg.norm(edge)
            self.support_margin = min(self.support_margin, float(margin))
        # pose_frame set qvel=0; qfrc_bias is gravity in this stationary evaluation.
        self.gravity = np.maximum(self.gravity, abs(data.qfrc_bias[3:]))

    def _scene_min(self, distances, name):
        index = int(np.argmin(distances))
        if distances[index] < self.minimum:
            self.minimum = float(distances[index])
            self.worst_pair = [self.model.geom(self.geom_ids[index]).name, name]

    def report(self):
        times = sorted(set(self.times))
        gap = max(b - a for a, b in zip(times, times[1:]))
        bound = self.minimum - self.max_relative_speed * gap / 2
        return dict(
            sampled_clearance_lower_bound_m=self.minimum,
            swept_clearance_lower_bound_m=bound,
            maximum_sampling_gap_s=gap,
            relative_geometry_speed_bound_m_s=self.max_relative_speed,
            worst_pair=self.worst_pair,
            conditional_clearance_proven=bound > 0.015,
            excluded_attachment_pairs=self.excluded,
            assumed_static_support_margin_m=self.support_margin,
            assumed_peak_gravity_torque_nm=self.gravity.tolist(),
            physical_qualification=False,
            scope="Conservative nominal geometry including cart, nonadjacent arms/payloads and shared scene. Actor/set use bounding volumes. Static support only; measured masses, dynamic tipping, contact/slip and cable envelopes require separate evidence.",
        )
