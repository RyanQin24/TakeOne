"""Graph structure and content addressing — the property the render cache depends on."""

import unittest

from takeone.editor.errors import GraphError
from takeone.editor.graph import EditGraph, NodeType, RenderNode, TimeRange, address, node

from tests.editor.support import ROOT  # noqa: F401


def simple_graph():
    source = node(NodeType.SOURCE, 1, parameters={"path": "/a.mp4", "in_s": 0.0, "out_s": 2.0})
    trim = node(
        NodeType.TRANSFORM, 1, (source.node_id,), {"width": 640, "height": 360, "fps_num": 30, "fps_den": 1}
    )
    output = node(NodeType.OUTPUT, 1, (trim.node_id,), {"target": "preview"})
    return EditGraph((source, trim, output), output.node_id), source, trim, output


class ContentAddressing(unittest.TestCase):
    def test_identical_meaning_produces_an_identical_identity(self):
        first = node(NodeType.SOURCE, 1, parameters={"path": "/a.mp4", "proxy": True})
        second = node(NodeType.SOURCE, 1, parameters={"proxy": True, "path": "/a.mp4"})
        self.assertEqual(first.node_id, second.node_id)

    def test_a_changed_parameter_changes_the_identity(self):
        base = node(NodeType.EFFECT, 1, ("abc",), {"primitive": "contrast", "amount": 1.1})
        changed = node(NodeType.EFFECT, 1, ("abc",), {"primitive": "contrast", "amount": 1.2})
        self.assertNotEqual(base.node_id, changed.node_id)

    def test_a_changed_input_changes_the_identity(self):
        base = node(NodeType.EFFECT, 1, ("abc",), {"primitive": "contrast", "amount": 1.1})
        changed = node(NodeType.EFFECT, 1, ("abd",), {"primitive": "contrast", "amount": 1.1})
        self.assertNotEqual(base.node_id, changed.node_id)

    def test_a_version_bump_invalidates_the_cache_for_that_node(self):
        base = node(NodeType.EFFECT, 1, ("abc",), {"primitive": "vignette"})
        bumped = node(NodeType.EFFECT, 2, ("abc",), {"primitive": "vignette"})
        self.assertNotEqual(base.node_id, bumped.node_id)

    def test_float_formatting_cannot_split_an_identity(self):
        first = node(NodeType.EFFECT, 1, ("abc",), {"primitive": "contrast", "amount": 1.1000000001})
        second = node(NodeType.EFFECT, 1, ("abc",), {"primitive": "contrast", "amount": 1.1})
        self.assertEqual(first.node_id, second.node_id)

    def test_a_hand_edited_identity_is_rejected(self):
        source = node(NodeType.SOURCE, 1, parameters={"path": "/a.mp4"})
        with self.assertRaises(GraphError):
            RenderNode(
                node_id="0123456789abcdef",
                type=NodeType.SOURCE,
                version=1,
                inputs=(),
                parameters={"path": "/b.mp4"},
            )
        self.assertEqual(source.node_id, address(NodeType.SOURCE, 1, (), {"path": "/a.mp4"}))

    def test_time_range_participates_in_the_identity(self):
        without = node(NodeType.EFFECT, 1, ("abc",), {"primitive": "glow"})
        within = node(NodeType.EFFECT, 1, ("abc",), {"primitive": "glow"}, TimeRange(0.0, 1.0))
        self.assertNotEqual(without.node_id, within.node_id)


class Structure(unittest.TestCase):
    def test_topological_order_respects_dependencies(self):
        graph, source, trim, output = simple_graph()
        order = [item.node_id for item in graph.topological()]
        self.assertLess(order.index(source.node_id), order.index(trim.node_id))
        self.assertLess(order.index(trim.node_id), order.index(output.node_id))

    def test_a_cycle_is_an_error(self):
        left = node(NodeType.EFFECT, 1, ("right",), {"primitive": "glow"})
        right = node(NodeType.EFFECT, 1, (left.node_id,), {"primitive": "glow"})
        cyclic = node(NodeType.EFFECT, 1, (right.node_id,), {"primitive": "glow"})
        rebuilt_left = RenderNode(
            node_id=left.node_id,
            type=NodeType.EFFECT,
            version=1,
            inputs=("right",),
            parameters={"primitive": "glow"},
        )
        output = node(NodeType.OUTPUT, 1, (cyclic.node_id,), {"target": "preview"})
        with self.assertRaises(GraphError):
            EditGraph((rebuilt_left, right, cyclic, output), output.node_id)

    def test_a_missing_input_is_an_error(self):
        orphan = node(NodeType.EFFECT, 1, ("does-not-exist",), {"primitive": "glow"})
        output = node(NodeType.OUTPUT, 1, (orphan.node_id,), {"target": "preview"})
        with self.assertRaises(GraphError):
            EditGraph((orphan, output), output.node_id)

    def test_exactly_one_output_is_required(self):
        graph, source, trim, output = simple_graph()
        second = node(NodeType.OUTPUT, 1, (trim.node_id,), {"target": "master"})
        with self.assertRaises(GraphError):
            EditGraph(graph.nodes + (second,), output.node_id)

    def test_unreachable_nodes_are_rejected(self):
        graph, source, trim, output = simple_graph()
        stray = node(NodeType.EFFECT, 1, (source.node_id,), {"primitive": "glow"})
        with self.assertRaises(GraphError):
            EditGraph(graph.nodes + (stray,), output.node_id)

    def test_arity_is_enforced_per_node_type(self):
        with self.assertRaises(GraphError):
            node(NodeType.TRANSITION, 1, ("only-one",), {"mode": "fade"})
        with self.assertRaises(GraphError):
            node(NodeType.TRANSFORM, 1, (), {"width": 8})

    def test_non_finite_parameters_are_rejected(self):
        with self.assertRaises(GraphError):
            node(NodeType.EFFECT, 1, ("abc",), {"primitive": "glow", "radius": float("inf")})

    def test_ancestors_returns_only_what_a_node_depends_on(self):
        graph, source, trim, output = simple_graph()
        self.assertEqual(
            [item.node_id for item in graph.ancestors(trim.node_id)],
            [source.node_id, trim.node_id],
        )


if __name__ == "__main__":
    unittest.main()
