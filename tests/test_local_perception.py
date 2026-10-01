"""Transient local person tracking: continuity without identity claims."""

import unittest

from takeone.perception import PerceptionState, PersonDetection, PersonTracker


def detection(left, top=0.2, width=0.2, height=0.5, confidence=0.9):
    return PersonDetection((left, top, left + width, top + height), confidence)


class PerceptionContractTests(unittest.TestCase):
    def test_detection_requires_normalized_ordered_box(self):
        with self.assertRaises(ValueError):
            PersonDetection((0.8, 0.2, 0.2, 0.9), 0.9)
        with self.assertRaises(ValueError):
            PersonDetection((0.1, 0.2, 0.3, 0.9), 2)

    def test_active_subject_must_reference_visible_track(self):
        tracker = PersonTracker()
        person = tracker.update(1_000_000_000, [detection(0.2)])[0]
        state = PerceptionState(1_000_000_000, 12, (person,), (person.track_id,))
        self.assertEqual(state.wire()["identity_scope"], "transient_visual_tracks_not_person_identity")
        with self.assertRaises(ValueError):
            PerceptionState(1_000_000_000, 0, (person,), ("person-missing",))


class PersonTrackerTests(unittest.TestCase):
    def test_small_motion_keeps_transient_track_id(self):
        tracker = PersonTracker()
        first = tracker.update(1_000_000_000, [detection(0.20)])[0]
        second = tracker.update(1_100_000_000, [detection(0.23)])[0]
        self.assertEqual(first.track_id, second.track_id)
        self.assertGreater(second.velocity_uv_s[0], 0)

    def test_short_occlusion_keeps_track_but_long_loss_creates_new_one(self):
        tracker = PersonTracker(max_missing_ms=500)
        first = tracker.update(1_000_000_000, [detection(0.20)])[0]
        self.assertEqual(tracker.update(1_300_000_000, []), ())
        returned = tracker.update(1_450_000_000, [detection(0.22)])[0]
        self.assertEqual(returned.track_id, first.track_id)
        tracker.update(2_100_000_000, [])
        replacement = tracker.update(2_110_000_000, [detection(0.22)])[0]
        self.assertNotEqual(replacement.track_id, first.track_id)

    def test_two_people_do_not_share_one_track(self):
        tracker = PersonTracker()
        first = tracker.update(1_000_000_000, [detection(0.1), detection(0.65)])
        second = tracker.update(1_100_000_000, [detection(0.12), detection(0.63)])
        self.assertEqual({p.track_id for p in first}, {p.track_id for p in second})
        self.assertEqual(len({p.track_id for p in second}), 2)


if __name__ == "__main__":
    unittest.main()
