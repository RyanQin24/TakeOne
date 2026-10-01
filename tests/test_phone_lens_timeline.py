"""A phone take films the reviewed lens timeline, or it films no timeline at all.

The Record page could start the handset recording and produce a completely
static frame where a Dolly Zoom was planned. The clip was real; the lens was
never commanded. `PhoneRecorder._plan` built `{plan_id, duration_s: 0}` and
nothing else, so `lens_schedule` returned an empty schedule and `PhoneTake` left
the lens wherever the operator had it for the whole take.

These pin the two halves of the fix: a take that names a reviewed shot carries
that shot's cues to the device, and a behavior-driven take — which genuinely has
no authored timeline — still carries none rather than fabricated ones.
"""

import unittest

from takeone.phone.capture import lens_schedule
from takeone.recording.api import shot_reference
from takeone.recording.phone import PhoneRecorder

PLAN_ID = "d" * 64
CALIBRATION = {
    "calibration": [
        {"focal_mm": 24.0, "normalised": 0.0},
        {"focal_mm": 50.0, "normalised": 0.0774},
    ]
}


def dolly_zoom_cues():
    return [
        {"time_s": 0.0, "focal_mm": 50.0},
        {"time_s": 1.5, "focal_mm": 36.0},
        {"time_s": 3.0, "focal_mm": 24.0},
    ]


class ShotReferenceTests(unittest.TestCase):
    def test_a_reviewed_shot_is_accepted_and_normalised(self):
        shot = shot_reference(
            {"plan_id": PLAN_ID, "duration_s": 3.0, "camera_cues": dolly_zoom_cues(), "label": "Dolly Zoom"}
        )
        self.assertEqual(shot["plan_id"], PLAN_ID)
        self.assertEqual(len(shot["camera_cues"]), 3)
        self.assertEqual(shot["camera_cues"][0]["focal_mm"], 50.0)

    def test_a_cue_outside_the_clock_or_the_lens_is_refused_at_the_boundary(self):
        for cues in (
            [{"time_s": 0.0, "focal_mm": 50.0}, {"time_s": 9.0, "focal_mm": 24.0}],
            [{"time_s": 0.0, "focal_mm": 5.0}, {"time_s": 3.0, "focal_mm": 24.0}],
        ):
            with self.assertRaises(ValueError):
                shot_reference({"plan_id": PLAN_ID, "duration_s": 3.0, "camera_cues": cues})

    def test_one_cue_is_not_a_timeline(self):
        with self.assertRaises(ValueError):
            shot_reference(
                {"plan_id": PLAN_ID, "duration_s": 3.0, "camera_cues": [{"time_s": 0.0, "focal_mm": 24.0}]}
            )

    def test_an_unknown_field_is_refused_rather_than_carried_into_the_take(self):
        with self.assertRaises(ValueError):
            shot_reference(
                {
                    "plan_id": PLAN_ID,
                    "duration_s": 3.0,
                    "camera_cues": dolly_zoom_cues(),
                    "zoom_factor": 2,
                }
            )


class PhonePlanTests(unittest.TestCase):
    def setUp(self):
        self.recorder = PhoneRecorder(service=None)

    def test_a_reviewed_shot_reaches_the_device_as_a_lens_schedule(self):
        shot = shot_reference({"plan_id": PLAN_ID, "duration_s": 3.0, "camera_cues": dolly_zoom_cues()})
        plan = self.recorder._plan("take-1", {"shot": shot})
        self.assertEqual(plan["plan_id"], PLAN_ID)
        self.assertEqual(plan["duration_s"], 3.0)
        times, targets = lens_schedule(CALIBRATION, plan)
        self.assertEqual(times, [0.0, 1.5, 3.0])
        # A real ramp: the schedule has to move, or the lens never does.
        self.assertGreater(targets[0], targets[-1])
        self.assertEqual(len(set(targets)), 3)

    def test_a_behaviour_take_still_carries_no_fabricated_cues(self):
        plan = self.recorder._plan("take-2", {"scope": {"plan_id": PLAN_ID}})
        self.assertNotIn("camera_cues", plan)
        self.assertEqual(lens_schedule(CALIBRATION, plan), ([], []))

    def test_the_plan_id_is_taken_from_the_shot_when_the_scope_has_none(self):
        shot = shot_reference({"plan_id": PLAN_ID, "duration_s": 3.0, "camera_cues": dolly_zoom_cues()})
        self.assertEqual(self.recorder._plan("take-3", {"shot": shot})["plan_id"], PLAN_ID)

    def test_a_shot_asking_for_an_unmeasured_focal_length_is_refused_not_clamped(self):
        """The old silence was worse than this refusal: the lens would simply
        sit still. Nothing may quietly pick a normalised value for 70 mm on a
        phone that was only ever measured to 50 mm."""
        shot = shot_reference(
            {
                "plan_id": PLAN_ID,
                "duration_s": 2.0,
                "camera_cues": [{"time_s": 0.0, "focal_mm": 70.0}, {"time_s": 2.0, "focal_mm": 24.0}],
            }
        )
        plan = self.recorder._plan("take-4", {"shot": shot})
        with self.assertRaises(ValueError) as caught:
            lens_schedule(CALIBRATION, plan)
        self.assertIn("outside measured phone range", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
