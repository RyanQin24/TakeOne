"""Validated semantic contracts for TakeOne production design.

These values describe creative relationships, not hardware commands. Exact world
coordinates are produced later by the deterministic layout solver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SCENE_MODES = ("physical_reconstruction", "proposed_dressing", "pure_previs")
RELATION_KINDS = (
    "near", "far_from", "left_of", "right_of", "in_front_of", "behind",
    "on_top_of", "under", "against_wall", "facing", "facing_toward",
    "aligned_with", "between", "foreground_of", "background_of",
    "visible_from", "occludes_initially", "must_clear", "route_clear_of",
    "camera_targetable", "motivates_light",
)


def _text(value, label, maximum=240):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be 1 to {maximum} characters")
    return value.strip()


def _strings(value, label, maximum=12):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label} must be a list of at most {maximum} strings")
    result = []
    for item in value:
        item = _text(item, label, 160)
        if item not in result:
            result.append(item)
    return tuple(result)


def _finite(value, label, low=None, high=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    value = float(value)
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(f"{label} is outside its accepted range")
    return value


@dataclass(frozen=True)
class SceneIntent:
    environment: str
    mood: str
    story_functions: tuple[str, ...] = ()
    visual_needs: tuple[str, ...] = ()
    camera_needs: tuple[str, ...] = ()
    actor_needs: tuple[str, ...] = ()
    mode: str = "pure_previs"

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Scene intent must be an object")
        allowed = {"environment", "mood", "story_functions", "visual_needs",
                   "camera_needs", "actor_needs", "mode"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown scene intent fields: {sorted(unknown)}")
        mode = value.get("mode", "pure_previs")
        if mode not in SCENE_MODES:
            raise ValueError("Unknown scene truth mode")
        return cls(
            environment=_text(value.get("environment", ""), "Environment", 200),
            mood=_text(value.get("mood", "neutral"), "Mood", 160),
            story_functions=_strings(value.get("story_functions", []), "Story function"),
            visual_needs=_strings(value.get("visual_needs", []), "Visual need"),
            camera_needs=_strings(value.get("camera_needs", []), "Camera need"),
            actor_needs=_strings(value.get("actor_needs", []), "Actor need"),
            mode=mode,
        )

    def wire(self):
        return {
            "environment": self.environment,
            "mood": self.mood,
            "story_functions": list(self.story_functions),
            "visual_needs": list(self.visual_needs),
            "camera_needs": list(self.camera_needs),
            "actor_needs": list(self.actor_needs),
            "mode": self.mode,
        }


@dataclass(frozen=True)
class AssetRequirement:
    role_id: str
    query: str
    purpose: str
    categories: tuple[str, ...] = ()
    required: bool = True
    max_width_m: float | None = None
    max_depth_m: float | None = None
    max_height_m: float | None = None

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Asset requirement must be an object")
        allowed = {"role_id", "query", "purpose", "categories", "required",
                   "max_width_m", "max_depth_m", "max_height_m"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown asset requirement fields: {sorted(unknown)}")
        role = _text(value.get("role_id", ""), "Role ID", 40)
        if not role.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Role ID must use letters, numbers, dashes or underscores")
        required = value.get("required", True)
        if type(required) is not bool:
            raise ValueError("required must be true or false")
        dims = {}
        for key in ("max_width_m", "max_depth_m", "max_height_m"):
            raw = value.get(key)
            dims[key] = None if raw is None else _finite(raw, key, 0.02, 30)
        return cls(
            role_id=role,
            query=_text(value.get("query", ""), "Asset query", 200),
            purpose=_text(value.get("purpose", ""), "Asset purpose", 300),
            categories=_strings(value.get("categories", []), "Asset category", 8),
            required=required,
            **dims,
        )

    def wire(self):
        result = {
            "role_id": self.role_id,
            "query": self.query,
            "purpose": self.purpose,
            "categories": list(self.categories),
            "required": self.required,
        }
        for key in ("max_width_m", "max_depth_m", "max_height_m"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result


@dataclass(frozen=True)
class Relation:
    kind: str
    source: str
    target: str | None = None
    minimum_m: float | None = None
    maximum_m: float | None = None
    weight: float = 1.0

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Scene relation must be an object")
        allowed = {"kind", "source", "target", "minimum_m", "maximum_m", "weight"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown relation fields: {sorted(unknown)}")
        kind = value.get("kind")
        if kind not in RELATION_KINDS:
            raise ValueError(f"Unknown scene relation: {kind}")
        source = _text(value.get("source", ""), "Relation source", 40)
        target = value.get("target")
        target = None if target in (None, "") else _text(target, "Relation target", 40)
        if target == source:
            raise ValueError("A relation cannot target itself")
        minimum = value.get("minimum_m")
        maximum = value.get("maximum_m")
        minimum = None if minimum is None else _finite(minimum, "minimum_m", 0, 30)
        maximum = None if maximum is None else _finite(maximum, "maximum_m", 0, 30)
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("Relation minimum cannot exceed maximum")
        return cls(
            kind=kind,
            source=source,
            target=target,
            minimum_m=minimum,
            maximum_m=maximum,
            weight=_finite(value.get("weight", 1.0), "Relation weight", 0.01, 100),
        )

    def wire(self):
        result = {"kind": self.kind, "source": self.source, "weight": self.weight}
        if self.target is not None:
            result["target"] = self.target
        if self.minimum_m is not None:
            result["minimum_m"] = self.minimum_m
        if self.maximum_m is not None:
            result["maximum_m"] = self.maximum_m
        return result


@dataclass(frozen=True)
class RouteConstraint:
    route_id: str
    points_m: tuple[tuple[float, float], ...]
    clearance_m: float

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Route constraint must be an object")
        allowed = {"route_id", "points_m", "clearance_m"}
        if set(value) - allowed:
            raise ValueError("Unknown route constraint fields")
        raw_points = value.get("points_m")
        if not isinstance(raw_points, list) or not 2 <= len(raw_points) <= 32:
            raise ValueError("Route needs 2 to 32 floor points")
        points = []
        for point in raw_points:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("Route points are [x,y] metres")
            points.append((_finite(point[0], "Route X", -100, 100),
                           _finite(point[1], "Route Y", -100, 100)))
        return cls(
            route_id=_text(value.get("route_id", ""), "Route ID", 40),
            points_m=tuple(points),
            clearance_m=_finite(value.get("clearance_m", 0.5), "Route clearance", 0.05, 5),
        )
    def wire(self):
        return {
            "route_id": self.route_id,
            "points_m": [list(point) for point in self.points_m],
            "clearance_m": self.clearance_m,
        }


@dataclass(frozen=True)
class ProductionDesignRequest:
    intent: SceneIntent
    requirements: tuple[AssetRequirement, ...]
    relations: tuple[Relation, ...] = ()
    routes: tuple[RouteConstraint, ...] = ()
    bounds_m: tuple[float, float] = (8.0, 8.0)
    seed: int = 1

    @classmethod
    def parse(cls, value, *, external_roles=()):
        if not isinstance(value, dict):
            raise ValueError("Production design request must be an object")
        allowed = {"intent", "requirements", "relations", "routes", "bounds_m", "seed"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown production design fields: {sorted(unknown)}")
        requirements = tuple(AssetRequirement.parse(v) for v in value.get("requirements", []))
        if not requirements or len(requirements) > 24:
            raise ValueError("Production design needs 1 to 24 asset requirements")
        roles = [item.role_id for item in requirements]
        if len(roles) != len(set(roles)):
            raise ValueError("Asset requirement role IDs must be unique")
        external = tuple(_text(role, "External scene role", 40) for role in external_roles)
        if len(external) != len(set(external)) or set(external) & set(roles):
            raise ValueError("External scene roles must be unique and distinct from generated roles")
        allowed_roles = set(roles) | set(external)
        relations = tuple(Relation.parse(v) for v in value.get("relations", []))
        for relation in relations:
            if relation.source not in allowed_roles:
                raise ValueError(f"Relation references unknown source role: {relation.source}")
            if relation.target and relation.target not in allowed_roles:
                raise ValueError(f"Relation references unknown target role: {relation.target}")
        routes = tuple(RouteConstraint.parse(v) for v in value.get("routes", []))
        bounds = value.get("bounds_m", [8.0, 8.0])
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("bounds_m must be [width, depth]")
        bounds_m = (_finite(bounds[0], "Scene width", 2, 30),
                    _finite(bounds[1], "Scene depth", 2, 30))
        seed = value.get("seed", 1)
        if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
            raise ValueError("seed must be a non-negative 32-bit integer")
        return cls(
            intent=SceneIntent.parse(value.get("intent")),
            requirements=requirements,
            relations=relations,
            routes=routes,
            bounds_m=bounds_m,
            seed=seed,
        )

    def wire(self):
        return {
            "intent": self.intent.wire(),
            "requirements": [item.wire() for item in self.requirements],
            "relations": [item.wire() for item in self.relations],
            "routes": [item.wire() for item in self.routes],
            "bounds_m": list(self.bounds_m),
            "seed": self.seed,
        }


def provider_schema():
    """Strict model schema for semantic production design; no asset IDs or servo values."""
    nullable_number = {"type": ["number", "null"], "minimum": 0, "maximum": 30}
    requirement = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "role_id": {"type": "string", "minLength": 1, "maxLength": 40},
            "query": {"type": "string", "minLength": 1, "maxLength": 200},
            "purpose": {"type": "string", "minLength": 1, "maxLength": 300},
            "categories": {
                "type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 80},
                "maxItems": 8,
            },
            "required": {"type": "boolean"},
            "max_width_m": nullable_number,
            "max_depth_m": nullable_number,
            "max_height_m": nullable_number,
        },
        "required": [
            "role_id", "query", "purpose", "categories", "required",
            "max_width_m", "max_depth_m", "max_height_m",
        ],
    }
    relation = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": list(RELATION_KINDS)},
            "source": {"type": "string", "minLength": 1, "maxLength": 40},
            "target": {"type": ["string", "null"], "maxLength": 40},
            "minimum_m": nullable_number,
            "maximum_m": nullable_number,
            "weight": {"type": "number", "minimum": 0.01, "maximum": 100},
        },
        "required": ["kind", "source", "target", "minimum_m", "maximum_m", "weight"],
    }
    route = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "route_id": {"type": "string", "minLength": 1, "maxLength": 40},
            "points_m": {
                "type": "array",
                "items": {
                    "type": "array", "items": {"type": "number", "minimum": -100, "maximum": 100},
                    "minItems": 2, "maxItems": 2,
                },
                "minItems": 2, "maxItems": 32,
            },
            "clearance_m": {"type": "number", "minimum": 0.05, "maximum": 5},
        },
        "required": ["route_id", "points_m", "clearance_m"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "environment": {"type": "string", "minLength": 1, "maxLength": 200},
                    "mood": {"type": "string", "minLength": 1, "maxLength": 160},
                    "story_functions": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 12},
                    "visual_needs": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 12},
                    "camera_needs": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 12},
                    "actor_needs": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 12},
                    "mode": {"type": "string", "enum": list(SCENE_MODES)},
                },
                "required": ["environment", "mood", "story_functions", "visual_needs", "camera_needs", "actor_needs", "mode"],
            },
            "requirements": {"type": "array", "items": requirement, "minItems": 1, "maxItems": 24},
            "relations": {"type": "array", "items": relation, "maxItems": 48},
            "routes": {"type": "array", "items": route, "maxItems": 8},
            "bounds_m": {
                "type": "array",
                "items": {"type": "number", "minimum": 2, "maximum": 30},
                "minItems": 2, "maxItems": 2,
            },
            "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647},
        },
        "required": ["intent", "requirements", "relations", "routes", "bounds_m", "seed"],
    }
