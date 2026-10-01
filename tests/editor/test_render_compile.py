"""Compiling to FFmpeg: determinism, and the safety rules from the architecture."""

import unittest

from takeone.editor import compile as compiler
from takeone.editor.errors import RenderError
from takeone.editor.operations import OperationType as T
from takeone.editor.operations import Target
from takeone.editor.reducer import apply
from takeone.editor.render.ffmpeg import SAFE_FILTER, compile_graph

from tests.editor.support import op, project_with_clips


def graded_project():
    state = project_with_clips(((0.0, 0.0, 3.0), (3.0, 4.0, 7.0)))
    state, _ = apply(
        state,
        op(
            T.APPLY_COLOR_CORRECTION,
            Target("clip", clip_id="c1"),
            exposure_stops=0.6,
            contrast=1.1,
            saturation=0.95,
            temperature_k=300.0,
        ),
    )
    state, _ = apply(
        state,
        op(
            T.APPLY_CREATIVE_LOOK,
            Target("clip", clip_id="c1"),
            look_id="spectrum_entrance",
            intensity=0.8,
        ),
    )
    state, _ = apply(
        state,
        op(
            T.APPLY_TRANSITION,
            Target("track", track_id="V1"),
            transition_id="t1",
            effect_id="whip",
            effect_version=1,
            from_clip_id="c1",
            to_clip_id="c2",
            duration_s=0.4,
        ),
    )
    state, _ = apply(
        state,
        op(
            T.ADD_EFFECT,
            Target("clip", clip_id="c2"),
            instance_id="fx1",
            effect_id="camera_shake",
            effect_version=1,
            parameters={"amplitude": 6.0, "frequency": 5.0},
        ),
    )
    return state


class Determinism(unittest.TestCase):
    def test_two_compilations_produce_identical_identities(self):
        state = graded_project()
        target = compiler.master_target(state)
        first = compiler.project_graph(state, target)
        second = compiler.project_graph(state, target)
        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(
            [item.node_id for item in first.topological()],
            [item.node_id for item in second.topological()],
        )

    def test_two_compilations_produce_identical_commands(self):
        state = graded_project()
        graph = compiler.project_graph(state, compiler.master_target(state))
        first = compile_graph(graph, "/tmp/out.mp4", binary="/usr/bin/ffmpeg")
        second = compile_graph(graph, "/tmp/out.mp4", binary="/usr/bin/ffmpeg")
        self.assertEqual(first.argv, second.argv)
        self.assertEqual(first.filter_complex, second.filter_complex)

    def test_preview_and_master_are_different_graphs(self):
        state = graded_project()
        preview = compiler.project_graph(state, compiler.preview_target(state))
        master = compiler.project_graph(state, compiler.master_target(state))
        self.assertNotEqual(preview.digest(), master.digest())


class Safety(unittest.TestCase):
    def test_the_command_is_a_list_and_never_a_shell_string(self):
        state = graded_project()
        graph = compiler.project_graph(state, compiler.master_target(state))
        plan = compile_graph(graph, "/tmp/out.mp4", binary="/usr/bin/ffmpeg")
        self.assertIsInstance(plan.argv, tuple)
        for argument in plan.argv:
            self.assertIsInstance(argument, str)
        self.assertNotIn("&&", " ".join(plan.argv))
        self.assertNotIn("|", plan.argv)

    def test_the_filter_graph_passes_the_character_allowlist(self):
        state = graded_project()
        graph = compiler.project_graph(state, compiler.master_target(state))
        plan = compile_graph(graph, "/tmp/out.mp4", binary="/usr/bin/ffmpeg")
        self.assertTrue(SAFE_FILTER.match(plan.filter_complex))

    def test_a_relative_media_path_is_refused(self):
        state = project_with_clips()
        state.media["m1"] = state.media["m1"].__class__(
            **{
                **{field: getattr(state.media["m1"], field) for field in state.media["m1"].__slots__},
                "path": "relative/file.mp4",
            }
        )
        graph = compiler.project_graph(state, compiler.master_target(state))
        with self.assertRaises(RenderError):
            compile_graph(graph, "/tmp/out.mp4", binary="/usr/bin/ffmpeg")

    def test_every_video_and_original_audio_source_is_seeked_at_the_input(self):
        state = graded_project()
        graph = compiler.project_graph(state, compiler.master_target(state))
        plan = compile_graph(graph, "/tmp/out.mp4", binary="/usr/bin/ffmpeg")
        # Picture and audio are independently seeked: a preview can use its silent
        # proxy for video while retaining original embedded sound.
        self.assertEqual(plan.argv.count("-i"), 4)
        self.assertEqual(plan.argv.count("-ss"), 4)

    def test_an_unknown_transition_mode_is_refused(self):
        state = project_with_clips(((0.0, 0.0, 3.0), (3.0, 4.0, 7.0)))
        state, _ = apply(
            state,
            op(
                T.APPLY_TRANSITION,
                Target("track", track_id="V1"),
                transition_id="t1",
                effect_id="crossfade",
                effect_version=1,
                from_clip_id="c1",
                to_clip_id="c2",
                duration_s=0.4,
                parameters={"mode": "teleport"},
            ),
        )
        graph = compiler.project_graph(state, compiler.master_target(state))
        with self.assertRaises(RenderError):
            compile_graph(graph, "/tmp/out.mp4", binary="/usr/bin/ffmpeg")


class ColourManagement(unittest.TestCase):
    def test_exposure_is_applied_in_a_linear_working_space(self):
        state = graded_project()
        graph = compiler.project_graph(state, compiler.master_target(state))
        plan = compile_graph(graph, "/tmp/out.mp4", binary="/usr/bin/ffmpeg")
        self.assertIn("t=linear", plan.filter_complex)
        self.assertIn("exposure=exposure=", plan.filter_complex)

    def test_a_described_but_unconvertible_space_fails_loudly(self):
        from dataclasses import replace

        state = project_with_clips()
        item = state.media["m1"]
        state.media["m1"] = replace(item, source_space="apple-log")
        with self.assertRaises(Exception) as caught:
            compiler.project_graph(state, compiler.master_target(state))
        self.assertIn("apple-log", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
