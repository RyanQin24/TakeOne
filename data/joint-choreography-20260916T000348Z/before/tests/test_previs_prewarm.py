"""The warm grid covers every template, honours the cache bound, and reports failures."""

import importlib.util
import unittest

from takeone.previs.prewarm import GRID_DURATIONS_S, GRID_LIMIT, grid, warm

MUJOCO = all(importlib.util.find_spec(name) for name in ("mujoco", "scipy", "numpy"))


def fixture_catalog():
    return {
        "templates": [
            {"id": "static", "route": "hold", "parameters": ["duration_s", "radius_m"]},
            {"id": "pan_left", "route": "hold", "parameters": ["duration_s", "angle_rad"]},
            {"id": "push_in", "route": "line", "parameters": ["distance_m", "speed_m_s"]},
            {"id": "hero_orbit", "route": "arc", "parameters": ["radius_m", "sweep_rad"]},
        ]
    }


class GridTests(unittest.TestCase):
    def test_every_template_is_warmed_and_holds_get_the_duration_grid(self):
        settings = grid(fixture_catalog())
        by_template = {}
        for entry in settings:
            by_template.setdefault(entry["template_id"], []).append(entry)
        self.assertEqual(set(by_template), {"static", "pan_left", "push_in", "hero_orbit"})
        self.assertEqual(len(by_template["push_in"]), 1)
        self.assertEqual(len(by_template["static"]), 1 + len(GRID_DURATIONS_S))
        durations = [entry["duration_s"] for entry in by_template["static"][1:]]
        self.assertEqual(tuple(durations), GRID_DURATIONS_S)
        self.assertLessEqual(len(settings), GRID_LIMIT)

    def test_oversized_grid_fails_loudly(self):
        huge = {
            "templates": [{"id": f"t{i}", "route": "hold", "parameters": ["duration_s"]} for i in range(50)]
        }
        with self.assertRaises(ValueError):
            grid(huge)


class WarmTests(unittest.TestCase):
    def test_warm_counts_and_continues_past_failures(self):
        compiled, messages = [], []

        def compile_preview(settings):
            if settings["template_id"] == "broken":
                raise ValueError("no")
            compiled.append(settings["template_id"])

        report = warm(
            [{"template_id": "a"}, {"template_id": "broken"}, {"template_id": "b"}],
            compile_preview=compile_preview,
            log=messages.append,
        )
        self.assertEqual(compiled, ["a", "b"])
        self.assertEqual((report["warmed"], report["failed"]), (2, 1))
        self.assertTrue(any("broken" in message for message in messages))

    @unittest.skipUnless(MUJOCO, "real compile needs the simulation extra")
    def test_second_compile_is_a_cache_hit_under_100ms(self):
        import time

        from takeone.previs.cache import compile_preview

        settings = {"mode": "template", "template_id": "static", "duration_s": 5}
        compile_preview(settings)
        started = time.monotonic()
        compile_preview(settings)
        self.assertLess(time.monotonic() - started, 0.1)


if __name__ == "__main__":
    unittest.main()
