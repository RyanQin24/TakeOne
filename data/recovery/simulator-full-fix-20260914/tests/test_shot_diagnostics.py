"""Every diagnostic fires on its own case, stays silent on its neighbour, and never blocks."""

import math
import unittest

from takeone.previs import diagnostics
from takeone.previs.diagnostics import ADVISORY, BLOCKING, CODES, Diagnostic
from takeone.previs.sequence import LONG_MOVE_S, SET_LIMIT_M, build_program
from takeone.previs.templates import defaults_for, screen_geometry


def shot(index, template, mark, start_ms, end_ms, framing="medium", **overrides):
    return dict(
        shot_id=f"s{index}", start_ms=start_ms, end_ms=end_ms, actor_id="a1", mark_id=mark,
        action="", framing=framing, camera_intent="", light_intent="", dialogue="",
        name=template, error=None, defaulted_parameters=[], settings=defaults_for(template) | overrides,
    )


def manifest(shots, marks):
    return dict(
        kind="takeone_director_rehearsal", schema_version=1, title="T", session_id="s",
        document_digest="d", manifest_digest="m", marks=marks, shots=shots,
    )


class RecordTests(unittest.TestCase):
    def test_only_a_compiler_refusal_is_blocking(self):
        self.assertEqual(
            {code for code, severity in CODES.items() if severity == BLOCKING},
            {"unresolved_movement", "unknown_parameter", "out_of_range", "compile_failed"},
        )
        for code, severity in CODES.items():
            self.assertIn(severity, (BLOCKING, ADVISORY))

    def test_an_unknown_code_cannot_be_constructed(self):
        with self.assertRaises(ValueError):
            Diagnostic("s1", "invented_code", "…")

    def test_the_wire_form_carries_severity_and_a_list_for_allowed(self):
        wire = Diagnostic("s1", "aim_reach", "…", observed=4.0).wire()
        self.assertEqual(wire["severity"], ADVISORY)
        self.assertEqual(wire["allowed"], [])
        self.assertEqual(wire["shot_id"], "s1")


class UnitTests(unittest.TestCase):
    def test_timing_fires_only_outside_its_tolerance(self):
        self.assertIsNone(diagnostics.timing("s1", 6.0, 6.0))
        self.assertIsNone(diagnostics.timing("s1", 6.5, 6.0))
        self.assertIsNone(diagnostics.timing("s1", 2.4, 2.0))
        longer = diagnostics.timing("s1", 20.0, 6.0)
        self.assertEqual(longer.code, "duration_mismatch")
        self.assertFalse(longer.blocking)
        self.assertIn("shorten the route", longer.suggestion)
        self.assertIn("lengthen the route", diagnostics.timing("s1", 1.0, 6.0).suggestion)

    def test_framing_accepts_any_band_the_move_travels_through(self):
        push = screen_geometry(defaults_for("push_in"))
        self.assertIsNone(diagnostics.framing("s1", "wide", push))
        self.assertIsNone(diagnostics.framing("s1", "medium", push))
        self.assertIsNone(diagnostics.framing("s1", None, push))
        mismatch = diagnostics.framing("s1", "close_up", push)
        self.assertEqual(mismatch.code, "framing_mismatch")
        self.assertEqual(mismatch.parameter, "focal_mm")

    def test_reach_reports_what_the_arm_achieved_and_stays_quiet_when_it_hit_the_mark(self):
        self.assertEqual(diagnostics.reach("s1", {"max_aim_error_deg": 1.0}), [])
        codes = [d.code for d in diagnostics.reach(
            "s1", {"max_aim_error_deg": 6.2, "camera_height_m": 1.4, "requested_camera_height_m": 1.59})]
        self.assertEqual(codes, ["aim_reach", "height_reach"])
        self.assertEqual(
            diagnostics.reach("s1", {"camera_height_m": 1.58, "requested_camera_height_m": 1.59}), []
        )

    def test_placement_and_long_move_use_their_stated_limits(self):
        self.assertIsNone(diagnostics.placement("s1", [SET_LIMIT_M, 0.0], SET_LIMIT_M))
        self.assertEqual(
            diagnostics.placement("s1", [SET_LIMIT_M + 0.1, 0.0], SET_LIMIT_M).code, "mark_placement"
        )
        self.assertIsNone(diagnostics.long_move("m1", LONG_MOVE_S, LONG_MOVE_S))
        self.assertEqual(diagnostics.long_move("m1", LONG_MOVE_S + 1, LONG_MOVE_S).code, "reposition_long")


class ProgramTests(unittest.TestCase):
    def test_a_shot_with_diagnostics_still_plays_its_full_length(self):
        marks = [dict(mark_id="A", description="", position_m=[0.0, 0.0], facing_rad=0.0)]
        program = build_program(
            manifest([shot(1, "orbit_360", "A", 0, 5000, framing="close_up")], marks)
        )
        segment = program["segments"][0]
        self.assertEqual(segment["kind"], "shot")
        self.assertIsNone(segment["error"])
        self.assertGreater(segment["duration_s"], 5.0)
        codes = {d["code"] for d in segment["diagnostics"]}
        self.assertIn("duration_mismatch", codes)
        self.assertIn("framing_mismatch", codes)
        self.assertTrue(all(d["severity"] == ADVISORY for d in segment["diagnostics"]))

    def test_a_mark_outside_the_drawn_set_is_a_note_not_a_refusal(self):
        marks = [dict(mark_id="A", description="", position_m=[SET_LIMIT_M + 3, 0.0], facing_rad=0.0)]
        program = build_program(manifest([shot(1, "static", "A", 0, 4000, duration_s=4.0)], marks))
        segment = program["segments"][0]
        self.assertEqual(segment["kind"], "shot")
        self.assertIn("mark_placement", {d["code"] for d in segment["diagnostics"]})
        self.assertEqual(segment["stage"]["origin_m"][0], SET_LIMIT_M + 3)

    def test_a_shot_the_translator_refused_is_listed_for_repair(self):
        broken = shot(1, "static", "A", 0, 4000, duration_s=4.0)
        broken["settings"] = None
        broken["error"] = "speed_m_s is 9; the rig accepts 0.14 to 0.35."
        broken["diagnostic"] = Diagnostic(
            "s1", "out_of_range", broken["error"], parameter="speed_m_s", observed=9.0, allowed=(0.14, 0.35)
        ).wire()
        marks = [dict(mark_id="A", description="", position_m=[0.0, 0.0], facing_rad=0.0)]
        program = build_program(manifest([broken, shot(2, "static", "A", 4000, 8000, duration_s=4.0)], marks))
        self.assertEqual(program["blocked_shot_ids"], ["s1"])
        self.assertEqual(program["segments"][0]["diagnostics"][0]["parameter"], "speed_m_s")
        self.assertEqual(program["segments"][1]["kind"], "shot")


if __name__ == "__main__":
    unittest.main()
