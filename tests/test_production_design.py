"""AI Production Designer contracts, retrieval and deterministic layout. No device IO."""

import unittest

from takeone.asset_library.catalog import AssetCatalog
from takeone.director.production_design import (
    AssetRequirement,
    ProductionDesignRequest,
    design_world,
    production_design_status,
    search_assets,
)
from takeone.director.production_design.layout_solver import solve_layout
from takeone.director.production_design.scene_graph import build_scene_graph


def asset(index, name, pack="test", tags=None, dimensions=None):
    return {
        "asset_id": f"lib:test:{index}:0123456789abcdef",
        "name": name,
        "pack_id": pack,
        "kind": "prop",
        "tags": tags or [],
        "dimensions_m": dimensions,
        "sha256": str(index),
    }


def fake_catalog():
    values = [
        asset("desk", "desk", "furniture", ["interior"], [1.4, 0.7, 0.75]),
        asset("chair", "chair", "furniture", ["interior"], [0.55, 0.55, 0.9]),
        asset("lamp", "lamp Round Floor", "furniture", ["interior"], [0.35, 0.35, 1.5]),
        asset("screen", "computer Screen", "furniture", ["technology"], [0.5, 0.2, 0.35]),
        asset("tree", "tree oak", "nature", ["outdoor"], [1.2, 1.2, 3.0]),
        asset("plant", "potted Plant", "furniture", ["interior"], [0.5, 0.5, 0.9]),
        asset("rock", "rock large A", "nature", ["outdoor"], [1.0, 0.9, 0.7]),
        asset("path", "ground path Straight", "nature", ["outdoor"], [2.0, 1.0, 0.08]),
        asset("bottle", "bottle", "food", ["product"], [0.18, 0.18, 0.3]),
        asset("door", "doorway Open", "furniture", ["architecture"], [1.0, 0.2, 2.2]),
        asset("shelf", "bookcase Open", "furniture", ["storage"], [1.0, 0.4, 1.8]),
    ]
    return AssetCatalog({"schema_version": 1, "assets": values})


class RetrievalTests(unittest.TestCase):
    def test_search_uses_semantics_not_catalog_order(self):
        catalog = fake_catalog()
        result = search_assets(
            AssetRequirement.parse(
                {
                    "role_id": "light",
                    "query": "floor lamp",
                    "purpose": "practical",
                    "categories": ["lighting"],
                    "required": True,
                }
            ),
            catalog=catalog,
        )
        self.assertEqual(result[0]["asset_id"], "lib:test:lamp:0123456789abcdef")

    def test_workspace_query_prefers_desk_and_technology_candidates(self):
        catalog = fake_catalog()
        desk = search_assets(
            {
                "role_id": "surface",
                "query": "desk workbench table",
                "purpose": "work surface",
                "categories": ["surface"],
                "required": True,
            },
            catalog=catalog,
        )
        self.assertEqual(desk[0]["asset_id"], "lib:test:desk:0123456789abcdef")

    def test_project_catalog_is_full_and_semantic_searches_are_useful(self):
        status = production_design_status()
        self.assertGreaterEqual(status["catalog"]["installed_count"], 600)
        for query, category in (
            ("floor lamp", "lighting"),
            ("workstation desk", "surface"),
            ("forest tree", "vegetation"),
        ):
            with self.subTest(query=query):
                result = search_assets(
                    {
                        "role_id": "search",
                        "query": query,
                        "purpose": "test",
                        "categories": [category],
                        "required": False,
                    }
                )
                self.assertTrue(result)
                self.assertIn(category, result[0]["categories"])


