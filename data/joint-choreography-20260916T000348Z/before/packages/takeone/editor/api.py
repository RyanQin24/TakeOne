"""Transport-independent editor use cases.

Shaped like the Director's API object so the existing rehearsal server can mount it without
learning anything new: `get(path)` and `post(path, body)` return plain documents, and
`stream(path, since)` yields them. HTTP framing — Server-Sent Events, byte ranges, status
codes — belongs to the server, not here.
"""

import uuid
from pathlib import Path

from .analysis.probe import probe
from .compile import master_target, preview_target, project_graph
from .contracts import boolean, fields, identity, integer, number, slug, text
from .effects import EFFECTS
from .errors import EditorError, OperationError, ValidationError
from .export import native as native_export
from .export import otio as otio_export
from .ids import file_digest
from .library import (
    ensure_project_library,
    ensure_track_operation,
    find_media_by_digest,
    media_dir,
    place_clip_operation,
    store_file,
    video_track,
)
from .media import import_operation
from .operations import EditOperation, OperationType, Target
from .plan import HeuristicPlanner
from .plan import run as run_plan
from .render.cache import ArtifactCache
from .render.ffmpeg import assert_backend_ready, available_filters, compile_graph
from .render.planner import RenderPlanner
from .render.proxy import ProxyManager
from .state import CreativeIntent, RenderSettings

MAX_STREAM_EVENTS = 200


