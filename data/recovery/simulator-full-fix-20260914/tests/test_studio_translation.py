"""The drift guard: the catalog, the schema sent to the model, and the translator agree.

If these three ever disagree, the model can write a shot the simulator refuses. The
simulator half is already covered by test_movement_library; this closes the director half.
"""

import math
import unittest

from takeone.director.creative import plan_schema, repair_schema, validate
from takeone.director.studio import MovementError, movement_catalog, movement_schema, shot_diagnostic, shot_settings
from takeone.previs.templates import BY_ID, FIELDS, catalog


def shot(template_id, parameters, start_ms=0, end_ms=8000, motion="hold"):
    return dict(
        shot_id="s1",
        start_ms=start_ms,
        end_ms=end_ms,
        framing="medium",
        movement=dict(
            template_id=template_id,
            subject_motion=motion,
            parameters=[dict(name=n, value=v) for n, v in parameters.items()],
        ),
    )


class CatalogAgreementTests(unittest.TestCase):
    def test_the_schema_enumerates_exactly_the_templates_the_simulator_has(self):
        schema = movement_schema()
        ids = set(schema["properties"]["template_id"]["enum"]) - {"unresolved"}
        self.assertEqual(ids, set(BY_ID))
        names = set(schema["properties"]["parameters"]["items"]["properties"]["name"]["enum"])
        self.assertEqual(names, set(FIELDS) | {"focal_mm"})

    def test_every_template_round_trips_its_own_defaults(self):
        for entry in catalog()["templates"]:
            defaults = entry["defaults"]
            values = {name: defaults[name] for name in entry["parameters"]}
            values["focal_mm"] = defaults["focal_mm"]
            duration = 8000
            if BY_ID[entry["id"]]["route"] == "hold":
                values.pop("duration_s", None)
                duration = int(defaults["duration_s"] * 1000)
            candidate = shot(entry["id"], values, end_ms=duration, motion=defaults["subject_motion"])
            validate(candidate["movement"], movement_schema(), "movement")
            settings, defaulted = shot_settings(candidate)
            with self.subTest(template=entry["id"]):
                self.assertEqual(settings["template_id"], entry["id"])
                for name, value in values.items():
                    self.assertAlmostEqual(settings[name], value, places=9, msg=name)
                self.assertNotIn(name, defaulted)

    def test_the_catalog_the_model_sees_states_the_same_bounds_the_translator_enforces(self):
        served = movement_catalog()["fields"]
        self.assertEqual(set(served), set(FIELDS))
        for name, field in FIELDS.items():
            self.assertAlmostEqual(served[name]["minimum"], field["min"] / field["scale"], places=9)
            self.assertAlmostEqual(served[name]["maximum"], field["max"] / field["scale"], places=9)

    def test_a_new_proposal_must_place_its_marks_but_an_old_script_need_not(self):
        strict = plan_schema(require_movement=True)["properties"]["marks"]["items"]
        lenient = plan_schema(require_movement=False)["properties"]["marks"]["items"]
        accepting = plan_schema(require_movement=True, require_marks=False)["properties"]["marks"]["items"]
        self.assertEqual(set(accepting["required"]), {"mark_id", "description"})
        self.assertEqual(set(strict["required"]), {"mark_id", "description", "position_m", "facing_rad"})
        self.assertEqual(set(lenient["required"]), {"mark_id", "description"})

    def test_a_repair_may_only_return_movement_objects(self):
        item = repair_schema()["properties"]["repairs"]["items"]
        self.assertEqual(set(item["properties"]), {"shot_id", "explanation", "movement"})
        self.assertEqual(item["properties"]["movement"], movement_schema())


class RefusalTests(unittest.TestCase):
    def refusal(self, candidate):
        with self.assertRaises(MovementError) as caught:
            shot_settings(candidate)
        return caught.exception

    def test_an_out_of_range_value_names_the_field_and_what_the_rig_accepts(self):
        error = self.refusal(shot("push_in", {"speed_m_s": 0.8}))
        self.assertEqual(error.code, "out_of_range")
        self.assertEqual(error.parameter, "speed_m_s")
        self.assertEqual(error.observed, 0.8)
        self.assertEqual(error.allowed, (0.14, 0.35))

    def test_a_parameter_the_template_does_not_use_names_the_ones_it_does(self):
        error = self.refusal(shot("push_in", {"sweep_rad": math.pi / 2}))
        self.assertEqual(error.code, "unknown_parameter")
        self.assertEqual(error.parameter, "sweep_rad")
        self.assertIn("distance_m", error.suggestion)

    def test_an_unresolved_movement_is_reported_as_such(self):
        error = self.refusal(shot("unresolved", {}))
        self.assertEqual(error.code, "unresolved_movement")

    def test_a_refusal_becomes_a_blocking_diagnostic_and_a_good_shot_becomes_none(self):
        blocked = shot_diagnostic(shot("push_in", {"speed_m_s": 9.0}))
        self.assertTrue(blocked.blocking)
        self.assertEqual(blocked.parameter, "speed_m_s")
        self.assertIsNone(shot_diagnostic(shot("push_in", {"speed_m_s": 0.3})))

    def test_the_bounds_checked_early_are_the_bounds_the_compiler_enforces(self):
        for name, field in FIELDS.items():
            low, high = field["min"] / field["scale"], field["max"] / field["scale"]
            template = next(e["id"] for e in catalog()["templates"] if name in e["parameters"])
            with self.subTest(parameter=name):
                self.refusal(shot(template, {name: low - abs(low) * 0.5 - 1}))
                self.refusal(shot(template, {name: high + abs(high) * 0.5 + 1}))


if __name__ == "__main__":
    unittest.main()
