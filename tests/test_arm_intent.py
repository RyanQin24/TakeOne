"""Semantic, geometric and selected-person checks; no serial or network IO."""

import copy
import math
import unittest

import numpy as np
from scipy.spatial.transform import Rotation
from takeone.perception import PerceptionState, TrackedPerson
from takeone.planning.arm_adjustment import preview_adjustment, resolve_target
from takeone.planning.kinematics import ArmSolver, task_errors
from takeone.planning.targets import ToolTarget
from takeone.simulation.robot import load_model
from takeone.voice.arm_intent import ACTIONS, ROTATIONS, TRANSLATIONS, prepare_arm_intent
from takeone.voice.live_robot import LiveRobotTools
from takeone.voice.selected_aim import selected_person_aim


def operation(action, amount=None, frame="tool", target=None):
    return dict(action=action, amount=amount, frame=frame, target=target)


def request(*operations, role="phone"):
    return dict(role=role, operations=list(operations))


class IntentTests(unittest.TestCase):
    def test_arm_request_cancels_only_previous_cart_review(self):
        class PendingCart:
            def cancel_review(self, owner):
                self.cancelled = owner

        nudges = PendingCart()
        result = LiveRobotTools(nudges=nudges).execute(
            "prepare_arm_adjustment", request(operation("lower", 0.02, "world")), owner="browser"
        )
        self.assertTrue(result["ok"])
        self.assertEqual(nudges.cancelled, "browser")

    def test_compound_retains_every_clause_and_discloses_defaults(self):
        result = prepare_arm_intent(
            request(
                operation("lower", frame="world"),
                operation("tilt_unspecified"),
                operation("face_target", target="us"),
            )
        )
        self.assertEqual(
            [o["action"] for o in result["intent"]["operations"]],
            ["lower", "tilt_unspecified", "face_target"],
        )
        self.assertEqual(result["code"], "clarification_required")
        self.assertEqual(result["proposed_defaults"][0]["proposed_amount"], 0.02)
        self.assertEqual(result["target_labels"], ["us"])
        self.assertFalse(result["executable"])

    def test_all_declared_actions_validate_without_actuation(self):
        for role in ("phone", "light"):
            for action in ACTIONS:
                with self.subTest(role=role, action=action):
                    op = operation(action, target="selected person" if action == "face_target" else None)
                    result = LiveRobotTools().execute("prepare_arm_adjustment", request(op, role=role))
                    self.assertTrue(result["ok"], result)
                    self.assertFalse(result["hardware_commands_sent"])

    def test_ambiguous_role_frame_and_direction_require_clarification(self):
        result = prepare_arm_intent(request(operation("left", frame="unspecified"), role="unspecified"))
        self.assertEqual(len(result["questions"]), 2)
        self.assertTrue(prepare_arm_intent(request(operation("pan_left", frame="world")))["questions"])

    def test_rejects_bad_numbers_unknown_fields_and_unbounded_compounds(self):
        for value in (True, -1, 0, float("nan"), float("inf"), "2", 0.11):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepare_arm_intent(request(operation("lower", value, "world")))
        bad = request(operation("lower"))
        bad["operations"][0]["servo_count"] = 2000
        with self.assertRaises(ValueError):
            prepare_arm_intent(bad)
        with self.assertRaises(ValueError):
            prepare_arm_intent(request(*[operation("lower", 0.04, "world")] * 3))
        with self.assertRaises(ValueError):
            prepare_arm_intent(request(*[operation("pan_left", math.radians(15))] * 3))

    def test_input_is_not_mutated_and_no_cart_substitution(self):
        value = request(operation("lower", 0.02, "world"))
        original = copy.deepcopy(value)

        class RejectOwner:
            def request(self, *args, **kwargs):
                raise AssertionError("Arm interpretation must not contact a robot owner")

        result = LiveRobotTools(RejectOwner()).execute("prepare_arm_adjustment", value)
        self.assertTrue(result["ok"])
        self.assertEqual(value, original)


