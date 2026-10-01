"""Heuristic planner: a watchable cut from probe signals, no network, no FFmpeg."""

import unittest
from dataclasses import replace

from takeone.editor import reducer, state
from takeone.editor.plan import HeuristicPlanner, run

from tests.editor.support import media_op  # noqa: F401


def _import(current, media_id, name, duration_s, fps_num=24, fps_den=1, width=3840, height=2160):
    current, _ = reducer.apply(
        current,
        media_op(
            media_id,
            name,
            duration_s,
            fps_num=fps_num,
            fps_den=fps_den,
            width=width,
            height=height,
        ),
    )
    return current


class Box:
    def __init__(self, value):
        self.value = value

    def submit(self, operation):
        self.value, _ = reducer.apply(self.value, operation)


class HeuristicCut(unittest.TestCase):
    def test_mixed_takes_become_a_graded_film(self):
        box = Box(
            replace(
                state.empty("p-plan"),
                intent=state.CreativeIntent(
                    "Make a mysterious luxury introduction that becomes powerful.",
                    12.0,
                ),
            )
        )
        for media_id, name, duration_s, fps_num, width, height in (
            ("m1", "Wide hall", 8.2, 24, 3840, 2160),
            ("m2", "Portrait", 6.0, 30, 1920, 1080),
            ("m3", "Impact", 5.017, 60, 3840, 2160),
            ("m4", "Close", 7.4, 25, 3840, 2160),
        ):
            box.value = _import(box.value, media_id, name, duration_s, fps_num, 1, width, height)

        planner = HeuristicPlanner()
        applied = run(
            lambda: planner.next_operation(box.value),
            box.submit,
            pace_s=0.0,
        )
        current = box.value
        self.assertGreater(applied, 12)
        self.assertEqual(current.phase, "complete")
        track = current.timeline.tracks[0]
        self.assertEqual(len(track.clips), 4)
        self.assertEqual(len(track.overlaps()), len(current.timeline.transitions))
        self.assertGreaterEqual(len(current.timeline.transitions), 1)
        self.assertTrue(all(clip.color.look_id for clip in track.clips))
        self.assertEqual(track.clips[0].color.look_id, "luxury_warm")
        self.assertEqual(track.clips[-1].color.look_id, "action_impact")
        self.assertTrue(any(item.effect_id == "fade" for item in track.clips[0].effects))
        self.assertTrue(all(item.state == "selected" for item in current.selection.values()))

    def test_the_same_intent_produces_the_same_kinds(self):
        def kinds_for():
            box = Box(
                replace(
                    state.empty("p-det"),
                    intent=state.CreativeIntent("A slow noir reveal.", 8.0),
                )
            )
            box.value = _import(box.value, "a", "A", 5.0)
            box.value = _import(box.value, "b", "B", 5.0)
            planner = HeuristicPlanner()
            kinds = []
            run(
                lambda: planner.next_operation(box.value),
                lambda operation: kinds.append(str(operation.type)) or box.submit(operation),
                pace_s=0.0,
            )
            return tuple(kinds), box.value.timeline.tracks[0].clips[0].color.look_id

        first, look = kinds_for()
        second, look_again = kinds_for()
        self.assertEqual(first, second)
        self.assertEqual(look, look_again)

    def test_nothing_to_do_without_media(self):
        planner = HeuristicPlanner()
        self.assertIsNone(planner.next_operation(state.empty("empty")))


if __name__ == "__main__":
    unittest.main()
