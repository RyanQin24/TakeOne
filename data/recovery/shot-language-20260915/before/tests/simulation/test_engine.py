import hashlib
import unittest

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from takeone.config import rig_config
from takeone.planning.compiler import compile_shot
from takeone.planning.kinematics import AIM_LIMIT_RAD
from takeone.planning.settings import LEGACY_SETTINGS, parameters
from takeone.planning.targets import ArmRole, ease, tracking_programs
from takeone.simulation import drive
from takeone.simulation.model import SOURCE
from takeone.simulation.robot import MODEL, model_path, visual_model


class CompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shot = compile_shot()
        cls.m = mujoco.MjModel.from_xml_path(str(MODEL))
        cls.d = mujoco.MjData(cls.m)

    def test_actual_model_and_camera_pose(self):
        self.assertEqual(self.m.nu, 10)
        self.assertEqual(self.m.nq, 13)
        self.assertTrue(self.shot["previewAvailable"])
        self.assertFalse(self.shot["hardwareReady"])
        self.assertTrue(self.shot["drive"]["reproducesRequestedPath"])
        for i in [0, 40, 160, 250, 320]:
            f = self.shot["frames"][i]
            self.d.qpos[:] = f["q"]
            mujoco.mj_forward(self.m, self.d)
            s = self.m.site("cam_optical").id
            np.testing.assert_allclose(f["camera"]["pos"], self.d.site_xpos[s], atol=1e-12)
            r = Rotation.from_quat(f["camera"]["quat"]).as_matrix()
            np.testing.assert_allclose(r, self.d.site_xmat[s].reshape(3, 3), atol=1e-12)
            # Image +y points down. A mirrored/upside-down view would fail this.
            self.assertLess(r[2, 1], -0.4)
            phase = f["time_s"] / self.shot["settings"]["duration"]
            yaw = (
                np.pi
                - np.deg2rad(self.shot["settings"]["orbit"]) / 2
                + np.deg2rad(self.shot["settings"]["turn"]) * ease(phase)
            )
            target = np.array(
                [0.085 * np.cos(yaw), 0.085 * np.sin(yaw), self.shot["settings"]["actorHeight"] - 0.12]
            )
            local = r.T @ (target - self.d.site_xpos[s])
            self.assertGreater(local[2], 0)
            self.assertLess(np.linalg.norm(local[:2] / local[2]), np.tan(AIM_LIMIT_RAD))

    def test_cart_pose_is_powered_axle_odometry_not_requested_arc(self):
        for frame in self.shot["frames"]:
            q = np.array(frame["q"])
            axle = np.array(frame["drive"]["axle"])
            np.testing.assert_allclose(
                q[:2] + drive.AXLE_OFFSET * np.array([np.cos(q[2]), np.sin(q[2])]),
                axle[:2],
                atol=1e-12,
            )
        self.assertLess(self.shot["drive"]["maxPathError"], 1e-10)
        self.assertEqual(self.shot["motorCommands"][-1]["wire"], "0.00,0.00\n")

    def test_infeasible_requests_are_flagged(self):
        high = compile_shot({"cameraHeight": 1.8})
        self.assertTrue(high["requiresRevision"])
        self.assertFalse(next(x for x in high["checks"] if x["name"] == "Camera height request")["passed"])
        fast = compile_shot({**LEGACY_SETTINGS, "orbit": 70, "duration": 8, "radius": 2.5})
        self.assertFalse(fast["playable"])
        self.assertFalse(next(x for x in fast["checks"] if x["name"] == "Cart speed")["passed"])

    def test_mesh_export_uses_compiled_mujoco_coordinates(self):
        model = visual_model()
        self.assertEqual(len(model["jointNames"]), 10)
        self.assertGreater(len(model["meshes"]), 5)
        for geom in model["geoms"]:
            g = geom["id"]
            np.testing.assert_allclose(geom["pos"], self.m.geom_pos[g])
            if geom["kind"] == 7:
                mid = geom["mesh"]
                addr = self.m.mesh_vertadr[mid]
                n = self.m.mesh_vertnum[mid]
                np.testing.assert_allclose(
                    np.array(model["meshes"][str(mid)]["vertices"]).reshape(-1, 3),
                    self.m.mesh_vert[addr : addr + n],
                )

    def test_input_validation(self):
        for invalid in [{"radius": float("nan")}, {"duration": 0}, {"turn": True}, {"surprise": 1}, []]:
            with self.assertRaises(ValueError):
                parameters(invalid)

    def test_confirmed_mount_height_and_original_arm_geometry(self):
        original = mujoco.MjModel.from_xml_path(str(SOURCE))
        # Verified against rig_5dof.xml in the user's original TakeOne-main.zip.
        self.assertEqual(
            hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "b05ec9116f62a866f3b3c914dcc925ed479dd9c2edbfaeef28218748d57f2d75",
        )
        for prefix in ["cam", "light"]:
            self.assertAlmostEqual(self.m.body_pos[self.m.body(prefix + "_base").id, 2], 1.23)
        deck = self.m.geom("cart_deck").id
        self.assertAlmostEqual(self.m.geom_pos[deck, 2] + self.m.geom_size[deck, 2], 1.23)
        for i in range(original.nbody):
            name = original.body(i).name
            if not name.startswith(("cam_", "light_")):
                continue
            j = self.m.body(name).id
            if name.endswith("_base"):
                yaw = np.deg2rad(rig_config()["upper"]["arm_mount_yaw_deg"]) / 2
                np.testing.assert_allclose(self.m.body_quat[j], [np.cos(yaw), 0, 0, np.sin(yaw)])
            else:
                np.testing.assert_allclose(self.m.body_quat[j], original.body_quat[i])
            if name != "light_tool_carrier":
                np.testing.assert_allclose(self.m.body_inertia[j], original.body_inertia[i])
            if not name.endswith("_base"):
                np.testing.assert_allclose(self.m.body_pos[j], original.body_pos[i])
        np.testing.assert_allclose(self.m.jnt_range, original.jnt_range)

    def test_raised_pose_uses_measured_mount_height_without_scaling(self):
        self.d.qpos[:] = 0
        self.d.qpos[3:8] = [0.2452579295, -0.2438059663, -1.2884520013, -0.4709976955, 2.0832087658]
        mujoco.mj_forward(self.m, self.d)
        height = self.d.site_xpos[self.m.site("cam_optical").id, 2]
        self.assertAlmostEqual(height, 1.7309801522, places=6)
        self.assertLess(height, 1.23 + 0.535004)
        # Reach witness only: this posture does not certify optical aim or clearance.

    def test_measured_physical_envelope_is_reported_separately_from_fk(self):
        model = visual_model()
        self.assertEqual(model["dimensions"]["mountHeight"], 1.23)
        self.assertEqual(model["dimensions"]["measuredMaximumExtendedHeight"], 1.8)
        self.assertEqual(model["dimensions"]["measuredHorizontalExtension"], 0.34)

    def test_default_height_and_load_warning_are_honest(self):
        self.assertAlmostEqual(self.shot["settings"]["cameraHeight"], 1.5)
        for frame in self.shot["frames"]:
            phase = frame["time_s"] / self.shot["settings"]["duration"]
            expected = (
                1.5
                + tracking_programs(self.shot["settings"], self.shot["drive"]["commandSign"])[
                    ArmRole.PHONE
                ].offset(phase)[2]
            )
            self.assertLess(abs(frame["camera"]["pos"][2] - expected), 0.02)
        self.assertFalse(
            next(c["passed"] for c in self.shot["checks"] if c["name"] == "Assumed payload margin")
        )
        self.assertFalse(self.shot["hardwareReady"])

    def test_photo_cart_and_front_rear_mounts(self):
        self.assertGreater(self.m.body("cam_base").pos[1], self.m.body("light_base").pos[1])
        self.assertAlmostEqual(self.m.body("cam_base").pos[1] - self.m.body("light_base").pos[1], 0.46)
        for name in [
            "upright_front",
            "upright_rear",
            "cart_work_deck",
            "laptop_screen",
            "electronics_box",
            "phone_clamp",
        ]:
            self.assertGreaterEqual(self.m.geom(name).id, 0)

    def test_all_lights_use_matching_models_and_stay_behind_lens(self):
        for variant in ["ring", "panel", "tube"]:
            with self.subTest(variant=variant):
                model = visual_model(variant)
                shot = compile_shot(
                    {
                        **LEGACY_SETTINGS,
                        "lightType": variant,
                        "radius": 1.45,
                        "duration": 5.153477,
                        "driveProfile": "constant",
                    }
                )
                m = mujoco.MjModel.from_xml_path(str(model_path(variant)))
                d = mujoco.MjData(m)
                self.assertEqual(model["modelHash"], shot["modelHash"])
                self.assertTrue(shot["previewAvailable"])
                self.assertTrue(
                    next(c["passed"] for c in shot["checks"] if c["name"] == "Light behind camera")
                )
                # Independently check every rendered light-arm mesh vertex/primitive
                # corner in five poses, not just the emitter's center.
                light_ids = [g for g in model["geoms"] if model["bodyNames"][g["body"]].startswith("light_")]
                for frame in shot["frames"][::80]:
                    d.qpos[:] = frame["q"]
                    mujoco.mj_forward(m, d)
                    forward = Rotation.from_quat(frame["camera"]["quat"]).as_matrix()[:, 2]
                    camera = np.array(frame["camera"]["pos"])
                    for g in light_ids:
                        if g["kind"] == 7:
                            vertices = np.array(model["meshes"][str(g["mesh"])]["vertices"]).reshape(-1, 3)
                        else:
                            from itertools import product

                            extent = np.array(g["size"])
                            if g["kind"] == 5:
                                extent = np.array([g["size"][0], g["size"][0], g["size"][1]])
                            vertices = np.array(list(product([-1, 1], repeat=3))) * extent
                        world = vertices @ d.geom_xmat[g["id"]].reshape(3, 3).T + d.geom_xpos[g["id"]]
                        self.assertLess(np.max((world - camera) @ forward), -0.025)
        for invalid in ["spot", None, 42, []]:
            with self.assertRaises(ValueError):
                parameters({"lightType": invalid})

    def test_arm_led_tracking_transfers_motion_off_the_base(self):
        old = compile_shot(
            {**LEGACY_SETTINGS, "radius": 1.45, "duration": 5.153477, "driveProfile": "constant"}
        )
        motion = self.shot["movement"]
        self.assertLess(abs(motion["baseTurnDegrees"]), abs(old["movement"]["baseTurnDegrees"]))
        self.assertGreater(abs(old["movement"]["baseTurnDegrees"]), 34)
        self.assertGreater(motion["cameraJointRangesDegrees"][0], 40)
        self.assertGreater(motion["lightJointRangesDegrees"][0], 30)
        self.assertGreater(motion["cameraJointRangesDegrees"][2], 20)
        self.assertGreater(
            motion["cameraJointRangesDegrees"][0], old["movement"]["cameraJointRangesDegrees"][0] * 5
        )
        for name in [
            "Aim at actor",
            "Joint limits",
            "Arm speed",
            "Arm acceleration",
            "Arm jerk",
            "Light behind camera",
            "Sampled arm clearance",
        ]:
            self.assertTrue(next(c["passed"] for c in self.shot["checks"] if c["name"] == name), name)
        from takeone.protocol import COMMAND_CAP, MIN_COMMAND, uart_pair

        # Coordinated planning may adjust the base while the arms supply most
        # of the pan. Validate the emitted packets and resulting path instead
        # of requiring the obsolete, constant minimum-speed reference packet.
        response = drive.CartResponse.load(self.shot["settings"]["minimumSpeed"])
        axle = np.array(self.shot["frames"][0]["drive"]["axle"])
        elapsed = 0.0
        for command in self.shot["motorCommands"][:-1]:
            values = np.array([float(value) for value in command["wire"].strip().split(",")])
            self.assertTrue(np.all(values >= MIN_COMMAND))
            self.assertTrue(np.all(values <= COMMAND_CAP))
            self.assertEqual(command["wire"], uart_pair(*command["commands"]))
            speeds = np.array(response.speeds_for(values))
            np.testing.assert_allclose(speeds, command["targetWheelSpeeds"], atol=1e-12)
            self.assertAlmostEqual(command["time"], elapsed)
            axle = drive.integrate(axle, *(speeds * command["duration"]), self.shot["settings"]["trackWidth"])
            elapsed += command["duration"]
        self.assertAlmostEqual(elapsed, self.shot["settings"]["duration"])
        np.testing.assert_allclose(axle, self.shot["frames"][-1]["drive"]["axle"], atol=1e-10)

    def test_arm_motion_controls_reject_out_of_range_requests(self):
        for invalid in [{"armTravel": -0.1}, {"armLift": 0.5}, {"armTravel": True}]:
            with self.assertRaises(ValueError):
                parameters(invalid)

    def test_reverse_direction_mirrors_cart_relative_arm_sweep(self):
        forward = tracking_programs(self.shot["settings"], 1)[ArmRole.PHONE]
        reverse = tracking_programs(self.shot["settings"], -1)[ArmRole.PHONE]
        for phase in (0.0, 0.25, 0.5, 0.75, 1.0):
            forward_offset = forward.offset(phase)
            reverse_offset = reverse.offset(phase)
            self.assertAlmostEqual(reverse_offset[0], -forward_offset[0])
            self.assertAlmostEqual(reverse_offset[2], forward_offset[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
