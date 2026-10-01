"""The project envelope and its migrations. A project loads completely or not at all."""

import json
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import ClassVar

from .contracts import fields, integer, slug
from .errors import MigrationError
from .operations import EditOperation, OperationType, Target
from .state import CreativeIntent, ProjectState, RenderSettings
from .state import empty as empty_state

CURRENT_SCHEMA = 1


def now_utc():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Project:
    schema_version: ClassVar[int] = CURRENT_SCHEMA
    project_id: str
    title: str
    state: ProjectState
    operations: tuple = ()
    created_utc: str = ""
    updated_utc: str = ""

    def __post_init__(self):
        slug(self.project_id, "Project ID")
        object.__setattr__(self, "operations", tuple(self.operations))

    def wire(self):
        return {
            "schema_version": CURRENT_SCHEMA,
            "project_id": self.project_id,
            "title": self.title,
            "created_utc": self.created_utc,
            "updated_utc": self.updated_utc,
            "state": self.state.wire(),
            "operations": [item.wire() for item in self.operations],
        }

    @classmethod
    def parse(cls, value):
        document = migrate(value)
        fields(
            document,
            ("schema_version", "project_id", "title", "state", "operations"),
            ("created_utc", "updated_utc"),
        )
        state = rebuild(document["project_id"], document["operations"], document["state"])
        return cls(
            project_id=document["project_id"],
            title=document["title"],
            state=state,
            operations=tuple(EditOperation.parse(item) for item in document["operations"]),
            created_utc=document.get("created_utc", ""),
            updated_utc=document.get("updated_utc", ""),
        )


def replay_base(project_id, operation_documents, state_document=None):
    """Recover creation metadata that schema 1 stored outside the operation log.

    `new()` can set the original brief without a SET_INTENT operation. Only
    recover that field when the complete history never sets intent; otherwise
    the logged operation must determine it and snapshot comparison stays strict.
    """
    settings = RenderSettings.parse(state_document["render_settings"]) if state_document else None
    state = empty_state(project_id, settings)
    if (
        state_document
        and state_document.get("intent") is not None
        and not any(item["type"] == OperationType.SET_INTENT for item in operation_documents)
    ):
        state = replace(state, intent=CreativeIntent.parse(state_document["intent"]))
    return state


def rebuild(project_id, operation_documents, state_document=None):
    """The state is always recomputed from the log; a stored snapshot is a cache, not truth.

    If the recomputed state disagrees with the stored snapshot, the log wins and the
    disagreement is reported rather than quietly accepted.
    """
    from .reducer import fold

    state = replay_base(project_id, operation_documents, state_document)
    operations = [EditOperation.parse(item) for item in operation_documents]
    state, _ = fold(state, operations)
    if state_document is not None:
        stored = json.dumps(state_document, sort_keys=True)
        rebuilt = json.dumps(state.wire(), sort_keys=True)
        if stored != rebuilt:
            raise MigrationError(
                "The stored project snapshot does not match its operation log",
                {"project_id": project_id, "log_length": len(operations)},
            )
    return state


MIGRATIONS = {}


def migrate(document):
    if not isinstance(document, dict):
        raise MigrationError("A project document must be an object")
    version = document.get("schema_version")
    integer(version, "Project schema version", 1, CURRENT_SCHEMA)
    while version < CURRENT_SCHEMA:
        step = MIGRATIONS.get(version)
        if step is None:
            raise MigrationError(f"No migration from project schema {version}")
        document = step(document)
        version = document["schema_version"]
    return document


def new(project_id, title, intent=None, render_settings=None):
    state = empty_state(project_id, render_settings)
    operations = ()
    stamp = now_utc()
    if intent is not None:
        from .reducer import apply

        parsed = intent if isinstance(intent, CreativeIntent) else CreativeIntent.parse(intent)
        operation = EditOperation(
            operation_id=str(uuid.uuid4()),
            type=OperationType.SET_INTENT,
            target=Target.project(),
            parameters={"intent": parsed.wire()},
            public_explanation="Saved the starting creative brief.",
            created_utc=stamp,
        ).executed(1, stamp)
        state, _ = apply(state, operation)
        operations = (operation,)
    return Project(project_id, title, state, operations, stamp, stamp)
