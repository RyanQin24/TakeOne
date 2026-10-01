"""Production state stays bounded and document-derived; the persona stays locked and honest."""

import importlib.util
import json
import unittest
from pathlib import Path

from takeone.director.shot_design import defaults as shot_design
from takeone.director.skills import SKILLS, cinematic_sample, sample_project
from takeone.voice.persona import PERSONA_MAX_BYTES, build_persona
from takeone.voice.session_context import (
    PRODUCTION_STATE_MAX_BYTES,
    build_production_state,
    cached_production_state,
)

SCIPY = importlib.util.find_spec("scipy") is not None


def fixture_catalog(templates=28):
    """Shaped like director.studio.movement_catalog() without importing the compiler stack."""
    fields = {
        f"field_{index}": {
            "label": f"Field {index}",
            "minimum": 0.1,
            "maximum": 25.0,
            "scale": 1.0,
            "unit": "m",
            "step": 0.05,
        }
        for index in range(16)
    }
    return {
        "version": 1,
        "coordinate_frame": "shot-local X/Y floor, Z up; tracked actor starts at (0,0)",
        "grid_m": 0.3048,
        "fields": fields,
        "lens_field": {
            "label": "Starting focal length",
            "minimum": 13,
            "maximum": 77,
            "scale": 1,
            "unit": "mm",
            "step": 1,
        },
        "templates": [
            {
                "id": f"template_{index}",
                "name": f"Template {index} · a descriptive name",
                "intent": "A sentence of dramatic intent long enough to be realistic in size.",
                "route": "arc",
                "aim": "face",
                "parameters": sorted(fields)[:8],
                "defaults": {name: 1.25 for name in sorted(fields)[:8]},
            }
            for index in range(templates)
        ],
        "timing": "Shot-local takes; planned edit time excludes setup.",
        "tracking": "One scripted actor per shot.",
    }


def build(document_source=cinematic_sample, **overrides):
    sample = document_source()
    arguments = dict(
        session_id="0" * 36,
        brief=sample["brief"],
        document=sample["document"],
        document_digest="d" * 64,
        skill=SKILLS[sample["context"]["skill_id"]],
        verdicts=[{"take_id": "t", "score": 0.8, "reason": "sharp"}] * 5,
        catalog=fixture_catalog(),
    )
    arguments.update(overrides)
    return build_production_state(**arguments)


class ProductionStateTests(unittest.TestCase):
    @unittest.skipUnless(SCIPY, "real movement catalog needs the simulation extra")
    def test_silent_multiscene_direction_survives_in_bounded_voice_context(self):
        sample = json.loads(
            (Path(__file__).parent / "fixtures/director_arrival.json").read_text(encoding="utf-8")
        )
        doc = sample["document"]
        doc["visual_style"] = {"sound": "Footfalls give way to the room tone."}
        for scene in doc["scenes"]:
            for shot in scene["shots"]:
                shot["lines"] = []
                shot["selected_line"] = 0
                shot["design"] = shot_design(shot)
                shot["audio_intent"] = "A breath before the next action."
        state = build(lambda: sample, catalog=None)
        self.assertEqual(state["script"]["visual_style"], doc["visual_style"])
        for scene, source in zip(state["script"]["scenes"], doc["scenes"], strict=True):
            for shot, original in zip(scene["shots"], source["shots"], strict=True):
                self.assertEqual(shot["dialogue"], "")
                self.assertEqual(shot["design"], original["design"])
                self.assertEqual(shot["audio_intent"], original["audio_intent"])
        self.assertLessEqual(
            len(json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
            PRODUCTION_STATE_MAX_BYTES,
        )

    def test_full_script_fits_under_the_ceiling(self):
        for source in (cinematic_sample, lambda: sample_project("dialogue")):
            state = build(source)
            size = len(json.dumps(state, ensure_ascii=False).encode("utf-8"))
            self.assertLessEqual(size, PRODUCTION_STATE_MAX_BYTES, source)

    def test_catalog_parameter_sets_preserve_every_template_parameter(self):
        catalog = fixture_catalog()
        packed = build(catalog=catalog)["movement_catalog"]
        for source, template in zip(catalog["templates"], packed["templates"], strict=True):
            self.assertEqual(packed["parameter_sets"][template["parameter_set"]], source["parameters"])

    def test_block_is_document_derived_and_carries_no_conversation(self):
        # A decision committed to the document survives any transcript compression,
        # because the block is regenerated from the document alone.
        state = build()
        movements = [
            shot["movement"]["template_id"]
            for scene in state["script"]["scenes"]
            for shot in scene["shots"]
            if shot.get("movement")
        ]
        self.assertIn("hero_orbit", movements)
        self.assertNotIn("transcript", state)
        self.assertEqual(
            state["recent_take_verdicts"], [{"take_id": "t", "score": 0.8, "reason": "sharp"}] * 3
        )
        self.assertEqual(len(state["marks"]), 2)

    def test_missing_script_is_explicit_not_invented(self):
        state = build(document=None, skill=None)
        self.assertEqual(state["script"], {"available": False, "reason": "no_script_yet"})
        self.assertIsNone(state["skill"])
        self.assertEqual(state["marks"], [])

    def test_oversize_state_fails_loudly(self):
        huge = fixture_catalog()
        huge["templates"] = huge["templates"] * 40
        with self.assertRaises(ValueError):
            build(catalog=huge)

    def test_cache_replays_identical_content_per_key(self):
        calls = []

        def builder():
            calls.append(1)
            return build()

        key = ("session", "digest", "provenance")
        first = cached_production_state(key, builder)
        second = cached_production_state(key, builder)
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)

    @unittest.skipUnless(SCIPY, "real movement catalog needs the simulation extra")
    def test_real_catalog_fits(self):
        state = build(catalog=None)
        self.assertTrue(state["movement_catalog"]["templates"])


class PersonaTests(unittest.TestCase):
    def test_all_filming_skills_fit_with_design_and_review_instructions(self):
        for skill in SKILLS.values():
            with self.subTest(skill=skill["name"]):
                persona = build_persona(skill)
                self.assertIn("Three levels of direction", persona)
                self.assertIn("Review the shot against its purpose", persona)
                self.assertLessEqual(len(persona.encode("utf-8")), PERSONA_MAX_BYTES)

    def test_persona_carries_prohibitions_skill_and_contract(self):
        skill = SKILLS["cinematic"]
        persona = build_persona(skill)
        for required in (
            "Never claim hardware readiness",
            "before the simulator has compiled it",
            "started by the operator",
            "you say nothing at all",
            "Never invent numbers",
            *skill["speaking_beats"],
        ):
            self.assertIn(required.lower(), persona.lower(), required)
        self.assertLessEqual(len(persona.encode("utf-8")), PERSONA_MAX_BYTES)

    def test_persona_without_a_skill_still_locks_the_contract(self):
        persona = build_persona(filming_skill_text="THE CONTRACT")
        self.assertIn("THE CONTRACT", persona)
        self.assertNotIn("Active skill", persona)

    def test_live_coaching_keeps_core_and_review_without_full_planner_examples(self):
        from takeone.director.studio import SKILL_PATH

        persona = build_persona(SKILLS["cinematic"])
        self.assertIn(SKILL_PATH.read_text(encoding="utf-8"), persona)
        self.assertIn(
            (SKILL_PATH.parent.parent / "rehearsal-review" / "SKILL.md").read_text(encoding="utf-8"),
            persona,
        )
        self.assertIn("hold A", persona)
        self.assertNotIn("The LEFT key's ease", persona)


if __name__ == "__main__":
    unittest.main()
