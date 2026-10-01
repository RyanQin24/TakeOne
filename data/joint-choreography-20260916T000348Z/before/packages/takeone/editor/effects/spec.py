"""What an effect is: an identity, a validated parameter schema, and a compilation.

A transition is an effect with two inputs. Keeping them one type removes a registry, a
compiler path and the recurring question of which one a given creative idea is.
"""

from dataclasses import dataclass, field
from typing import Callable

from ..contracts import boolean, integer, mapping, slug, text
from ..errors import ValidationError
from ..graph import NodeType, node

CATEGORIES = ("color", "film", "dynamic", "transform", "stylise", "transition")


@dataclass(frozen=True, slots=True)
class EffectSpec:
    id: str
    version: int
    name: str
    category: str
    parameters: tuple
    arity: int = 1
    primitive: bool = True
    compile: Callable | None = None
    description: str = ""
    tags: tuple = ()

    def __post_init__(self):
        slug(self.id, "Effect ID")
        integer(self.version, "Effect version", 1, 999)
        text(self.name, "Effect name", 80)
        if self.category not in CATEGORIES:
            raise ValidationError(f"Unknown effect category '{self.category}'")
        if self.arity not in (1, 2):
            raise ValidationError("An effect takes one or two inputs")
        boolean(self.primitive, "Effect primitive flag")
        if not self.primitive and self.compile is None:
            raise ValidationError(f"Composite effect '{self.id}' needs a compile function")

    @property
    def key(self):
        return (self.id, self.version)

    def validate(self, parameters):
        """Validate and fill defaults. Unknown parameters are an error, never ignored."""
        parameters = mapping(parameters or {}, f"{self.id} parameters")
        known = {spec.name for spec in self.parameters}
        unknown = parameters.keys() - known
        if unknown:
            raise ValidationError(f"Unknown parameters for effect '{self.id}': {sorted(unknown)}")
        result = {}
        for spec in self.parameters:
            if spec.name in parameters:
                result[spec.name] = spec.validate(parameters[spec.name])
            elif spec.default is not None:
                result[spec.name] = spec.validate(spec.default)
            elif spec.required:
                raise ValidationError(f"Effect '{self.id}' requires '{spec.name}'")
        return result

    def build(self, inputs, parameters, time_range=None, metadata=None):
        """Compile to render nodes. Returns `(nodes, output_id)`."""
        values = self.validate(parameters)
        if len(inputs) != self.arity:
            raise ValidationError(f"Effect '{self.id}' takes {self.arity} input(s)")
        if self.compile is not None:
            return self.compile(self, tuple(inputs), values, time_range, metadata or {})
        node_type = NodeType.TRANSITION if self.arity == 2 else NodeType.EFFECT
        built = node(
            node_type,
            self.version,
            tuple(inputs),
            {"primitive": self.id, **values},
            time_range,
            metadata or {},
        )
        return (built,), built.node_id

    def ui_schema(self):
        return {
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "category": self.category,
            "arity": self.arity,
            "primitive": self.primitive,
            "description": self.description,
            "tags": list(self.tags),
            "parameters": [
                {
                    "name": spec.name,
                    "kind": spec.kind,
                    "required": spec.required,
                    "minimum": spec.minimum,
                    "maximum": spec.maximum,
                    "choices": list(spec.choices),
                    "default": spec.default,
                }
                for spec in self.parameters
            ],
        }


@dataclass(frozen=True, slots=True)
class EffectRegistry:
    """One registry, populated by explicit calls. No directory scanning, no import magic."""

    entries: dict = field(default_factory=dict)

    def register(self, spec):
        if spec.key in self.entries:
            raise ValidationError(f"Effect '{spec.id}' version {spec.version} is already registered")
        self.entries[spec.key] = spec
        return spec

    def get(self, effect_id, version):
        try:
            return self.entries[(effect_id, version)]
        except KeyError:
            available = sorted(v for i, v in self.entries if i == effect_id)
            raise ValidationError(
                f"Unknown effect '{effect_id}' version {version}"
                + (f"; installed versions: {available}" if available else "")
            ) from None

    def latest(self, effect_id):
        versions = sorted(version for identifier, version in self.entries if identifier == effect_id)
        if not versions:
            raise ValidationError(f"Unknown effect '{effect_id}'")
        return self.entries[(effect_id, versions[-1])]

    def ids(self):
        return tuple(sorted({identifier for identifier, _ in self.entries}))

    def catalog(self):
        return [spec.ui_schema() for spec in sorted(self.entries.values(), key=lambda s: s.key)]