class EditorAPI:
    def __init__(self, service, workspace, media_roots, jobs=None):
        self.service = service
        self.workspace = Path(workspace).resolve()
        self.media_roots = [Path(item).resolve() for item in media_roots]
        self.jobs = jobs
        self.proxies = ProxyManager(self.workspace / "proxy")
        self.cache = ArtifactCache(self.workspace / "cache")
        self.planner = RenderPlanner(self.cache)
        self._editing = set()

    # -- reads -------------------------------------------------------------

    def get(self, path, query=None):
        query = query or {}
        if path == "/api/editor/health":
            return self.health()
        if path == "/api/editor/effects":
            return {"schema_version": 1, "effects": EFFECTS.catalog()}
        if path == "/api/editor/projects":
            return {"schema_version": 1, "projects": self.service.repository.list_projects()}
        if path == "/api/editor/jobs":
            if self.jobs is None:
                return {"schema_version": 1, "jobs": []}
            return {"schema_version": 1, "jobs": self.jobs.list(query.get("project", [None])[0])}
        prefix = "/api/editor/projects/"
        if path.startswith(prefix):
            remainder = path.removeprefix(prefix)
            project_id, _, tail = remainder.partition("/")
            slug(project_id, "Project ID")
            if tail == "":
                return self.inspect(project_id)
            if tail == "jobs":
                return {
                    "schema_version": 1,
                    "jobs": self.jobs.list(project_id) if self.jobs else [],
                }
            if tail == "operations":
                since = int(query.get("since", ["0"])[0])
                return {
                    "schema_version": 1,
                    "project_id": project_id,
                    "operations": self.service.history(project_id, since),
                }
            if tail == "graph":
                state = self.service.state(project_id)
                target = (
                    master_target(state)
                    if query.get("target", [""])[0] == "master"
                    else preview_target(state)
                )
                graph = project_graph(state, target)
                return {
                    "schema_version": 1,
                    "target": target.wire(),
                    "graph": graph.wire(),
                    "cache": self.cache.report(graph),
                }
        raise KeyError("Editor endpoint not found")

    def health(self):
        try:
            assert_backend_ready()
            backend = {"ready": True, "filters": len(available_filters())}
        except EditorError as error:
            backend = {"ready": False, **error.wire()}
        return {
            "schema_version": 1,
            "ok": backend["ready"],
            "backend": backend,
            "effects": len(EFFECTS.entries),
            "workspace": str(self.workspace),
            "library": str(self.workspace / "library"),
        }

    def inspect(self, project_id):
        snapshot = self.service.repository.snapshot(project_id)
        state = self.service.state(project_id)
        return {
            "schema_version": 1,
            "project": {
                "project_id": snapshot["project_id"],
                "title": snapshot["title"],
                "created_utc": snapshot["created_utc"],
                "updated_utc": snapshot["updated_utc"],
            },
            "state": state.wire(),
            "operations": self.service.history(project_id),
            "artifacts": self.service.repository.artifacts(project_id),
            "events": self.service.repository.events(project_id, 50),
            "library": {"folder": str(media_dir(self.workspace, project_id))},
        }

    # -- writes ------------------------------------------------------------

    def post(self, path, body):
        if not isinstance(body, dict):
            raise ValidationError("Expected a JSON object")
        if path == "/api/editor/projects":
            return self.create(body)
        prefix = "/api/editor/projects/"
        if path.startswith(prefix):
            remainder = path.removeprefix(prefix)
            project_id, _, tail = remainder.partition("/")
            slug(project_id, "Project ID")
            if tail == "operations":
                return self.submit(project_id, body)
            if tail == "media":
                return self.import_media(project_id, body)
            if tail == "place":
                return self.place(project_id, body)
            if tail == "undo":
                return self.service.undo(project_id, integer(body.get("steps", 1), "Steps", 1, 100))
            if tail == "render":
                return self.render(project_id, body)
            if tail == "export":
                return self.export(project_id, body)
            if tail == "auto-edit":
                return self.auto_edit(project_id, body)
        raise KeyError("Editor endpoint not found")

    def create(self, body):
        fields(body, ("project_id", "title"), ("intent", "render_settings"))
        intent = CreativeIntent.parse(body["intent"]) if body.get("intent") else None
        settings = RenderSettings.parse(body["render_settings"]) if body.get("render_settings") else None
        project_id = slug(body["project_id"], "Project ID")
        state = self.service.create(project_id, text(body["title"], "Title", 120), intent, settings)
        folder = ensure_project_library(self.workspace, project_id)
        return {
            "schema_version": 1,
            "ok": True,
            "state": state.wire(),
            "library": {"folder": str(folder)},
        }

    def submit(self, project_id, body):
        fields(body, ("operation",))
        document = dict(body["operation"])
        document.setdefault("schema_version", 1)
        document.setdefault("operation_id", str(uuid.uuid4()))
        identity(document["operation_id"], "Operation ID")
        document["type"] = OperationType(document["type"])
        document["target"] = Target.parse(document["target"])
        operation = EditOperation(
            operation_id=document["operation_id"],
            type=document["type"],
            target=document["target"],
            parameters=document.get("parameters", {}),
            public_explanation=document.get("public_explanation", ""),
            metadata={**document.get("metadata", {}), "source": "client"},
        )
        return {"schema_version": 1, "ok": True, **self.service.submit(project_id, operation)}

    def import_media(self, project_id, body):
        fields(body, ("path",), ("name", "source_space", "build_proxy", "place"))
        return self.ingest_path(
            project_id,
            body["path"],
            name=body.get("name"),
            source_space=body.get("source_space", "rec709"),
            build_proxy=body.get("build_proxy", True),
            place=boolean(body.get("place", False), "Place"),
        )

    def place(self, project_id, body):
        fields(body, ("media_id",), ("name",))
        events = self._place_media(project_id, slug(body["media_id"], "Media ID"), body.get("name"))
        return {"schema_version": 1, "ok": True, "placed": True, "events": events}

    def receive_upload(self, project_id, filename, source_path, place=True):
        """Store an uploaded file in the film's folder, then import and place it."""
        slug(project_id, "Project ID")
        folder = ensure_project_library(self.workspace, project_id)
        stored = store_file(folder, filename, source_path)
        return self.ingest_path(project_id, stored, name=Path(filename).name, place=place)

    def ingest_path(self, project_id, path, name=None, source_space="rec709", build_proxy=True, place=True):
        """Import a file that already lives inside an allowed root, and optionally place it."""
        slug(project_id, "Project ID")
        state = self.service.state(project_id)
        roots = self._roots_for(project_id)
        resolved = Path(path).resolve()
        digest = file_digest(resolved)
        existing = find_media_by_digest(state, digest)
        events = []
        imported = False
        if existing is None:
            operation = import_operation(
                resolved,
                roots=roots,
                probe_fn=probe,
                proxy_manager=self.proxies if build_proxy else None,
                existing=tuple(state.media),
                name=name,
                source_space=source_space,
            )
            events.append(self.service.submit(project_id, operation))
            imported = True
            media_id = operation.parameters["media_id"]
        else:
            media_id = existing.media_id
        placed = []
        if place:
            placed = self._place_media(project_id, media_id, name)
            events.extend(placed)
        return {
            "schema_version": 1,
            "ok": True,
            "imported": imported,
            "reused": not imported,
            "placed": bool(placed),
            "media_id": media_id,
            "library": {"folder": str(media_dir(self.workspace, project_id))},
            "events": events,
            "operation": (events[0]["operation"] if events and imported else None),
        }

    def _place_media(self, project_id, media_id, name=None):
        events = []
        state = self.service.state(project_id)
        if video_track(state) is None:
            events.append(self.service.submit(project_id, ensure_track_operation()))
            state = self.service.state(project_id)
        events.append(self.service.submit(project_id, place_clip_operation(state, media_id, name)))
        return events

    def _roots_for(self, project_id):
        extra = [self.workspace, media_dir(self.workspace, project_id)]
        merged = []
        seen = set()
        for root in list(self.media_roots) + extra:
            resolved = Path(root).resolve()
            if resolved not in seen:
                seen.add(resolved)
                merged.append(resolved)
        return merged

    def render(self, project_id, body):
        fields(body, (), ("target", "wait"))
        state = self.service.state(project_id)
        kind = body.get("target", "preview")
        target = master_target(state) if kind == "master" else preview_target(state)
        graph = project_graph(state, target)
        work = self.planner.plan(graph)
        response = {
            "schema_version": 1,
            "ok": True,
            "target": target.wire(),
            "work": work.wire(),
            "graph_digest": graph.digest(),
        }
        if not work.needs_render:
            response["artifact"] = work.cached_path
            response["cached"] = True
            return response
        if self.jobs is None or boolean(body.get("wait", False), "Wait"):
            plan = compile_graph(graph, self.cache.path_for(work.output_id))
            from .render.executor import RenderExecutor

            result = RenderExecutor().run(plan)
            entry = self.cache.put(work.output_id, plan.duration_s)
            self.service.repository.record_artifact(
                project_id,
                work.output_id,
                kind,
                entry.path,
                entry.bytes,
                entry.duration_s,
                _now(),
            )
            response["artifact"] = entry.path
            response["cached"] = False
            response["result"] = result.wire()
            return response
        job = self.jobs.submit(project_id, kind, graph, work, self.cache, self.service)
        response["job"] = job
        response["cached"] = False
        return response

    def auto_edit(self, project_id, body):
        """Fold a paced heuristic plan. The client watches the operations over SSE."""
        fields(body, (), ("pace_s",))
        slug(project_id, "Project ID")
        pace = number(body.get("pace_s", 0.32), "Pace", 0.0, 2.0)
        state = self.service.state(project_id)
        if not state.media:
            raise ValidationError("Import at least one take before asking the AI to edit")
        if state.finalized:
            raise OperationError("The timeline is finalized; reopen it before editing")
        if project_id in self._editing:
            raise OperationError("The AI is already editing this film")
        planner = HeuristicPlanner()
        self._editing.add(project_id)
        try:
            applied = run_plan(
                lambda: planner.next_operation(self.service.state(project_id)),
                lambda operation: self.service.submit(project_id, operation),
                pace_s=pace,
            )
        finally:
            self._editing.discard(project_id)
        result = self.service.state(project_id)
        return {
            "schema_version": 1,
            "ok": True,
            "applied": applied,
            "phase": result.phase,
            "duration_s": result.timeline.duration_s,
        }

    def export(self, project_id, body):
        fields(body, ("format",), ("destination",))
        state = self.service.state(project_id)
        destination = Path(body.get("destination") or (self.workspace / "export" / project_id))
        if body["format"] == "takeone":
            path = destination.with_suffix("").with_name(destination.name + native_export.EXTENSION)
            return {"schema_version": 1, "ok": True, **native_export.export(self.service, project_id, path)}
        if body["format"] == "otio":
            path = destination.with_suffix(".otio")
            return {"schema_version": 1, "ok": True, **otio_export.export(state, path, project_id)}
        raise ValidationError("Unknown export format; choose 'takeone' or 'otio'")

    # -- stream ------------------------------------------------------------

    def subscribe(self, project_id):
        return self.service.subscribe(project_id)

    def unsubscribe(self, subscription):
        self.service.unsubscribe(subscription)

    def backlog(self, project_id, since):
        """What the client missed, in the shape the live stream publishes.

        A client that has seen nothing gets one whole-state event, never a replay of the
        log: an incremental patch is only meaningful against the state it was computed
        from, and a fresh client has no such state. A client that names a sequence gets
        exactly the operations after it, which is what resume-after-reconnect needs.
        """
        state = self.service.state(project_id)
        history = self.service.history(project_id)
        latest = history[-1]["sequence"] if history else 0
        if since <= 0:
            return [
                {
                    "schema_version": 1,
                    "project_id": project_id,
                    "sequence": latest,
                    "version": state.version,
                    "operation": None,
                    "patch": [{"op": "replace", "path": "", "value": state.wire()}],
                }
            ]
        missed = [entry for entry in history if entry["sequence"] > since]
        if len(missed) > MAX_STREAM_EVENTS:
            # Too far behind to catch up patch by patch; one snapshot is both cheaper and
            # correct, and the client keeps the same resume contract either way.
            return [
                {
                    "schema_version": 1,
                    "project_id": project_id,
                    "sequence": latest,
                    "version": state.version,
                    "operation": None,
                    "patch": [{"op": "replace", "path": "", "value": state.wire()}],
                }
            ]
        return [
            {
                "schema_version": 1,
                "project_id": project_id,
                "sequence": entry["sequence"],
                "version": entry["operation"].get("sequence", entry["sequence"]),
                "operation": entry["operation"],
                "patch": entry["patch"],
            }
            for entry in missed
        ]

    def media_path(self, project_id, media_id, variant="proxy"):
        """Resolve a media file for playback, refusing anything outside the project."""
        state = self.service.state(project_id)
        item = state.media_item(slug(media_id, "Media ID"))
        candidate = {
            "proxy": item.proxy_path or item.path,
            "original": item.path,
            "thumbnail": item.thumbnail_path,
            "waveform": item.waveform_path,
        }.get(variant)
        if not candidate:
            raise KeyError(f"No {variant} for media '{media_id}'")
        resolved = Path(candidate).resolve()
        allowed = self.media_roots + [self.workspace.resolve()]
        if not any(resolved == root or resolved.is_relative_to(root) for root in allowed):
            raise ValidationError("Refusing to serve a file outside the project")
        return resolved

    def artifact_path(self, node_id):
        resolved = self.cache.path_for(slug(node_id, "Artifact ID")).resolve()
        if not resolved.is_relative_to(self.cache.root.resolve()):
            raise ValidationError("Refusing to serve a file outside the artifact cache")
        return resolved


def _now():
    from .project import now_utc

    return now_utc()
