"""The edit graph: a serializable, backend-independent, content-addressed DAG.

A node's identity *is* its meaning. `node_id = sha256(type, version, inputs, parameters,
time range)` means two identical edits produce the same id, a changed parameter produces a
new id, and a rendered artifact keyed by that id is valid forever. Incremental rendering,
determinism testing and honest progress all fall out of this one property.

Nothing here knows what FFmpeg is. `render/ffmpeg.py` is the only translator.
"""

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar

from .contracts import boolean, integer, mapping, number, seconds, slug
from .errors import GraphError
from .ids import content_id


class NodeType(StrEnum):
    SOURCE = "source"
    TIMING = "timing"
    TRANSFORM = "transform"
    TRACKING = "tracking"
    MASK = "mask"
    COLOR = "color"
    EFFECT = "effect"
    TRANSITION = "transition"
    SEQUENCE = "sequence"
    COMPOSITE = "composite"
    AUDIO = "audio"
    GENERATOR = "generator"
    OUTPUT = "output"


ARITY = {
    NodeType.SOURCE: (0, 0),
    NodeType.GENERATOR: (0, 0),
    NodeType.TIMING: (1, 1),
    NodeType.TRANSFORM: (1, 1),
    NodeType.TRACKING: (1, 1),
    NodeType.MASK: (1, 2),
    NodeType.COLOR: (1, 1),
    NodeType.EFFECT: (1, 1),
    NodeType.TRANSITION: (2, 2),
    NodeType.SEQUENCE: (2, 2),
    NodeType.COMPOSITE: (1, 16),
    NodeType.AUDIO: (0, 8),
    NodeType.OUTPUT: (1, 2),
}


@dataclass(frozen=True, slots=True)
class TimeRange:
    start_s: float
    end_s: float

    def __post_init__(self):
        seconds(self.start_s, "Time range start")
        seconds(self.end_s, "Time range end", self.start_s)

    @property
    def duration_s(self):
        return self.end_s - self.start_s

    def wire(self):
        return {"start_s": round(self.start_s, 6), "end_s": round(self.end_s, 6)}


