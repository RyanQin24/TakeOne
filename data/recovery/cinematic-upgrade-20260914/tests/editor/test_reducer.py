"""The fold. Every operation type is exercised, and every one that should be refused is."""

import unittest

from takeone.editor import patch, reducer, state
from takeone.editor.errors import OperationError, ValidationError
from takeone.editor.operations import OperationType as T
from takeone.editor.operations import Target
from takeone.editor.timing.curve import SpeedCurve

from tests.editor.support import media_op, op, project_with_clips


class Structure(unittest.TestCase):
    def test_import_registers_media_and_a_pending_selection(self):
        current, _ = reducer.apply(state.empty("p"), media_op("m1"))
        self.assertIn("m1", current.media)
        self.assertEqual(current.selection["m1"].state, "pending")

    def test_importing_the_same_media_twice_is_refused(self):
        current, _ = reducer.apply(state.empty("p"), media_op("m1"))
        with self.assertRaises(OperationError):
            reducer.apply(current, media_op("m1"))

    def test_clip_beyond_the_media_is_refused(self):
        current = project_with_clips()
        with self.assertRaises(OperationError):
            reducer.apply(
                current,
                op(
                    T.ADD_CLIP,
                    Target("track", track_id="V1"),
                    clip_id="cx",
                    media_id="m1",
                    timeline_start_s=5.0,
                    source_start_s=9.0,
                    source_end_s=99.0,
                ),
            )

    def test_overlapping_clips_are_refused(self):
        current = project_with_clips(((0.0, 0.0, 2.0),))
        with self.assertRaises(OperationError):
            reducer.apply(
                current,
                op(
                    T.ADD_CLIP,
                    Target("track", track_id="V1"),
                    clip_id="c2",
                    media_id="m1",
                    timeline_start_s=1.0,
                    source_start_s=3.0,
                    source_end_s=5.0,
                ),
            )

    def test_remove_ripples_the_following_clips(self):
        current = project_with_clips(((0.0, 0.0, 2.0), (2.0, 3.0, 5.0), (4.0, 6.0, 7.0)))
        current, _ = reducer.apply(current, op(T.REMOVE_CLIP, Target("clip", clip_id="c2")))
        track = current.timeline.track("V1")
        self.assertEqual([clip.clip_id for clip in track.clips], ["c1", "c3"])
        self.assertAlmostEqual(track.clip("c3").timeline_start_s, 2.0, places=9)

    def test_split_conserves_total_duration(self):
        current = project_with_clips(((0.0, 0.0, 4.0),))
        before = current.timeline.duration_s
        current, _ = reducer.apply(
            current, op(T.SPLIT_CLIP, Target("clip", clip_id="c1"), time_s=1.5, new_clip_id="c1b")
        )
        self.assertAlmostEqual(current.timeline.duration_s, before, places=6)
        self.assertEqual(len(current.timeline.track("V1").clips), 2)


class Rhythm(unittest.TestCase):
    def test_trim_ripples_and_snaps_to_the_media_frame_grid(self):
        current = project_with_clips(((0.0, 0.0, 3.0), (3.0, 4.0, 6.0)))
        current, _ = reducer.apply(
            current, op(T.TRIM_CLIP, Target("clip", clip_id="c1"), edge="out", source_end_s=2.017)
        )
        track = current.timeline.track("V1")
        frame = current.media_item("m1").probe.frame_s
        self.assertAlmostEqual(track.clip("c1").source_end_s, round(round(2.017 / frame) * frame, 9))
        self.assertAlmostEqual(track.clip("c2").timeline_start_s, track.clip("c1").timeline_end_s, places=9)

    def test_trim_that_leaves_less_than_a_frame_is_refused(self):
        current = project_with_clips(((0.0, 0.0, 3.0),))
        with self.assertRaises(OperationError):
            reducer.apply(
                current, op(T.TRIM_CLIP, Target("clip", clip_id="c1"), edge="out", source_end_s=0.001)
            )

    def test_speed_curve_is_refitted_to_the_clip_and_ripples(self):
        current = project_with_clips(((0.0, 0.0, 3.0), (3.0, 4.0, 6.0)))
        curve = SpeedCurve.ramp(4.0, 0.42)
        current, _ = reducer.apply(
            current, op(T.APPLY_SPEED_CURVE, Target("clip", clip_id="c1"), curve=curve.wire())
        )
        clip = current.timeline.track("V1").clip("c1")
        self.assertAlmostEqual(clip.speed_curve.source_duration_s, 3.0, places=6)
        self.assertGreater(clip.timeline_duration_s, 3.0)
        self.assertAlmostEqual(
            current.timeline.track("V1").clip("c2").timeline_start_s,
            clip.timeline_end_s,
            places=6,
        )

    def test_freeze_frame_extends_the_timeline_by_the_hold(self):
        current = project_with_clips(((0.0, 0.0, 3.0),))
        before = current.timeline.duration_s
        current, _ = reducer.apply(
            current, op(T.FREEZE_FRAME, Target("clip", clip_id="c1"), time_s=1.0, hold_s=0.8)
        )
        self.assertAlmostEqual(current.timeline.duration_s, before + 0.8, delta=0.05)
        self.assertEqual(len(current.timeline.track("V1").clips), 3)

    def test_transition_overlaps_the_clips_and_shortens_the_film(self):
        current = project_with_clips(((0.0, 0.0, 3.0), (3.0, 4.0, 7.0)))
        current, _ = reducer.apply(
            current,
            op(
                T.APPLY_TRANSITION,
                Target("track", track_id="V1"),
                transition_id="t1",
                effect_id="crossfade",
                effect_version=1,
                from_clip_id="c1",
                to_clip_id="c2",
                duration_s=0.5,
            ),
        )
        self.assertAlmostEqual(current.timeline.duration_s, 5.5, places=6)
        self.assertEqual(len(current.timeline.transitions), 1)

    def test_transition_longer_than_a_clip_is_refused(self):
        current = project_with_clips(((0.0, 0.0, 0.5), (0.5, 4.0, 7.0)))
        with self.assertRaises(OperationError):
            reducer.apply(
                current,
                op(
                    T.APPLY_TRANSITION,
                    Target("track", track_id="V1"),
                    transition_id="t1",
                    effect_id="crossfade",
                    effect_version=1,
                    from_clip_id="c1",
                    to_clip_id="c2",
                    duration_s=2.0,
                ),
            )

    def test_beat_alignment_is_a_roll_edit_that_preserves_duration(self):
        current = project_with_clips(((0.0, 0.0, 3.0), (3.0, 4.0, 7.0)))
        before = current.timeline.duration_s
        current, _ = reducer.apply(
            current,
            op(
                T.ALIGN_CUT_TO_BEAT,
                Target("track", track_id="V1"),
                clip_id="c2",
                beat_time_s=3.2,
                max_shift_s=0.25,
            ),
        )
        track = current.timeline.track("V1")
        self.assertAlmostEqual(current.timeline.duration_s, before, places=6)
        self.assertAlmostEqual(track.clip("c2").timeline_start_s, 3.2, places=6)
        self.assertAlmostEqual(track.clip("c1").timeline_end_s, 3.2, places=6)