class ContractTests(unittest.TestCase):
    def test_unknown_relation_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Unknown scene relation"):
            ProductionDesignRequest.parse(
                {
                    "intent": {"environment": "room", "mood": "quiet"},
                    "requirements": [{"role_id": "desk", "query": "desk", "purpose": "surface"}],
                    "relations": [{"kind": "teleport_near", "source": "desk"}],
                }
            )

    def test_relation_cannot_reference_missing_role(self):
        with self.assertRaisesRegex(ValueError, "unknown target"):
            ProductionDesignRequest.parse(
                {
                    "intent": {"environment": "room", "mood": "quiet"},
                    "requirements": [{"role_id": "desk", "query": "desk", "purpose": "surface"}],
                    "relations": [{"kind": "near", "source": "desk", "target": "ghost"}],
                }
            )


class LayoutTests(unittest.TestCase):
    def structured_request(self):
        return {
            "intent": {
                "environment": "late night workspace",
                "mood": "night",
                "camera_needs": ["foreground_reveal"],
                "mode": "pure_previs",
            },
            "requirements": [
                {
                    "role_id": "surface",
                    "query": "desk",
                    "purpose": "story surface",
                    "categories": ["surface"],
                },
                {
                    "role_id": "technology",
                    "query": "computer screen",
                    "purpose": "hero prop",
                    "categories": ["technology"],
                },
                {
                    "role_id": "lamp",
                    "query": "floor lamp",
                    "purpose": "practical",
                    "categories": ["lighting"],
                },
                {
                    "role_id": "foreground",
                    "query": "plant",
                    "purpose": "reveal",
                    "categories": ["vegetation"],
                    "max_width_m": 0.8,
                },
            ],
            "relations": [
                {"kind": "on_top_of", "source": "technology", "target": "surface"},
                {"kind": "near", "source": "lamp", "target": "surface", "maximum_m": 1.8},
                {"kind": "foreground_of", "source": "foreground", "target": "surface", "minimum_m": 0.8},
            ],
            "routes": [{"route_id": "actor", "points_m": [[0, -3], [0, 2]], "clearance_m": 0.4}],
            "bounds_m": [8, 8],
            "seed": 17,
        }

    def test_same_graph_and_seed_are_bitwise_deterministic(self):
        catalog = fake_catalog()
        one = design_world({"request": self.structured_request()}, catalog=catalog)
        two = design_world({"request": self.structured_request()}, catalog=catalog)
        self.assertEqual(one["layout"]["layout_digest"], two["layout"]["layout_digest"])
        self.assertEqual(one["layout"]["scene"], two["layout"]["scene"])

    def test_on_top_of_uses_same_xy_and_vertical_surface(self):
        catalog = fake_catalog()
        result = design_world({"request": self.structured_request()}, catalog=catalog)
        objects = {item["production_role"]: item for item in result["layout"]["scene"]["objects"]}
        self.assertEqual(objects["technology"]["position_m"][:2], objects["surface"]["position_m"][:2])
        desk_top = objects["surface"]["position_m"][2] + objects["surface"]["size_m"][2] / 2
        screen_bottom = objects["technology"]["position_m"][2] - objects["technology"]["size_m"][2] / 2
        self.assertAlmostEqual(desk_top, screen_bottom, places=6)

    def test_route_clearance_is_reported_and_passes(self):
        result = design_world({"request": self.structured_request()}, catalog=fake_catalog())
        route = result["layout"]["evidence"]["routes"][0]
        self.assertTrue(route["passes"], route)
        self.assertGreaterEqual(route["minimum_clearance_m"], route["required_clearance_m"])

    def test_different_briefs_create_different_semantic_worlds_without_scene_templates(self):
        catalog = fake_catalog()
        workspace = design_world(
            {
                "brief": "cinematic late-night hacker workspace with a robot prototype and foreground reveal",
                "seed": 3,
            },
            catalog=catalog,
        )
        forest = design_world(
            {
                "brief": "quiet sunset walk through a forest path with rocks",
                "seed": 3,
            },
            catalog=catalog,
        )
        self.assertNotEqual(
            workspace["graph_summary"]["categories"],
            forest["graph_summary"]["categories"],
        )
        self.assertNotEqual(
            workspace["graph_summary"]["asset_ids"],
            forest["graph_summary"]["asset_ids"],
        )

    def test_solver_reports_evidence_boundary(self):
        graph = build_scene_graph(
            ProductionDesignRequest.parse(self.structured_request()),
            catalog=fake_catalog(),
        )
        result = solve_layout(graph)
        self.assertIn("not physical safety", result["evidence"]["evidence_boundary"])
        self.assertIn(result["evidence"]["status"], ("solver_verified", "needs_revision"))


