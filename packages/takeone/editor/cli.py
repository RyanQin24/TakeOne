"""Offline editor commands, and the local editor server the React app talks to.

No command here touches hardware, and none starts a render unless asked to.
"""

import argparse
import json
import sys
from pathlib import Path

from ..paths import APP, DATA, WORKSPACE
from .api import EditorAPI
from .jobs import JobPool
from .repository import ProjectRepository
from .service import EditorService

DEFAULT_PORT = 8767


def _api(workspace=None, media_roots=None, jobs=None):
    workspace = Path(workspace or (DATA / "editor"))
    repository = ProjectRepository(workspace / "projects.sqlite3")
    service = EditorService(repository)
    roots = [Path(item) for item in (media_roots or [WORKSPACE])]
    return EditorAPI(service, workspace, roots, jobs=jobs)


def doctor(arguments):
    api = _api(arguments.workspace)
    print(json.dumps(api.health(), indent=2))
    return 0 if api.health()["ok"] else 1


def effects(arguments):
    api = _api(arguments.workspace)
    catalog = api.get("/api/editor/effects")["effects"]
    for entry in catalog:
        parameters = ", ".join(item["name"] for item in entry["parameters"])
        kind = "transition" if entry["arity"] == 2 else ("primitive" if entry["primitive"] else "look")
        print(f"{entry['id']:<24} v{entry['version']}  {kind:<10} {parameters}")
    print(f"\n{len(catalog)} effects registered")
    return 0


def projects(arguments):
    api = _api(arguments.workspace)
    print(json.dumps(api.get("/api/editor/projects"), indent=2))
    return 0


def replay(arguments):
    api = _api(arguments.workspace)
    state, operations, _ = api.service.replay(arguments.project, arguments.upto)
    for operation in operations:
        print(
            f"{operation.sequence:>4}  {operation.phase:<10} {str(operation.type):<24} "
            f"{operation.public_explanation}"
        )
    print(f"\n{len(operations)} operations; timeline {state.timeline.duration_s:.3f}s")
    return 0


def _editor_http():
    """Load the HTTP adapter by path, so the command works from any working directory."""
    import importlib.util

    location = APP / "editor_http.py"
    specification = importlib.util.spec_from_file_location("takeone_editor_http", location)
    if specification is None or specification.loader is None:
        raise SystemExit(f"The editor HTTP adapter is missing: {location}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def serve(arguments):
    editor_http = _editor_http()

    jobs = JobPool()
    api = _api(arguments.workspace, arguments.media_root, jobs=jobs)
    static = Path(arguments.static) if arguments.static else None
    server = editor_http.serve(api, arguments.port, static)
    print(f"TAKE ONE editor API on http://127.0.0.1:{arguments.port}", flush=True)
    if static:
        print(f"Serving the built interface from {static}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        jobs.close()
        server.server_close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="TAKE ONE editor; no hardware is touched")
    parser.add_argument("--workspace", default=None, help="Editor data directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check the render backend and report what is installed")
    sub.add_parser("effects", help="List the installed effects")
    sub.add_parser("projects", help="List local projects")

    replay_parser = sub.add_parser("replay", help="Print a project's operation log")
    replay_parser.add_argument("project")
    replay_parser.add_argument("--upto", type=int, default=None)

    serve_parser = sub.add_parser("serve", help="Run the local editor API")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument("--media-root", action="append", default=None)
    serve_parser.add_argument("--static", default=None, help="Directory of the built interface")

    arguments = parser.parse_args(argv)
    return {
        "doctor": doctor,
        "effects": effects,
        "projects": projects,
        "replay": replay,
        "serve": serve,
    }[arguments.command](arguments)


if __name__ == "__main__":
    sys.exit(main())
