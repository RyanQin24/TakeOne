"""The editor service: one owner of project state, one door for every operation.

A planner, a template, a human control and the robot director all arrive here. The service
appends the operation, folds it, commits the result atomically and publishes the resulting
patch. Nothing else in the system is allowed to change a project.
"""

import threading
from collections import deque
from dataclasses import replace

from . import project as project_module
from . import reducer
from .errors import EditorError, OperationError
from .operations import EditOperation
from .state import RenderSettings

MAX_SUBSCRIBERS = 16
MAX_BUFFERED_EVENTS = 512


class Subscription:
    """A bounded queue of published events. A slow reader is dropped, never back-pressured
    onto the editor; the client resumes from its last sequence."""

    def __init__(self, project_id):
        self.project_id = project_id
        self.events = deque(maxlen=MAX_BUFFERED_EVENTS)
        self.condition = threading.Condition()
        self.closed = False

    def publish(self, event):
        with self.condition:
            self.events.append(event)
            self.condition.notify_all()

    def drain(self, timeout=15.0):
        with self.condition:
            if not self.events:
                self.condition.wait(timeout)
            items = list(self.events)
            self.events.clear()
            return items

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()


class EditorService:
    def __init__(self, repository):
        self.repository = repository
        self._states = {}
        self._lock = threading.RLock()
        self._subscribers = []

    # -- lifecycle ---------------------------------------------------------

    def create(self, project_id, title, intent=None, render_settings=None):
        with self._lock:
            if self.repository.exists(project_id):
                raise OperationError(f"Project '{project_id}' already exists")
            settings = render_settings
            if isinstance(settings, dict):
                settings = RenderSettings.parse(settings)
            record = project_module.new(project_id, title, intent, settings)
            self.repository.create(record, project_module.now_utc())
            self._states[project_id] = record.state
            return record.state

    def state(self, project_id):
        with self._lock:
            if project_id not in self._states:
                self._states[project_id] = self._load(project_id)
            return self._states[project_id]

    def _load(self, project_id):
        snapshot = self.repository.snapshot(project_id)
        history = self.repository.operations(project_id)
        return project_module.rebuild(
            project_id, [entry["operation"] for entry in history], snapshot["state"]
        )

    # -- the one door ------------------------------------------------------

    def submit(self, project_id, operation):
        """Apply one operation. Returns the published event, or raises."""
        if not isinstance(operation, EditOperation):
            raise EditorError("submit takes a typed EditOperation")
        with self._lock:
            state = self.state(project_id)
            new_state, patch = reducer.apply(state, operation)
            stamped, sequence = self.repository.append(
                project_id, operation, patch, new_state, project_module.now_utc()
            )
            self._states[project_id] = new_state
            event = {
                "schema_version": 1,
                "project_id": project_id,
                "sequence": sequence,
                "version": new_state.version,
                "operation": stamped.wire(),
                "patch": patch,
            }
        self._publish(project_id, event)
        return event

    def submit_all(self, project_id, operations):
        return [self.submit(project_id, operation) for operation in operations]

    # -- history, replay, undo --------------------------------------------

    def history(self, project_id, since=0):
        return self.repository.operations(project_id, since)

    def replay(self, project_id, upto=None):
        """Fold a prefix of the log. The replay *is* the edit, not a re-enactment of it."""
        history = self.repository.operations(project_id)
        documents = [entry["operation"] for entry in history]
        if upto is not None:
            documents = documents[:upto]
        snapshot = self.repository.snapshot(project_id)
        settings = RenderSettings.parse(snapshot["state"]["render_settings"])
        from .state import empty as empty_state

        state = empty_state(project_id, settings)
        operations = [EditOperation.parse(item) for item in documents]
        state, patches = reducer.fold(state, operations)
        return state, operations, patches

    def undo(self, project_id, steps=1):
        with self._lock:
            history = self.repository.operations(project_id)
            if not history:
                raise OperationError("There is nothing to undo")
            keep = max(0, len(history) - max(1, int(steps)))
            state, _, _ = self.replay(project_id, keep)
            state = replace(state, version=state.version)
            self.repository.truncate(
                project_id,
                history[keep - 1]["sequence"] if keep else 0,
                state,
                project_module.now_utc(),
            )
            self._states[project_id] = state
        event = {
            "schema_version": 1,
            "project_id": project_id,
            "sequence": keep,
            "version": state.version,
            "operation": None,
            "patch": [{"op": "replace", "path": "", "value": state.wire()}],
        }
        self._publish(project_id, event)
        return event

    # -- publication -------------------------------------------------------

    def subscribe(self, project_id):
        with self._lock:
            if len(self._subscribers) >= MAX_SUBSCRIBERS:
                raise EditorError("Too many editor subscribers")
            subscription = Subscription(project_id)
            self._subscribers.append(subscription)
            return subscription

    def unsubscribe(self, subscription):
        with self._lock:
            if subscription in self._subscribers:
                self._subscribers.remove(subscription)
        subscription.close()

    def _publish(self, project_id, event):
        with self._lock:
            targets = [item for item in self._subscribers if item.project_id == project_id]
        for target in targets:
            target.publish(event)