if __name__ == "__main__":
    unittest.main()


class ProviderProductionDesignTests(unittest.TestCase):
    def test_provider_asks_for_semantics_and_keeps_fixed_asset_ids_local(self):
        import json

        from takeone.director.production_design.contracts import RELATION_KINDS
        from takeone.director.provider import PRODUCTION_DESIGN_INSTRUCTIONS, ResponsesPlanner

        planner = ResponsesPlanner(api_key="")
        payload = {
            "brief": {"title": "World", "objective": "Design a workspace"},
            "context": {"skill_id": "cinematic", "audience": "judges", "tone": "tense"},
            "skill": {"version": 1},
            "scene": {
                "scene_id": "scene-1",
                "title": "Workspace",
                "location": "room",
                "location_notes": "",
                "atmosphere": "interior_day",
                "shot_needs": [],
            },
            "instruction": "Create depth and a tracking lane.",
            "mode": "pure_previs",
            "seed": 4,
            "relation_vocabulary": list(RELATION_KINDS),
            "anchors": [
                {
                    "object_id": "hero",
                    "label": "Hero prop",
                    "availability": "present",
                    "size_m": [0.3, 0.3, 0.3],
                }
            ],
            "fixed_objects": [
                {
                    "object_id": "hero",
                    "asset_id": "lib:private-local-id",
                    "availability": "present",
                    "label": "Hero prop",
                    "position_m": [0, 0, 0.15],
                    "size_m": [0.3, 0.3, 0.3],
                    "yaw_rad": 0,
                }
            ],
        }
        raw, reserved = planner.request(payload, "production_design")
        body = json.loads(raw)
        sent = json.loads(body["input"])
        self.assertGreater(reserved, 0)
        self.assertEqual(body["instructions"], PRODUCTION_DESIGN_INSTRUCTIONS)
        self.assertEqual(body["text"]["format"]["name"], "takeone_production_design_v1")
        self.assertNotIn("fixed_objects", sent)
        self.assertNotIn("lib:private-local-id", raw.decode())
        self.assertEqual(sent["anchors"][0]["object_id"], "hero")


