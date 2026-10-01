"""HTTP framing for the editor API: Server-Sent Events, byte ranges, status mapping.

Kept out of `packages/takeone/editor` so the editor stays transport-independent, and kept
out of `server.py` so mounting it there is a handful of lines rather than a rewrite.

Server-Sent Events rather than WebSockets: the traffic is one-directional (commands go over
POST, state comes back as patches), SSE is a few dozen lines on the standard library
server, and `Last-Event-ID` gives resume-after-reconnect without a protocol of our own.
"""

import json
import mimetypes
import os
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HEARTBEAT_SECONDS = 12.0
MAX_BODY_BYTES = 1 << 20
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
STREAM_PREFIX = "/api/editor/projects/"


def status_for(error):
    from takeone.editor.errors import (
        CompileError,
        GraphError,
        MigrationError,
        OperationError,
        RenderError,
        ValidationError,
    )

    if isinstance(error, ValidationError):
        return 400
    if isinstance(error, (OperationError, GraphError, CompileError, MigrationError)):
        return 409
    if isinstance(error, KeyError):
        return 404
    if isinstance(error, RenderError):
        return 503
    return 500


def send_json(handler, document, status=200):
    blob = json.dumps(document, allow_nan=False, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(blob)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(blob)


def send_error(handler, error):
    from takeone.editor.errors import EditorError

    status = status_for(error)
    if isinstance(error, EditorError):
        document = {"schema_version": 1, "ok": False, **error.wire()}
    elif isinstance(error, KeyError):
        document = {
            "schema_version": 1,
            "ok": False,
            "code": "not_found",
            "message": str(error.args[0] if error.args else "Not found"),
        }
    else:
        document = {"schema_version": 1, "ok": False, "code": "error", "message": str(error)}
    send_json(handler, document, status)


def send_file_range(handler, path, download=False, filename=None):
    """Range-aware file serving. Video scrubbing is unusable without it."""
    path = Path(path)
    if not path.is_file():
        return send_json(handler, {"ok": False, "code": "not_found", "message": "Media not found"}, 404)
    size = path.stat().st_size
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    start, end = 0, size - 1
    status = 200
    requested = handler.headers.get("Range")
    if requested and requested.startswith("bytes="):
        piece = requested.removeprefix("bytes=").split(",")[0]
        first, _, last = piece.partition("-")
        try:
            if first:
                start = int(first)
                end = int(last) if last else size - 1
            elif last:
                start = max(0, size - int(last))
        except ValueError:
            start, end = 0, size - 1
        else:
            status = 206
        end = min(end, size - 1)
        if start > end:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{size}")
            handler.end_headers()
            return None
    length = end - start + 1
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(length))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Cache-Control", "no-cache")
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    if download:
        name = Path(filename or path.name).name.replace('"', "")
        handler.send_header("Content-Disposition", f'attachment; filename="{name}"')
    handler.end_headers()
    with path.open("rb") as source:
        source.seek(start)
        remaining = length
        while remaining > 0:
            chunk = source.read(min(1 << 16, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)
    return None


def send_stream(handler, api, project_id, last_event_id):
    """One Server-Sent Events connection per open editor."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()
    subscription = api.subscribe(project_id)
    try:
        for event in api.backlog(project_id, last_event_id):
            _write_event(handler, event)
        while not subscription.closed:
            events = subscription.drain(HEARTBEAT_SECONDS)
            if not events:
                handler.wfile.write(b": keep-alive\n\n")
                handler.wfile.flush()
                continue
            for event in events:
                _write_event(handler, event)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        api.unsubscribe(subscription)


def _write_event(handler, event):
    blob = json.dumps(event, allow_nan=False, separators=(",", ":"))
    handler.wfile.write(f"id: {event.get('sequence', 0)}\nevent: operation\ndata: {blob}\n\n".encode())
    handler.wfile.flush()


class EditorRoutes:
    """Mountable routing for the editor. Returns True when it has handled the request."""

    def __init__(self, api):
        self.api = api

    def handle_get(self, handler, path, query):
        if not path.startswith("/api/editor/"):
            return False
        try:
            if path.startswith(STREAM_PREFIX) and path.endswith("/stream"):
                project_id = path.removeprefix(STREAM_PREFIX).removesuffix("/stream")
                last = handler.headers.get("Last-Event-ID") or query.get("since", ["0"])[0]
                send_stream(handler, self.api, project_id, int(last or 0))
                return True
            if path.startswith(STREAM_PREFIX) and "/media/" in path:
                remainder = path.removeprefix(STREAM_PREFIX)
                project_id, _, tail = remainder.partition("/media/")
                media_id, _, variant = tail.partition("/")
                send_file_range(handler, self.api.media_path(project_id, media_id, variant or "proxy"))
                return True
            if path.startswith("/api/editor/artifacts/"):
                node_id = path.removeprefix("/api/editor/artifacts/")
                want_download = (query.get("download", ["0"])[0] or "").lower() in ("1", "true", "yes")
                filename = query.get("filename", [None])[0]
                send_file_range(
                    handler,
                    self.api.artifact_path(node_id),
                    download=want_download,
                    filename=filename,
                )
                return True
            send_json(handler, self.api.get(path, query))
        except Exception as error:  # noqa: BLE001 - mapped to an explicit status below
            send_error(handler, error)
        return True

    def handle_post(self, handler, path, body):
        if not path.startswith("/api/editor/"):
            return False
        try:
            send_json(handler, self.api.post(path, body))
        except Exception as error:  # noqa: BLE001 - mapped to an explicit status below
            send_error(handler, error)
        return True

    def handle_upload(self, handler, path):
        """Multipart media upload or review-aware derivative intake."""
        if not path.startswith(STREAM_PREFIX) or not path.endswith("/upload"):
            return False
        derivative = path.endswith("/vfx/derivatives/upload")
        suffix = "/vfx/derivatives/upload" if derivative else "/upload"
        project_id = path.removeprefix(STREAM_PREFIX).removesuffix(suffix)
        if not project_id or "/" in project_id:
            send_json(handler, {"ok": False, "code": "not_found", "message": "Not found"}, 404)
            return True
        stored = None
        try:
            filename, stored, fields = _read_multipart_upload(handler, self.api.workspace)
            if derivative:
                if set(fields) != {"metadata"}:
                    raise ValueError("Derivative uploads require one metadata field")
                try:
                    metadata = json.loads(fields["metadata"])
                except ValueError:
                    raise ValueError("Derivative metadata must be JSON") from None
                result = self.api.receive_derivative_upload(project_id, filename, stored, metadata)
            else:
                place = _truthy(fields.get("place", "true"))
                result = self.api.receive_upload(project_id, filename, stored, place=place)
            send_json(handler, result)
        except ValueError as error:
            send_json(handler, {"ok": False, "code": "invalid_request", "message": str(error)}, 400)
        except Exception as error:  # noqa: BLE001 - mapped to an explicit status below
            send_error(handler, error)
        finally:
            if stored is not None:
                Path(stored).unlink(missing_ok=True)
        return True


def make_handler(api, static_root=None):
    """A standalone handler for the editor alone: used by the dev server and the tests."""
    routes = EditorRoutes(api)
    root = str(static_root) if static_root else None

    class Handler(SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def __init__(self, *args, **kwargs):
            if root:
                kwargs["directory"] = root
            super().__init__(*args, **kwargs)

        def log_message(self, fmt, *args):
            if os.environ.get("TAKEONE_EDITOR_VERBOSE"):
                super().log_message(fmt, *args)

        def _local_only(self):
            host = self.headers.get("Host", "")
            return host.split(":")[0] in ("127.0.0.1", "localhost")

        def do_GET(self):
            parsed = urlparse(self.path)
            if not self._local_only():
                return send_json(
                    self,
                    {"ok": False, "code": "local_request_required", "message": "Local host required"},
                    403,
                )
            if routes.handle_get(self, parsed.path, parse_qs(parsed.query)):
                return None
            if root:
                return super().do_GET()
            return send_json(self, {"ok": False, "code": "not_found", "message": "Not found"}, 404)

        def do_POST(self):
            parsed = urlparse(self.path)
            if not self._local_only():
                return send_json(
                    self,
                    {"ok": False, "code": "local_request_required", "message": "Local host required"},
                    403,
                )
            if parsed.path.startswith(STREAM_PREFIX) and parsed.path.endswith("/upload"):
                return routes.handle_upload(self, parsed.path)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= MAX_BODY_BYTES:
                    raise ValueError("Invalid request size")
                raw = self.rfile.read(size)
                body = json.loads(raw)
            except (ValueError, TypeError) as error:
                return send_json(self, {"ok": False, "code": "invalid_request", "message": str(error)}, 400)
            if routes.handle_post(self, parsed.path, body):
                return None
            return send_json(self, {"ok": False, "code": "not_found", "message": "Not found"}, 404)

    return Handler


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _boundary(content_type):
    for piece in str(content_type).split(";"):
        piece = piece.strip()
        if piece.lower().startswith("boundary="):
            value = piece.split("=", 1)[1].strip().strip('"')
            if value:
                return value.encode("ascii", "strict")
    raise ValueError("Multipart upload is missing a boundary")


def _find_marker_offsets(path, marker):
    offsets = []
    overlap = max(0, len(marker) - 1)
    carried = b""
    consumed = 0
    with Path(path).open("rb") as source:
        while True:
            chunk = source.read(1 << 20)
            if not chunk:
                break
            window = carried + chunk
            start = 0
            while True:
                index = window.find(marker, start)
                if index < 0:
                    break
                offsets.append(consumed - len(carried) + index)
                start = index + 1
            carried = window[-overlap:] if overlap else b""
            consumed += len(chunk)
    return offsets


def _copy_range(source, destination, start, end):
    remaining = max(0, end - start)
    with Path(source).open("rb") as incoming, Path(destination).open("wb") as outgoing:
        incoming.seek(start)
        while remaining:
            chunk = incoming.read(min(65536, remaining))
            if not chunk:
                break
            outgoing.write(chunk)
            remaining -= len(chunk)


def _read_headers(path, start, limit=8192):
    with Path(path).open("rb") as source:
        source.seek(start)
        peek = source.read(limit)
    if peek.startswith(b"\r\n"):
        peek = peek[2:]
        start += 2
    separator = peek.find(b"\r\n\r\n")
    if separator < 0:
        raise ValueError("Multipart part is missing headers")
    text = peek[:separator].decode("utf-8", "replace")
    headers = {}
    for line in text.split("\r\n"):
        name, _, value = line.partition(":")
        if name:
            headers[name.strip().lower()] = value.strip()
    return headers, start + separator + 4


def _disposition(value):
    fields = {}
    for piece in value.split(";"):
        piece = piece.strip()
        if "=" not in piece:
            continue
        key, raw = piece.split("=", 1)
        fields[key.strip().lower()] = raw.strip().strip('"')
    return fields


def _read_multipart_upload(handler, workspace):
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ValueError("Uploads must be multipart/form-data")
    size = int(handler.headers.get("Content-Length", "0"))
    if not 1 <= size <= MAX_UPLOAD_BYTES:
        raise ValueError("Upload is empty or larger than 2 GB")
    workspace = Path(workspace)
    spool_dir = workspace / "tmp"
    spool_dir.mkdir(parents=True, exist_ok=True)
    handle, spool_name = tempfile.mkstemp(prefix="upload-", dir=spool_dir)
    os.close(handle)
    spool = Path(spool_name)
    try:
        remaining = size
        with spool.open("wb") as outgoing:
            while remaining:
                chunk = handler.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                outgoing.write(chunk)
                remaining -= len(chunk)
        if remaining:
            raise ValueError("Upload ended before the declared size")
        return _extract_upload(spool, content_type, spool_dir)
    finally:
        spool.unlink(missing_ok=True)


def _extract_upload(spool, content_type, work_dir):
    marker = b"--" + _boundary(content_type)
    offsets = _find_marker_offsets(spool, marker)
    if len(offsets) < 2:
        raise ValueError("Upload did not contain a complete multipart body")
    fields = {}
    filename = None
    stored = None
    try:
        for index, start in enumerate(offsets[:-1]):
            headers, body_start = _read_headers(spool, start + len(marker))
            body_end = offsets[index + 1] - 2
            if body_end < body_start:
                body_end = body_start
            disposition = _disposition(headers.get("content-disposition", ""))
            name = disposition.get("name", "")
            part_name = disposition.get("filename")
            if part_name:
                if stored is not None or name != "file":
                    raise ValueError("Upload requires exactly one file field")
                handle, part_path = tempfile.mkstemp(prefix="part-", dir=work_dir)
                os.close(handle)
                stored = Path(part_path)
                _copy_range(spool, stored, body_start, body_end)
                filename = Path(part_name).name
            elif name:
                if name in fields or body_end - body_start > MAX_BODY_BYTES:
                    raise ValueError("Upload field is repeated or exceeds the metadata limit")
                with spool.open("rb") as source:
                    source.seek(body_start)
                    fields[name] = source.read(body_end - body_start).decode("utf-8", "replace")
        if not filename or stored is None:
            raise ValueError("Upload is missing a video file")
        return filename, stored, fields
    except BaseException:
        if stored is not None:
            stored.unlink(missing_ok=True)
        raise


def serve(api, port=8767, static_root=None):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(api, static_root))
    server.daemon_threads = True
    return server
