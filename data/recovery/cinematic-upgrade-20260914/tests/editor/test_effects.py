"""The effect registry, parameter validation and composite compilation."""

import unittest

from takeone.editor.effects import EFFECTS
from takeone.editor.effects.primitives import PRIMITIVES
from takeone.editor.errors import ValidationError
from takeone.editor.graph import NodeType
from takeone.editor.render.ffmpeg import MULTI_STAGE, PRIMITIVE_FILTERS, SAFE_FILTER

from tests.editor.support import ROOT  # noqa: F401


class Registry(unittest.TestCase):
    def test_every_primitive_has_a_backend_compilation(self):
        missing = [spec.id for spec in PRIMITIVES if spec.id not in PRIMITIVE_FILTERS]
        self.assertEqual(missing, [], f"primitives with no FFmpeg fragment: {missing}")

    def test_no_orphan_backend_compilations(self):
        known = {spec.id for spec in PRIMITIVES}
        extra = sorted(set(PRIMITIVE_FILTERS) - known)
        self.assertEqual(extra, [], f"fragments with no registered primitive: {extra}")

    def test_registering_a_duplicate_is_refused(self):
        with self.assertRaises(ValidationError):
            EFFECTS.register(EFFECTS.latest("vignette"))

    def test_an_unknown_effect_names_the_installed_versions(self):
        with self.assertRaises(ValidationError) as caught:
            EFFECTS.get("vignette", 7)
        self.assertIn("installed versions", str(caught.exception))

    def test_the_catalog_is_serialisable(self):
        catalog = EFFECTS.catalog()
        self.assertTrue(all("parameters" in entry for entry in catalog))
        self.assertEqual(len(catalog), len(EFFECTS.entries))


class Validation(unittest.TestCase):
    def test_unknown_parameters_are_rejected(self):
        with self.assertRaises(ValidationError):
            EFFECTS.latest("vignette").validate({"strength": 0.5})

    def test_out_of_range_parameters_are_rejected(self):
        with self.assertRaises(ValidationError):
            EFFECTS.latest("pixelate").validate({"size": 9999})

    def test_defaults_are_filled(self):
        values = EFFECTS.latest("bloom").validate({})
        self.assertEqual(set(values), {"threshold", "radius", "intensity"})

    def test_a_required_parameter_with_no_default_is_demanded(self):
        with self.assertRaises(ValidationError):
            EFFECTS.latest("lut3d").validate({})


class Compilation(unittest.TestCase):
    def test_a_primitive_compiles_to_exactly_one_node(self):
        nodes, output = EFFECTS.latest("vignette").build(("in",), {"intensity": 0.4})
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].node_id, output)
        self.assertIs(nodes[0].type, NodeType.EFFECT)

    def test_a_look_compiles_to_a_chain_of_primitives(self):
        nodes, output = EFFECTS.latest("luxury_warm").build(("in",), {"intensity": 0.7})
        self.assertGreater(len(nodes), 3)
        self.assertEqual(nodes[-1].node_id, output)
        for item in nodes:
            self.assertIn(item.parameters["primitive"], PRIMITIVE_FILTERS)
        self.assertEqual(nodes[0].inputs, ("in",))
        for previous, current in zip(nodes, nodes[1:]):
            self.assertEqual(current.inputs, (previous.node_id,))

    def test_look_intensity_changes_every_downstream_identity(self):
        low, _ = EFFECTS.latest("luxury_warm").build(("in",), {"intensity": 0.3})
        high, _ = EFFECTS.latest("luxury_warm").build(("in",), {"intensity": 0.9})
        self.assertNotEqual([n.node_id for n in low], [n.node_id for n in high])

    def test_zero_intensity_still_compiles_to_a_valid_chain(self):
        nodes, _ = EFFECTS.latest("noir_contrast").build(("in",), {"intensity": 0.0})
        self.assertTrue(nodes)

    def test_new_looks_compile_to_registered_primitives(self):
        for look in ("golden_hour", "vintage", "vhs_tape", "cyberpunk", "high_key"):
            nodes, _ = EFFECTS.latest(look).build(("in",), {"intensity": 0.6})
            self.assertGreater(len(nodes), 1, look)
            for item in nodes:
                self.assertIn(item.parameters["primitive"], PRIMITIVE_FILTERS)

    def test_default_fragments_stay_inside_the_allowlist(self):
        for spec in PRIMITIVES:
            if any(item.required and item.default is None for item in spec.parameters):
                continue
            values = spec.validate({})
            handler = PRIMITIVE_FILTERS[spec.id]
            fragment = (
                handler(values, ["[0]"], "[out]", "t")
                if spec.id in MULTI_STAGE
                else handler(values, ["[0]"], "[out]")
            )
            self.assertTrue(SAFE_FILTER.match(fragment), f"{spec.id}: {fragment}")

    def test_a_transition_takes_two_inputs(self):
        nodes, _ = EFFECTS.latest("crossfade").build(("a", "b"), {"duration_s": 0.5, "offset_s": 2.0})
        self.assertIs(nodes[0].type, NodeType.TRANSITION)
        self.assertEqual(nodes[0].inputs, ("a", "b"))

    def test_a_transition_refuses_one_input(self):
        with self.assertRaises(ValidationError):
            EFFECTS.latest("crossfade").build(("a",), {"duration_s": 0.5})


if __name__ == "__main__":
    unittest.main()