def _canonical(value):
    """Parameters are normalised before hashing so float formatting cannot split an id.

    A non-finite value is rejected here rather than at encoding time, because a node's
    identity is computed before anything else and an unhashable parameter must fail as a
    graph error with its context, not as a JSON error three frames down.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GraphError(f"A node parameter is not finite: {value}")
        return round(value, 9)
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class RenderNode:
    schema_version: ClassVar[int] = 1
    node_id: str
    type: NodeType
    version: int
    inputs: tuple[str, ...] = ()
    parameters: dict = field(default_factory=dict)
    time_range: TimeRange | None = None
    enabled: bool = True
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.type, NodeType):
            object.__setattr__(self, "type", NodeType(self.type))
        integer(self.version, "Node version", 1, 999)
        object.__setattr__(self, "inputs", tuple(self.inputs))
        for value in self.inputs:
            slug(value, "Node input")
        low, high = ARITY[self.type]
        if not low <= len(self.inputs) <= high:
            raise GraphError(
                f"A {self.type} node takes {low}-{high} inputs, not {len(self.inputs)}",
                {"node_id": self.node_id},
            )
        object.__setattr__(self, "parameters", _canonical(mapping(self.parameters, "Node parameters", 64)))
        _validate_finite(self.parameters, self.type)
        boolean(self.enabled, "Node enabled")
        object.__setattr__(self, "metadata", mapping(self.metadata, "Node metadata", 32))
        expected = address(self.type, self.version, self.inputs, self.parameters, self.time_range)
        if self.node_id != expected:
            raise GraphError(
                f"Node identity does not match its content: {self.node_id} != {expected}",
                {"type": str(self.type)},
            )

    def wire(self):
        return {
            "node_id": self.node_id,
            "type": str(self.type),
            "version": self.version,
            "inputs": list(self.inputs),
            "parameters": dict(self.parameters),
            "time_range": self.time_range.wire() if self.time_range else None,
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }


def _validate_finite(parameters, node_type, path="parameters"):
    for key, value in parameters.items():
        where = f"{path}.{key}"
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            number(value, where)
        elif isinstance(value, str):
            if len(value) > 2048:
                raise GraphError(f"{where} is too long for a {node_type} node")
        elif isinstance(value, dict):
            _validate_finite(value, node_type, where)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    _validate_finite(item, node_type, f"{where}[{index}]")
                elif isinstance(item, (int, float)) and not isinstance(item, bool):
                    number(item, f"{where}[{index}]")
        elif value is not None:
            raise GraphError(f"{where} is not a JSON value")


def address(node_type, version, inputs, parameters, time_range=None):
    """The content address of a node. Changing anything here changes every descendant."""
    return content_id(
        "render-node",
        {
            "type": str(node_type),
            "version": int(version),
            "inputs": list(inputs),
            "parameters": _canonical(parameters),
            "time_range": time_range.wire() if time_range else None,
        },
    )


def node(node_type, version, inputs=(), parameters=None, time_range=None, metadata=None, enabled=True):
    """Build a node with its derived identity. Node ids are never assigned by hand."""
    parameters = _canonical(parameters or {})
    inputs = tuple(inputs)
    return RenderNode(
        node_id=address(node_type, version, inputs, parameters, time_range),
        type=node_type,
        version=version,
        inputs=inputs,
        parameters=parameters,
        time_range=time_range,
        enabled=enabled,
        metadata=metadata or {},
    )


@dataclass(frozen=True, slots=True)
class EditGraph:
    schema_version: ClassVar[int] = 1
    nodes: tuple[RenderNode, ...]
    output_id: str

    def __post_init__(self):
        object.__setattr__(self, "nodes", tuple(self.nodes))
        slug(self.output_id, "Output node id")
        self.validate()

    def by_id(self, node_id):
        for item in self.nodes:
            if item.node_id == node_id:
                return item
        raise GraphError(f"Unknown node '{node_id}'")

    def validate(self):
        index = {}
        for item in self.nodes:
            if not isinstance(item, RenderNode):
                raise GraphError("Graph contents must be typed render nodes")
            if item.node_id in index and index[item.node_id] != item:
                raise GraphError(f"Two different nodes share the identity '{item.node_id}'")
            index[item.node_id] = item
        if self.output_id not in index:
            raise GraphError("The graph's output node is missing")
        outputs = [item for item in self.nodes if item.type is NodeType.OUTPUT]
        if len(outputs) != 1:
            raise GraphError(f"A graph has exactly one output node, found {len(outputs)}")
        for item in self.nodes:
            for source in item.inputs:
                if source not in index:
                    raise GraphError(
                        f"Node '{item.node_id}' reads from missing node '{source}'",
                        {"type": str(item.type)},
                    )
        self.topological()
        reachable = set()
        stack = [self.output_id]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            stack.extend(index[current].inputs)
        orphans = index.keys() - reachable
        if orphans:
            raise GraphError(f"{len(orphans)} nodes cannot reach the output", {"nodes": sorted(orphans)})
        return True

    def topological(self):
        """Kahn's algorithm. A cycle is an error, never a warning."""
        index = {item.node_id: item for item in self.nodes}
        indegree = {key: 0 for key in index}
        dependents = {key: [] for key in index}
        for item in self.nodes:
            for source in item.inputs:
                indegree[item.node_id] += 1
                dependents[source].append(item.node_id)
        ready = sorted(key for key, count in indegree.items() if count == 0)
        order = []
        while ready:
            current = ready.pop(0)
            order.append(index[current])
            for dependent in sorted(dependents[current]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
            ready.sort()
        if len(order) != len(index):
            raise GraphError("The edit graph contains a cycle")
        return tuple(order)

    def ancestors(self, node_id):
        """Every node the given node depends on, in topological order, inclusive."""
        index = {item.node_id: item for item in self.nodes}
        needed, stack = set(), [node_id]
        while stack:
            current = stack.pop()
            if current in needed:
                continue
            needed.add(current)
            stack.extend(index[current].inputs)
        return tuple(item for item in self.topological() if item.node_id in needed)

    def digest(self):
        return content_id(
            "edit-graph",
            {"output": self.output_id, "nodes": [item.node_id for item in self.topological()]},
            32,
        )

    def wire(self):
        return {
            "schema_version": 1,
            "output_id": self.output_id,
            "digest": self.digest(),
            "nodes": [item.wire() for item in self.topological()],
        }
