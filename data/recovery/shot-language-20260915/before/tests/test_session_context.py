"""Production state stays bounded and document-derived; the persona stays locked and honest."""

import importlib.util
import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
