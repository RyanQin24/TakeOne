"""Which camera judged the framing, and whether it was the taking lens.

Tracking ran on a witness webcam, so every take carried an unmeasured offset
between the camera that said "settled" and the camera recording the film. The
phone's own image can reach this computer as a video device — its USB-C/HDMI
feed through a capture card, or Continuity Camera — and when it does there is
one lens and no offset to measure.

That claim removes a standing caveat from every take, so it is the operator's
to make explicitly, it is stored as operator-reported, and it never upgrades
into a claim that TakeOne has read the recorded clip.
"""

import json
import tempfile
import unittest
from pathlib import Path

from takeone.embodied.contracts import FilmingGoal
from takeone.embodied.recorder import BehaviorRecordingAdapter
from takeone.perception.source import PerceptionSource, aim_facts, defaults


def goal():
    return FilmingGoal(
        subject_track_ids=("person-0001",),
        subject_relation="one_person",
        camera_relation="hold",
        framing="medium",
        screen_target_uv=(0.5, 0.5),
        desired_subject_size_range=(0.2, 0.7),
        recording_policy="after_settle",
        max_duration_s=8,
        lost_target_policy="hold",
    )


class PerceptionSourceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "perception-source.json"
        self.source = PerceptionSource(self.path)

    def test_a_fresh_rig_tracks_on_a_witness_camera_with_an_unmeasured_offset(self):
        status = self.source.status()
        self.assertEqual(status["aim_reference"], "witness_camera")
        self.assertEqual(status["witness_to_lens_offset"], "unmeasured")
        self.assertFalse(status["optical_framing_verified"])

    def test_selecting_the_phone_feed_removes_the_offset_because_there_is_one_lens(self):
        status = self.source.update(
            {
                "kind": "phone_lens_feed",
                "feed": "usb_hdmi_capture",
                "device_id": "capture-1",
                "device_label": "USB Capture HDMI",
                "operator_confirmed": True,
            }
        )
        self.assertEqual(status["aim_reference"], "phone_lens_feed")
        self.assertEqual(status["witness_to_lens_offset"], "none_same_lens")
        self.assertEqual(status["aim_source_evidence"], "operator_reported")
        # Tracking the lens's frames is not reading the recorded clip.
        self.assertFalse(status["optical_framing_verified"])

    def test_the_phone_feed_cannot_be_claimed_without_the_operator_saying_so(self):
        with self.assertRaises(ValueError):
            self.source.update({"kind": "phone_lens_feed", "operator_confirmed": False})
        self.assertEqual(self.source.status()["aim_reference"], "witness_camera")

    def test_unknown_kinds_feeds_and_fields_are_refused(self):
        for change in (
            {"kind": "phone_camera"},
            {"feed": "airplay", "kind": "phone_lens_feed", "operator_confirmed": True},
            {"device_label": 7},
            {"operator_confirmed": "yes"},
        ):
            with self.assertRaises(ValueError):
                self.source.update(change)

    def test_galaxy_camera_cannot_be_claimed_as_the_iphone_feed(self):
        with self.assertRaisesRegex(ValueError, "Galaxy"):
            self.source.update(
                {
                    "kind": "phone_lens_feed",
                    "feed": "usb_hdmi_capture",
                    "device_label": "Ryan's S23 FE (Windows Virtual Camera)",
                    "operator_confirmed": True,
                }
            )

    def test_cart_camera_cannot_be_claimed_as_the_iphone_feed(self):
        with self.assertRaisesRegex(ValueError, "cart"):
            self.source.update(
                {
                    "kind": "phone_lens_feed",
                    "feed": "usb_hdmi_capture",
                    "device_label": "Live Streamer CAM 313",
                    "operator_confirmed": True,
                }
            )

    def test_going_back_to_a_witness_camera_restores_the_caveat(self):
        self.source.update(
            {"kind": "phone_lens_feed", "feed": "continuity_camera", "operator_confirmed": True}
        )
        status = self.source.update({"kind": "witness_camera", "operator_confirmed": False})
        self.assertEqual(status["witness_to_lens_offset"], "unmeasured")
        self.assertEqual(status["source"]["feed"], "other")

    def test_the_choice_survives_a_restart(self):
        self.source.update(
            {
                "kind": "phone_lens_feed",
                "feed": "usb_hdmi_capture",
                "device_id": "capture-1",
                "device_label": "USB Capture HDMI",
                "operator_confirmed": True,
            }
        )
        self.assertEqual(PerceptionSource(self.path).status()["aim_reference"], "phone_lens_feed")
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(set(stored), set(defaults()))

    def test_aim_facts_are_pure_and_take_no_position_on_unverified_things(self):
        facts = aim_facts(defaults())
        self.assertEqual(facts["aim_reference"], "witness_camera")
        self.assertFalse(facts["optical_framing_verified"])


class RecordedAimReferenceTests(unittest.TestCase):
    """The take has to record which camera decided it, not a fixed string."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.source = PerceptionSource(Path(self.folder.name) / "perception-source.json")

    def adapter(self, source):
        return BehaviorRecordingAdapter(service=None, perception_source=source)

    def test_a_take_records_the_witness_camera_and_its_unmeasured_offset(self):
        context = self.adapter(self.source).context("a" * 64, goal(), "behavior-1")
        self.assertEqual(context["aim_reference"], "witness_camera")
        self.assertEqual(context["witness_to_lens_offset"], "unmeasured")

    def test_a_take_on_the_phone_feed_records_that_instead(self):
        self.source.update(
            {
                "kind": "phone_lens_feed",
                "feed": "usb_hdmi_capture",
                "device_label": "USB Capture HDMI",
                "operator_confirmed": True,
            }
        )
        context = self.adapter(self.source).context("a" * 64, goal(), "behavior-1")
        self.assertEqual(context["aim_reference"], "phone_lens_feed")
        self.assertEqual(context["witness_to_lens_offset"], "none_same_lens")
        self.assertEqual(context["aim_source_device"], "USB Capture HDMI")
        self.assertEqual(context["identity_scope"], "transient_visual_tracks_not_person_identity")

    def test_without_a_configured_source_the_old_honest_default_stands(self):
        context = BehaviorRecordingAdapter(service=None).context("a" * 64, goal(), "behavior-1")
        self.assertEqual(context["aim_reference"], "witness_camera")
        self.assertEqual(context["witness_to_lens_offset"], "unmeasured")


if __name__ == "__main__":
    unittest.main()