class GeometryTests(unittest.TestCase):
    # camera faces world +Y, right +X, down -Z
    rotation = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])

    def resolve(self, *ops, rotation=None, yaw=0, targets=None):
        return resolve_target(
            [0.0, 0.0, 1.0],
            self.rotation if rotation is None else rotation,
            yaw,
            prepare_arm_intent(request(*ops)),
            targets,
        )

    def test_world_lower_is_independent_of_camera_and_cart_orientation(self):
        for angle in np.linspace(-math.pi, math.pi, 13):
            r = Rotation.from_euler("z", angle).as_matrix() @ self.rotation
            t = self.resolve(operation("lower", 0.02, "world"), rotation=r, yaw=angle)
            np.testing.assert_allclose(t.position_m, [0, 0, 0.98])
            np.testing.assert_allclose(np.subtract(t.look_at_m, t.position_m), r[:, 2], atol=1e-12)

    def test_translation_opposites_and_rotation_opposites_cancel(self):
        for first, second in (
            ("raise", "lower"),
            ("left", "right"),
            ("forward", "backward"),
            ("pan_left", "pan_right"),
            ("tilt_up", "tilt_down"),
            ("roll_left", "roll_right"),
        ):
            t = self.resolve(operation(first), operation(second))
            np.testing.assert_allclose(t.position_m, [0, 0, 1], atol=1e-12)
            np.testing.assert_allclose(np.subtract(t.look_at_m, t.position_m), [0, 1, 0], atol=1e-12)
            np.testing.assert_allclose(t.right_axis, [1, 0, 0], atol=1e-12)

    def test_all_translation_axes_in_tool_and_rotated_chassis_frames(self):
        for frame, vectors in (
            ("tool", ([0, 0, 1], [0, 0, -1], [-1, 0, 0], [1, 0, 0], [0, 1, 0], [0, -1, 0])),
            ("chassis", ([0, 0, 1], [0, 0, -1], [1, 0, 0], [-1, 0, 0], [0, -1, 0], [0, 1, 0])),
        ):
            for action, vector in zip(TRANSLATIONS, vectors):
                t = self.resolve(operation(action, 0.02, frame), yaw=math.pi / 2)
                np.testing.assert_allclose(
                    np.subtract(t.position_m, [0, 0, 1]), np.array(vector) * 0.02, atol=1e-12
                )

    def test_rotation_signs_and_position_preservation(self):
        expected = {"pan_left": (0, -1), "pan_right": (0, 1), "tilt_up": (2, 1), "tilt_down": (2, -1)}
        for action in ROTATIONS:
            t = self.resolve(operation(action, math.radians(5)))
            np.testing.assert_allclose(t.position_m, [0, 0, 1])
            if action in expected:
                index, sign = expected[action]
                self.assertGreater(sign * np.subtract(t.look_at_m, t.position_m)[index], 0)
            else:
                np.testing.assert_allclose(np.subtract(t.look_at_m, t.position_m), [0, 1, 0])
                self.assertGreater(t.right_axis[2] * (1 if action == "roll_left" else -1), 0)

    def test_face_target_requires_position_and_never_guesses_depth(self):
        op = operation("face_target", target="us")
        with self.assertRaisesRegex(ValueError, "no locally supplied"):
            self.resolve(op)
        t = self.resolve(operation("lower", 0.02, "world"), op, targets={"us": [0, 2, 1]})
        expected = np.array([0, 2, 0.02])
        expected /= np.linalg.norm(expected)
        np.testing.assert_allclose(np.subtract(t.look_at_m, t.position_m), expected)
        for point in ([0, 0, 1], [0, -1, 1]):
            with self.assertRaises(ValueError):
                self.resolve(op, targets={"us": point})

    def test_explicit_roll_is_scored_against_requested_axis_not_horizon(self):
        target = self.resolve(operation("roll_right", math.radians(10)))
        rotated = Rotation.from_rotvec(np.array([0, 1, 0]) * math.radians(10)).as_matrix() @ self.rotation
        self.assertAlmostEqual(task_errors(np.array([0, 0, 1]), rotated, target)[2], 0)
        self.assertAlmostEqual(task_errors(np.array([0, 0, 1]), self.rotation, target)[2], math.radians(10))
        with self.assertRaises(ValueError):
            ToolTarget((0, 0, 0), (0, 1, 0), (0, 2, 0))

    def test_offline_ik_preserves_cart_and_other_arm_and_is_never_executable(self):
        solver = ArmSolver(load_model())
        q = np.r_[[0.0, 0.0, 0.0], (solver.lower[3:] + solver.upper[3:]) / 2]
        for role, unchanged in (("phone", slice(8, 13)), ("light", slice(3, 8))):
            result = preview_adjustment(request(operation("lower", 0.005, "world"), role=role), q)
            self.assertIn(result["code"], ("offline_endpoint_preview", "endpoint_infeasible"))
            np.testing.assert_allclose(result["candidate_model_qpos"][:3], q[:3])
            np.testing.assert_allclose(result["candidate_model_qpos"][unchanged], q[unchanged])
            self.assertFalse(result["executable"])
            self.assertFalse(result["trajectory_validated"])
            self.assertFalse(result["collision_checked"])


class SelectionTests(unittest.TestCase):
    def state(self, confidence=0.9, age=10, selected=("p1",), seen=1_000_000_000):
        return PerceptionState(
            1_000_000_000,
            age,
            (
                TrackedPerson("p1", (0.1, 0.2, 0.3, 0.8), confidence, (0, 0), seen),
                TrackedPerson("p2", (0.6, 0.2, 0.8, 0.8), 0.99, (0, 0), 1_000_000_000),
            ),
            selected,
        )

    def test_uses_only_selected_person_and_keeps_cart_stationary(self):
        result = selected_person_aim(self.state(), "p1", now_ns=1_010_000_000, source_role="phone")
        self.assertAlmostEqual(result["aim_error_uv"][0], -0.3)
        self.assertEqual(result["cart_action"], "hold")
        self.assertIsNone(result["depth_m"])
        self.assertFalse(result["executable"])

    def test_stale_missing_low_confidence_and_wrong_camera_rejected(self):
        for state, track, source in (
            (self.state(age=300), "p1", "phone"),
            (self.state(confidence=0.3), "p1", "phone"),
            (self.state(), "p2", "phone"),
            (self.state(seen=1), "p1", "phone"),
            (self.state(), "p1", "cart_webcam"),
        ):
            with self.assertRaises(ValueError):
                selected_person_aim(state, track, now_ns=1_010_000_000, source_role=source)


if __name__ == "__main__":
    unittest.main()
