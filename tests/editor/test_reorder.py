"""Manual timeline moves use the same journal, replay and renderer as other edits."""

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from takeone.editor import patch, reducer, state
from takeone.editor.errors import OperationError, ValidationError
from takeone.editor.operations import OperationType as T
from takeone.editor.operations import Target
from takeone.editor.repository import ProjectRepository
from takeone.editor.service import EditorService

from tests.editor.support import media_op, op, project_with_clips


class Reorder(unittest.TestCase):
    def setUp(self):
        self.current = project_with_clips(((0, 0, 2), (2, 2, 5), (5, 5, 6)))

    def move(self, current, clip_id, index):
        return reducer.apply(current, op(T.REORDER_CLIP, Target("clip", clip_id=clip_id), index=index))

    def test_move_first_to_last_and_back_preserves_sources_and_duration(self):
        moved, changes = self.move(self.current, "c1", 2)
        clips = moved.timeline.track("V1").clips
        self.assertEqual([c.clip_id for c in clips], ["c2", "c3", "c1"])
        self.assertEqual([c.timeline_start_s for c in clips], [0, 3, 4])
        self.assertEqual(moved.timeline.duration_s, 6)
        for c in clips:
            original = self.current.timeline.track("V1").clip(c.clip_id)
            self.assertEqual(
                (c.source_start_s, c.source_end_s, c.color, c.speed_curve),
                (original.source_start_s, original.source_end_s, original.color, original.speed_curve),
            )
        self.assertEqual(patch.apply(self.current.wire(), changes), moved.wire())
        restored, _ = self.move(moved, "c1", 0)
        self.assertEqual(restored.timeline, self.current.timeline)

    def test_invalid_index_and_unknown_clip_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.move(self.current, "c1", -1)
        for clip_id, index in (("c1", 3), ("missing", 0)):
            with self.assertRaises(OperationError):
                self.move(self.current, clip_id, index)

    def test_noop_keeps_timeline_and_mixed_fps_do_not_overlap(self):
        same, _ = self.move(self.current, "c2", 1)
        self.assertEqual(same.timeline, self.current.timeline)
        current, _ = reducer.apply(state.empty("mixed"), media_op("m", fps_num=24))
        current, _ = reducer.apply(current, op(T.ADD_TRACK, Target.project(), track_id="V1", kind="video"))
        for i in range(3):
            current, _ = reducer.apply(
                current,
                op(
                    T.ADD_CLIP,
                    Target("track", track_id="V1"),
                    clip_id=f"c{i}",
                    media_id="m",
                    timeline_start_s=current.timeline.duration_s,
                    source_start_s=0,
                    source_end_s=7 / 24,
                ),
            )
        moved, _ = self.move(current, "c0", 2)
        self.assertEqual(moved.timeline.track("V1").overlaps(), [])

    def test_preserves_adjacent_transitions_but_removes_separated_ones(self):
        current, _ = reducer.apply(
            self.current,
            op(
                T.APPLY_TRANSITION,
                Target("track", track_id="V1"),
                transition_id="t",
                effect_id="crossfade",
                effect_version=1,
                from_clip_id="c1",
                to_clip_id="c2",
                duration_s=0.5,
            ),
        )
        kept, _ = self.move(current, "c3", 0)
        self.assertEqual(kept.timeline.transitions, current.timeline.transitions)
        self.assertEqual(kept.timeline.duration_s, 5.5)
        separated, _ = self.move(current, "c1", 2)
        self.assertEqual(separated.timeline.transitions, ())
        self.assertEqual(separated.timeline.duration_s, 6)

    def test_reorder_is_one_undo_step_and_survives_reload(self):
        with TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "projects.sqlite3")
            service = EditorService(repository)
            service.create("p", "Manual edit")
            service.submit("p", media_op("m"))
            service.submit("p", op(T.ADD_TRACK, Target.project(), track_id="V1", kind="video"))
            for i in range(3):
                service.submit(
                    "p",
                    op(
                        T.ADD_CLIP,
                        Target("track", track_id="V1"),
                        clip_id=f"c{i}",
                        media_id="m",
                        timeline_start_s=i * 2,
                        source_start_s=0,
                        source_end_s=2,
                    ),
                )
            before = service.state("p")
            service.submit("p", op(T.REORDER_CLIP, Target("clip", clip_id="c0"), index=2))
            self.assertEqual(EditorService(repository).state("p").wire(), service.state("p").wire())
            service.undo("p", 1)
            self.assertEqual(service.state("p").wire(), before.wire())

    def test_clip_local_effect_span_travels_unchanged(self):
        track = self.current.timeline.track("V1")
        effect = state.EffectInstance("e", "vignette", 1, {}, 0.2, 0.8)
        decorated = replace(track.clip("c3"), effects=(effect,))
        current = replace(
            self.current,
            timeline=self.current.timeline.with_track(
                track.with_clips(tuple(decorated if c.clip_id == "c3" else c for c in track.clips))
            ),
        )
        moved, _ = self.move(current, "c3", 0)
        self.assertEqual(moved.timeline.track("V1").clip("c3").effects, (effect,))
