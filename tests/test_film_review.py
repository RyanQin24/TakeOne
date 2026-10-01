"""Edited cuts use retained source samples, not setup or an unused tail."""

import copy
import unittest

from takeone.previs.film_review import edit_boundaries, review_cuts

from tests.test_screen_review import fixture


class FilmReviewTests(unittest.TestCase):
    def test_trimmed_source_tail_is_not_the_edited_ending(self):
        shot, settings, scene, mark, preview = fixture()
        shot["end_ms"] = 2000
        preview["frames"][-1]["actor"]["position_m"] = [99, 0, 0]
        evidence = edit_boundaries(shot, settings, scene, dict(origin_m=[0, 0], heading_rad=0), preview)
        self.assertEqual(evidence["source_window_s"], [0, 2])
        self.assertEqual(evidence["ending"]["actors"]["visitor"]["position_m"], [0, 0, 0])

    def test_raw_and_processed_orientations_remain_distinct(self):
        shot, settings, scene, mark, preview = fixture()
        for frame in preview["frames"]:
            frame["camera_view"] = dict(pos=frame["camera"]["pos"], quat=[0, 0, 0, 1])
        original = copy.deepcopy(preview)
        evidence = edit_boundaries(shot, settings, scene, dict(origin_m=[2, 3], heading_rad=0), preview)
        self.assertNotEqual(
            evidence["ending"]["raw_optical_pose"]["quat"],
            evidence["ending"]["simulated_output_pose"]["quat"],
        )
        self.assertEqual(evidence["ending"]["raw_optical_pose"]["pos"], [2, 0, 1.59])
        self.assertEqual(preview, original)

    def test_short_source_labels_the_preview_hold(self):
        shot, settings, scene, mark, preview = fixture()
        shot["end_ms"] = 6000
        evidence = edit_boundaries(shot, settings, scene, dict(origin_m=[0, 0], heading_rad=0), preview)
        self.assertEqual(evidence["preview_hold_s"], 2)
        self.assertEqual(evidence["ending"]["source_s"], 4)

    def test_axis_crossing_is_evidence_not_a_universal_error(self):
        actors = {"a": dict(position_m=[0, 0, 0]), "b": dict(position_m=[1, 0, 0])}
        left = dict(actors=actors, raw_optical_pose=dict(pos=[0, -3, 1]))
        right = dict(actors=actors, raw_optical_pose=dict(pos=[0, 3, 1]))
        segments = [
            dict(
                shot_id="s1",
                scene_id="room",
                space_id="set",
                edit=dict(start_ms=0),
                edit_evidence=dict(opening=left, ending=left),
            ),
            dict(
                shot_id="s2",
                scene_id="room",
                space_id="set",
                edit=dict(start_ms=2000),
                shot_card=dict(continuity="Deliberate reverse viewpoint."),
                edit_evidence=dict(opening=right, ending=right),
            ),
        ]
        report = review_cuts(segments, [dict(scene_id="room", objects=[])])
        cut = report["cuts"][0]
        self.assertTrue(cut["axis_crossing_observed"])
        self.assertEqual(cut["authored_continuity"], "Deliberate reverse viewpoint.")
        self.assertNotIn("status", cut)

    def test_other_location_does_not_claim_matching_coordinates(self):
        actors = {"a": dict(position_m=[0, 0, 0])}
        boundary = dict(actors=actors, raw_optical_pose=dict(pos=[0, -3, 1]))
        segments = [
            dict(
                shot_id=str(i),
                scene_id=str(i),
                space_id=str(i),
                edit=dict(start_ms=i * 1000),
                edit_evidence=dict(opening=boundary, ending=boundary),
            )
            for i in (0, 1)
        ]
        report = review_cuts(segments, [dict(scene_id=str(i), objects=[]) for i in (0, 1)])
        self.assertFalse(report["cuts"][0]["same_space"])
        self.assertEqual(report["cuts"][0]["actor_position_change_m"], {})