class Colour(unittest.TestCase):
    def test_colour_correction_records_only_what_it_was_given(self):
        current = project_with_clips()
        current, _ = reducer.apply(
            current, op(T.APPLY_COLOR_CORRECTION, Target("clip", clip_id="c1"), exposure_stops=0.5)
        )
        grade = current.timeline.track("V1").clip("c1").color
        self.assertEqual(grade.exposure_stops, 0.5)
        self.assertEqual(grade.contrast, 1.0)

    def test_out_of_range_correction_is_refused_rather_than_clamped(self):
        with self.assertRaises(ValidationError):
            op(T.APPLY_COLOR_CORRECTION, Target("clip", clip_id="c1"), exposure_stops=9.0)

    def test_matching_records_its_reference(self):
        current = project_with_clips(((0.0, 0.0, 2.0), (2.0, 3.0, 5.0)))
        current, _ = reducer.apply(
            current,
            op(
                T.MATCH_COLOR,
                Target("clip", clip_id="c2"),
                reference_clip_id="c1",
                exposure_stops=-0.2,
                temperature_k=120.0,
                tint=0.05,
                contrast=0.98,
            ),
        )
        self.assertEqual(current.timeline.track("V1").clip("c2").color.matched_to, "c1")


class Lifecycle(unittest.TestCase):
    def test_finalize_refuses_an_empty_timeline(self):
        current = state.empty("p")
        with self.assertRaises(OperationError):
            reducer.apply(current, op(T.FINALIZE_TIMELINE, Target.project()))

    def test_a_finalized_timeline_refuses_further_edits(self):
        current = project_with_clips()
        current, _ = reducer.apply(current, op(T.FINALIZE_TIMELINE, Target.project()))
        with self.assertRaises(OperationError):
            reducer.apply(
                current, op(T.APPLY_COLOR_CORRECTION, Target("clip", clip_id="c1"), exposure_stops=0.1)
            )

    def test_version_increments_once_per_operation(self):
        current = project_with_clips(((0.0, 0.0, 2.0), (2.0, 3.0, 5.0)))
        self.assertEqual(current.version, 4)


class PatchAgreement(unittest.TestCase):
    def test_published_patches_reproduce_the_folded_state(self):
        operations = [
            media_op("m1"),
            op(T.ADD_TRACK, Target.project(), track_id="V1", kind="video"),
            op(
                T.ADD_CLIP,
                Target("track", track_id="V1"),
                clip_id="c1",
                media_id="m1",
                timeline_start_s=0.0,
                source_start_s=0.0,
                source_end_s=2.0,
            ),
            op(T.APPLY_COLOR_CORRECTION, Target("clip", clip_id="c1"), exposure_stops=0.4),
            op(T.APPLY_CREATIVE_LOOK, Target("clip", clip_id="c1"), look_id="luxury_warm", intensity=0.6),
            op(
                T.ADD_EFFECT,
                Target("clip", clip_id="c1"),
                instance_id="e1",
                effect_id="film_grain",
                effect_version=1,
                parameters={"intensity": 9.0},
            ),
            op(T.TRIM_CLIP, Target("clip", clip_id="c1"), edge="in", source_start_s=0.3),
        ]
        final, patches = reducer.fold(state.empty("p"), operations)
        mirror = state.empty("p").wire()
        for entry in patches:
            mirror = patch.apply(mirror, entry)
        self.assertEqual(mirror, final.wire())


if __name__ == "__main__":
    unittest.main()
