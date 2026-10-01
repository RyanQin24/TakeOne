"""The authored demo must actually perform its named moves; no provider or hardware."""

import copy
import json
import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from takeone.director.creative import digest
from takeone.director.studio import rehearsal_manifest
from takeone.previs.sequence import build_program
from takeone.previs.templates import DEFAULTS, defaults_for


class TemplateIsolationTests(unittest.TestCase):
    def test_editing_one_shots_channels_does_not_change_other_shots(self):
        # Restore the baseline even when exercising the pre-fix aliasing bug.
        with patch.dict(DEFAULTS, copy.deepcopy(DEFAULTS), clear=True):
            first = defaults_for("static")
            second = defaults_for("boom_up")
            before = copy.deepcopy(second)
            first["channels"]["gaze_pitch_rad"] = [dict(at=0, value=0.2, ease="hold")]
            first["camera"]["keyframes"].append(dict(at=0, focal_mm=50))
            self.assertEqual(second, before)
            self.assertEqual(defaults_for("boom_up"), before)


class ShotLanguageDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        with patch.object(sys, "path", [str(scripts), *sys.path]):
            sample = runpy.run_path(str(scripts / "shot_language_demo.py"))["project"]()
        document = sample["document"]
        detail = dict(
            creative=dict(document=document, context=sample["context"], digest=digest(document)),
            session=dict(brief=sample["brief"], session_id="offline-demo-audit", revision=1),
        )
        cls.manifest = rehearsal_manifest(detail, digest(document))

    def test_named_booms_produce_an_achieved_upward_move(self):
        # Match the real HTTP handoff used to reproduce the held boom shots.
        program = build_program(json.loads(json.dumps(self.manifest)))
        booms = [s for s in program["segments"] if s["template_id"] == "boom_up"]
        self.assertTrue(booms)
        for shot in booms:
            with self.subTest(shot=shot["shot_id"]):
                motion = shot["shot_review"]["motion"]
                self.assertEqual(motion["status"], "reviewable", motion["issues"])
                self.assertGreater(motion["checks"][0]["achieved_delta_m"], 0.01)

    def test_demo_retains_varied_edit_pacing_and_separate_location_resets(self):
        program = build_program(json.loads(json.dumps(self.manifest)))
        self.assertEqual(program["edit_duration_s"], 30)
        self.assertEqual(len(program["segments"]), 6)
        durations = [(s["edit"]["end_ms"] - s["edit"]["start_ms"]) / 1000 for s in program["segments"]]
        self.assertEqual(durations, [5, 4, 6, 4, 5, 6])
        self.assertTrue(all(s["dialogue"] is None for s in program["segments"]))
        self.assertEqual(len(program["relocations"]), 4)
        self.assertTrue(all(r["duration_s"] is None for r in program["relocations"]))
        self.assertGreater(program["duration_s"], program["edit_duration_s"])

    def test_manifest_compiles_without_a_json_roundtrip_to_coerce_numeric_types(self):
        program = build_program(self.manifest)
        self.assertEqual(len(program["segments"]), 6)