class FixedAnchorTests(unittest.TestCase):
    def test_existing_story_target_keeps_identity_and_exact_transform(self):
        request = {
            "intent": {"environment": "product room", "mood": "neutral", "mode": "pure_previs"},
            "requirements": [
                {
                    "role_id": "surface",
                    "query": "desk",
                    "purpose": "supporting set dressing",
                    "categories": ["surface"],
                    "required": True,
                }
            ],
            "relations": [],
            "routes": [],
            "bounds_m": [8, 8],
            "seed": 9,
        }
        anchor = {
            "object_id": "hero-product",
            "asset_id": "product",
            "availability": "present",
            "label": "Real hero object",
            "position_m": [0.75, 0.5, 0.45],
            "size_m": [0.3, 0.3, 0.9],
            "yaw_rad": 0.4,
        }
        result = design_world({"request": request, "fixed_objects": [anchor]})
        by_id = {item["object_id"]: item for item in result["layout"]["scene"]["objects"]}
        self.assertIn("hero-product", by_id)
        self.assertEqual(by_id["hero-product"]["position_m"], anchor["position_m"])
        self.assertEqual(by_id["hero-product"]["yaw_rad"], anchor["yaw_rad"])
        self.assertEqual(by_id["hero-product"]["availability"], "present")
        self.assertTrue(result["layout"]["evidence"]["valid"], result["layout"]["evidence"])

    def test_fixed_anchor_roles_distinguish_long_and_sanitization_colliding_ids(self):
        hashed_role = "fixed_~20df008a27af6dee"
        request = {
            "intent": {"environment": "product room", "mood": "neutral", "mode": "physical_reconstruction"},
            "requirements": [
                {
                    "role_id": "surface",
                    "query": "desk",
                    "purpose": "supporting set dressing",
                    "categories": ["surface"],
                    "required": True,
                }
            ],
            "relations": [
                {
                    "kind": "near",
                    "source": "surface",
                    "target": hashed_role,
                    "maximum_m": 10.0,
                }
            ],
            "routes": [],
            "bounds_m": [12, 12],
            "seed": 9,
        }
        anchor_ids = [
            "a" * 34 + "1",
            "a" * 34 + "2",
            "hero object",
            "hero@object",
            "heroobject_20df008a27af6dee",
            "digest_heroobject_20df008a27af6dee",
            "digest_hero",
        ]
        anchors = [
            {
                "object_id": object_id,
                "asset_id": "product",
                "availability": "present",
                "label": f"Anchor {index}",
                "position_m": [-4.0 + index * 2.0, 0.0, 0.45],
                "size_m": [0.3, 0.3, 0.9],
                "yaw_rad": 0.4,
            }
            for index, object_id in enumerate(anchor_ids)
        ]

        result = design_world({"request": request, "fixed_objects": anchors}, catalog=fake_catalog())

        self.assertEqual(
            {item["object_id"] for item in result["layout"]["scene"]["objects"]},
            set(anchor_ids) | {"pd-surface"},
        )
        fixed_roles = [node["node_id"] for node in result["graph"]["nodes"] if "object_id" in node]
        self.assertEqual(len(fixed_roles), len(set(fixed_roles)))
        self.assertIn("fixed_digest_hero", fixed_roles)
        self.assertIn(hashed_role, fixed_roles)
        self.assertEqual(result["layout"]["evidence"]["relations"][0]["target"], hashed_role)


class ShotFeasibilityTests(unittest.TestCase):
    def test_compiled_moving_shots_contribute_cart_and_actor_routes(self):
        from takeone.director.production_design.feasibility import derive_scene_routes
        from takeone.director.skills import sample_project

        document = sample_project("cinematic")["document"]
        routes = derive_scene_routes(document, "scene-1")
        ids = {route.route_id for route in routes}
        self.assertTrue(any(value.startswith("cart-") for value in ids), ids)
        self.assertTrue(any(value.startswith("actor-") for value in ids), ids)
        self.assertTrue(all(2 <= len(route.points_m) <= 16 for route in routes))
        self.assertTrue(all(route.clearance_m >= 0.45 for route in routes))

    def test_generated_dressing_can_relate_to_a_preserved_anchor(self):
        from takeone.director.production_design.scene_graph import fixed_role_id

        anchor = {
            "object_id": "hero-product",
            "asset_id": "product",
            "availability": "present",
            "label": "Real hero object",
            "position_m": [0.75, 0.5, 0.45],
            "size_m": [0.3, 0.3, 0.9],
            "yaw_rad": 0.4,
        }
        role = fixed_role_id(anchor["object_id"])
        request = {
            "intent": {"environment": "product room", "mood": "neutral", "mode": "pure_previs"},
            "requirements": [
                {
                    "role_id": "practical",
                    "query": "floor lamp",
                    "purpose": "motivated edge source",
                    "categories": ["lighting"],
                    "required": True,
                }
            ],
            "relations": [
                {
                    "kind": "near",
                    "source": "practical",
                    "target": role,
                    "maximum_m": 1.8,
                }
            ],
            "routes": [],
            "bounds_m": [8, 8],
            "seed": 13,
        }
        result = design_world({"request": request, "fixed_objects": [anchor]})
        relation = result["layout"]["evidence"]["relations"][0]
        self.assertEqual(relation["target"], role)
        self.assertTrue(relation["passes"], relation)
