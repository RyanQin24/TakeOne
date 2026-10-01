"""The HTTP surface, exercised against a live local server.

Checks the things that only break over the wire: Server-Sent Events framing and resume,
byte-range media delivery (without which scrubbing is unusable), and the mapping from
editor errors to HTTP status codes.
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from takeone.editor.api import EditorAPI  # noqa: E402
from takeone.editor.cli import _editor_http  # noqa: E402
from takeone.editor.jobs import JobPool  # noqa: E402
from takeone.editor.repository import ProjectRepository  # noqa: E402
from takeone.editor.service import EditorService  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
CHECKS = []


def check(label, condition, detail=""):
    CHECKS.append((label, bool(condition), detail))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + (f"  — {detail}" if detail else ""))
    return condition


def _upload(path, file_path):
    boundary = "----takeone-api-check"
    header = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="place"\r\n\r\n'
        "true\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode()
    body = header + file_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    call = urllib.request.Request(
        BASE + path,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(call, timeout=60) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def request(path, body=None, headers=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    call = urllib.request.Request(
        BASE + path,
        data=data,
        method=method or ("POST" if data else "GET"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(call, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}"), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}"), dict(error.headers)


def main():
    workspace = ROOT / "data" / "editor" / "api-check"
    if workspace.exists():
        import shutil

        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    print("\nEDITOR HTTP SURFACE\n")
    jobs = JobPool()
    service = EditorService(ProjectRepository(workspace / "projects.sqlite3"))
    api = EditorAPI(service, workspace, [FIXTURES], jobs=jobs)
    server = _editor_http().serve(api, PORT)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)

    try:
        status, document, _ = request("/api/editor/health")
        check(
            "Health reports a ready backend",
            status == 200 and document["ok"],
            f"{document['effects']} effects registered",
        )

        status, document, _ = request("/api/editor/projects", {"project_id": "api", "title": "API check"})
        check("Project created over HTTP", status == 200 and document["ok"])

        status, document, _ = request("/api/editor/projects", {"project_id": "api", "title": "Duplicate"})
        check("A duplicate project is a 409, not a 500", status == 409, document.get("code"))

        status, document, _ = request(
            "/api/editor/projects/api/media",
            {"path": str(FIXTURES / "shot_a_neutral.mp4")},
        )
        media_id = document["operation"]["parameters"]["media_id"]
        check("Media imported over HTTP", status == 200 and document["ok"], media_id)

        status, document, _ = request("/api/editor/projects", {"project_id": "ingest", "title": "Ingest"})
        check(
            "A second project gets its own library folder",
            status == 200 and document["ok"] and Path(document["library"]["folder"]).is_dir(),
        )
        upload_status, upload_document = _upload(
            "/api/editor/projects/ingest/upload", FIXTURES / "shot_a_neutral.mp4"
        )
        check(
            "A dropped clip is stored locally and placed on the timeline",
            upload_status == 200 and upload_document.get("ok") and upload_document.get("placed"),
            upload_document.get("media_id", ""),
        )

        status, document, _ = request(
            "/api/editor/projects",
            {
                "project_id": "cut",
                "title": "Auto edit",
                "intent": {
                    "prompt": "Make a mysterious luxury introduction that becomes powerful.",
                    "target_duration_s": 8,
                    "aspect_ratio": "16:9",
                },
            },
        )
        check("A film with intent is created for the AI edit", status == 200 and document["ok"])
        for name in ("shot_a_neutral.mp4", "shot_b_warm.mp4"):
            path = FIXTURES / name
            if not path.is_file():
                continue
            boundary = "----takeone-api-check"
            header = (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="place"\r\n\r\n'
                "false\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
                "Content-Type: video/mp4\r\n\r\n"
            ).encode()
            body = header + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
            call = urllib.request.Request(
                BASE + "/api/editor/projects/cut/upload",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(call, timeout=60) as response:
                uploaded = json.loads(response.read() or b"{}")
            check(f"{name} stored without placing", uploaded.get("ok") and not uploaded.get("placed"))
        status, document, _ = request("/api/editor/projects/cut/auto-edit", {"pace_s": 0})
        check(
            "The heuristic editor produces a complete cut",
            status == 200
            and document.get("ok")
            and document.get("phase") == "complete"
            and document.get("applied", 0) > 8,
            f"phase={document.get('phase')} applied={document.get('applied')}",
        )

        status, document, _ = request("/api/editor/projects/api/media", {"path": "/etc/passwd"})
        check("A path outside the media roots is refused", status == 400, document.get("message", "")[:60])

        events = []
        stop = threading.Event()

        def listen():
            call = urllib.request.Request(f"{BASE}/api/editor/projects/api/stream")
            with urllib.request.urlopen(call, timeout=20) as response:
                buffer = b""
                while not stop.is_set():
                    chunk = response.read1(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n\n" in buffer:
                        frame, _, buffer = buffer.partition(b"\n\n")
                        for line in frame.decode().splitlines():
                            if line.startswith("data: "):
                                events.append(json.loads(line[6:]))
                        if len(events) >= 4:
                            stop.set()

        listener = threading.Thread(target=listen, daemon=True)
        listener.start()
        time.sleep(0.4)

        for operation in (
            {
                "type": "ADD_TRACK",
                "target": {"kind": "project"},
                "parameters": {"track_id": "V1", "kind": "video"},
            },
            {
                "type": "ADD_CLIP",
                "target": {"kind": "track", "track_id": "V1"},
                "parameters": {
                    "clip_id": "c1",
                    "media_id": media_id,
                    "timeline_start_s": 0.0,
                    "source_start_s": 0.5,
                    "source_end_s": 3.0,
                },
                "public_explanation": "Strongest opening composition.",
            },
            {
                "type": "APPLY_CREATIVE_LOOK",
                "target": {"kind": "clip", "clip_id": "c1"},
                "parameters": {"look_id": "luxury_warm", "intensity": 0.65},
                "public_explanation": "Applying restrained luxury warmth.",
            },
        ):
            status, document, _ = request(
                "/api/editor/projects/api/operations",
                {"operation": {**operation, "operation_id": str(uuid.uuid4())}},
            )
            if status != 200:
                print("   operation rejected:", document)
                break

        deadline = time.time() + 5
        while len(events) < 4 and time.time() < deadline:
            time.sleep(0.1)
        stop.set()

        check(
            "The stream delivered the initial state and every operation",
            len(events) >= 4,
            f"{len(events)} events",
        )
        check(
            "Every streamed event carries its operation and its patch",
            all("patch" in item for item in events)
            and sum(1 for item in events if item.get("operation")) >= 3,
        )

        status, document, _ = request(
            "/api/editor/projects/api/operations",
            {
                "operation": {
                    "type": "ADD_CLIP",
                    "target": {"kind": "track", "track_id": "V1"},
                    "parameters": {
                        "clip_id": "c2",
                        "media_id": media_id,
                        "timeline_start_s": 0.0,
                        "source_start_s": 0.0,
                        "source_end_s": 1.0,
                    },
                }
            },
        )
        check(
            "An operation that does not fit the state is a 409",
            status == 409,
            document.get("message", "")[:70],
        )

        status, document, _ = request(
            "/api/editor/projects/api/operations",
            {
                "operation": {
                    "type": "APPLY_CREATIVE_LOOK",
                    "target": {"kind": "clip", "clip_id": "c1"},
                    "parameters": {"look_id": "luxury_warm", "intensity": 4.0},
                }
            },
        )
        check("An out-of-range parameter is a 400", status == 400, document.get("message", "")[:70])

        status, document, _ = request("/api/editor/projects/api/render", {"wait": True})
        check(
            "Render completed over HTTP",
            status == 200 and document["ok"],
            f"{document['work']['node_count']} nodes, cached={document['cached']}",
        )
        artifact_id = document["work"]["output_id"]

        status, document, _ = request("/api/editor/projects/api/render", {"wait": True})
        check("The second render is served from cache", document.get("cached") is True)

        call = urllib.request.Request(
            f"{BASE}/api/editor/artifacts/{artifact_id}", headers={"Range": "bytes=0-1023"}
        )
        with urllib.request.urlopen(call, timeout=10) as response:
            payload = response.read()
            check(
                "Byte-range requests work, so the preview can scrub",
                response.status == 206 and len(payload) == 1024,
                response.headers.get("Content-Range"),
            )

        status, document, _ = request("/api/editor/projects/api/export", {"format": "otio"})
        check(
            "OTIO export over HTTP",
            status == 200 and Path(document["path"]).is_file(),
            Path(document["path"]).name,
        )

        status, document, _ = request("/api/editor/projects/api/undo", {"steps": 1})
        check(
            "Undo over HTTP returns a full-state patch", status == 200 and document["patch"][0]["path"] == ""
        )

        status, document, _ = request("/api/editor/projects/missing")
        check("An unknown project is a 404", status == 404, document.get("code"))

        backlog = api.backlog("api", 1)
        check(
            "The stream can resume from a sequence",
            all(item["sequence"] > 1 for item in backlog),
            f"{len(backlog)} events after sequence 1",
        )
    finally:
        server.shutdown()
        server.server_close()
        jobs.close()

    failed = [label for label, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    if failed:
        print("FAILED: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
