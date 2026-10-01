"""Bounded read-only qualification probe for a local ChatCut MCP process."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
REQUIRED_TOOLS = frozenset({"get_active_project", "read_project", "preview_timeline", "inspect_item"})
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
MAX_PRIOR_REPORT_BYTES = 8 * 1024 * 1024
MAX_PROBE_BYTES = MAX_PRIOR_REPORT_BYTES
MAX_PROBE_PAGES = 1_000
MAX_PROBE_ITEMS = 10_000
MAX_NOTIFICATIONS_PER_RESPONSE = 1_000
MAX_QUEUED_MESSAGES = 8

_WRITE_STOP = object()


class ProbeError(RuntimeError):
    """A bounded probe failure whose message is safe to show to an operator."""


@dataclass(slots=True)
class _ProbeBudget:
    pages: int = 0
    items: int = 0
    encoded_bytes: int = 0

    def add_page(self, item_count: int) -> None:
        self.pages += 1
        if self.pages > MAX_PROBE_PAGES:
            raise ProbeError("the MCP server exceeded the probe page limit")
        self.items += item_count
        if self.items > MAX_PROBE_ITEMS:
            raise ProbeError("the MCP server exceeded the probe item limit")

    def add_item(self) -> None:
        self.items += 1
        if self.items > MAX_PROBE_ITEMS:
            raise ProbeError("the MCP server exceeded the probe item limit")

    def add_bytes(self, count: int) -> None:
        self.encoded_bytes += count
        if self.encoded_bytes > MAX_PROBE_BYTES:
            raise ProbeError("the MCP server exceeded the probe data limit")


def _reject_nonfinite_json(value: str) -> None:
    del value
    raise ValueError("non-finite JSON number")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON number is outside the finite float range")
    return parsed


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise ProbeError("invalid command-line arguments")


class _Connection:
    def __init__(self, command: list[str], deadline: float, budget: _ProbeBudget):
        self._deadline = deadline
        self._budget = budget
        self._next_id = 1
        self._messages: queue.Queue[bytes | BaseException | None] = queue.Queue(maxsize=MAX_QUEUED_MESSAGES)
        self._reader_failure: BaseException | None = None
        self._writes: queue.Queue[tuple[bytes, queue.Queue[BaseException | None]] | object] = queue.Queue(
            maxsize=1
        )
        self._writer_stop = threading.Event()
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except (OSError, ValueError) as error:
            raise ProbeError("could not start the MCP server") from error
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._writer = threading.Thread(target=self._write_stdin, daemon=True)
        self._reader.start()
        self._writer.start()

    def _publish(self, value: bytes | BaseException | None) -> bool:
        try:
            self._messages.put_nowait(value)
        except queue.Full:
            self._reader_failure = ProbeError("the MCP server exceeded the message backlog limit")
            return False
        return True

    def _read_stdout(self) -> None:
        stdout = self._process.stdout
        if stdout is None:
            self._publish(None)
            return
        try:
            while True:
                line = stdout.readline(MAX_MESSAGE_BYTES + 1)
                if not line:
                    self._publish(None)
                    return
                if len(line) > MAX_MESSAGE_BYTES or not line.endswith(b"\n"):
                    self._publish(ProbeError("the MCP server sent an invalid message"))
                    return
                self._budget.add_bytes(len(line))
                if not self._publish(line):
                    return
        except ProbeError as error:
            self._publish(error)
        except (OSError, ValueError) as error:
            self._publish(error)

    def _write_stdin(self) -> None:
        stdin = self._process.stdin
        if stdin is None:
            return
        while not self._writer_stop.is_set():
            task = self._writes.get()
            if task is _WRITE_STOP or self._writer_stop.is_set():
                return
            encoded, completed = task
            failure: BaseException | None = None
            try:
                remaining = memoryview(encoded)
                while remaining:
                    written = stdin.write(remaining)
                    if not isinstance(written, int) or written <= 0:
                        raise BrokenPipeError
                    remaining = remaining[written:]
                stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as error:
                failure = error
            try:
                completed.put_nowait(failure)
            except queue.Full:
                pass

    def _remaining(self) -> float:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeError("the MCP probe timed out")
        return remaining

    def _send(self, document: dict[str, Any]) -> None:
        try:
            encoded = (
                json.dumps(document, allow_nan=False, separators=(",", ":"), ensure_ascii=False).encode(
                    "utf-8"
                )
                + b"\n"
            )
        except (TypeError, ValueError) as error:
            raise ProbeError("could not encode an MCP request") from error
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise ProbeError("an MCP request exceeded the size limit")
        completed: queue.Queue[BaseException | None] = queue.Queue(maxsize=1)
        try:
            self._writes.put((encoded, completed), timeout=self._remaining())
            failure = completed.get(timeout=self._remaining())
        except queue.Full as error:
            raise ProbeError("the MCP probe timed out") from error
        except queue.Empty as error:
            raise ProbeError("the MCP probe timed out") from error
        if failure is not None:
            raise ProbeError("the MCP server connection closed unexpectedly") from failure

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        notifications = 0
        while True:
            if self._reader_failure is not None:
                raise ProbeError(
                    "the MCP server exceeded the message backlog limit"
                ) from self._reader_failure
            try:
                raw = self._messages.get(timeout=self._remaining())
            except queue.Empty as error:
                raise ProbeError("the MCP probe timed out") from error
            if raw is None:
                raise ProbeError("the MCP server connection closed unexpectedly")
            if isinstance(raw, ProbeError):
                raise raw
            if isinstance(raw, BaseException):
                raise ProbeError("the MCP server sent an invalid message") from raw
            try:
                response = json.loads(
                    raw,
                    parse_constant=_reject_nonfinite_json,
                    parse_float=_finite_float,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
                raise ProbeError("the MCP server sent malformed JSON") from error
            if not isinstance(response, dict):
                raise ProbeError("the MCP server sent an invalid response")
            if response.get("jsonrpc") != "2.0":
                raise ProbeError("the MCP server sent an invalid JSON-RPC response")
            if "id" not in response:
                params = response.get("params", {})
                if (
                    not isinstance(response.get("method"), str)
                    or not response["method"]
                    or "result" in response
                    or "error" in response
                    or not isinstance(params, (dict, list))
                ):
                    raise ProbeError("the MCP server sent an invalid JSON-RPC notification")
                notifications += 1
                if notifications > MAX_NOTIFICATIONS_PER_RESPONSE:
                    raise ProbeError("the MCP server sent too many notifications")
                continue
            if (
                type(response.get("id")) is not int
                or response["id"] != request_id
                or "method" in response
                or "params" in response
            ):
                raise ProbeError("the MCP server sent an unexpected response")
            has_result = "result" in response
            has_error = "error" in response
            if has_result == has_error:
                raise ProbeError("the MCP server sent an invalid JSON-RPC response")
            if has_error:
                rpc_error = response["error"]
                if (
                    not isinstance(rpc_error, dict)
                    or isinstance(rpc_error.get("code"), bool)
                    or not isinstance(rpc_error.get("code"), int)
                    or not isinstance(rpc_error.get("message"), str)
                ):
                    raise ProbeError("the MCP server sent an invalid JSON-RPC error")
                raise ProbeError("the MCP server rejected a request")
            result = response["result"]
            if not isinstance(result, dict):
                raise ProbeError("the MCP server returned an invalid result")
            return result

    def close(self) -> None:
        self._writer_stop.set()
        if self._process.poll() is None:
            try:
                self._process.terminate()
            except OSError:
                pass
        try:
            self._process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                self._process.kill()
            except OSError:
                pass
            try:
                self._process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
        try:
            self._writes.put_nowait(_WRITE_STOP)
        except queue.Full:
            pass
        stdin = self._process.stdin
        if stdin is not None:
            try:
                stdin.close()
            except OSError:
                pass
        stdout = self._process.stdout
        if stdout is not None:
            try:
                stdout.close()
            except OSError:
                pass
        self._writer.join(timeout=0.2)
        self._reader.join(timeout=0.2)


def _validate_inputs(command: list[str], project_id: str, timeline_id: str, timeout_s: float) -> None:
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(part, str) or not part for part in command)
    ):
        raise ProbeError("server command must be a nonempty argument list")
    if not isinstance(project_id, str) or not project_id:
        raise ProbeError("project ID must be nonempty")
    if not isinstance(timeline_id, str) or not timeline_id:
        raise ProbeError("timeline ID must be nonempty")
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
        raise ProbeError("timeout must be a finite positive number")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ProbeError("timeout must be a finite positive number")


def _structured(result: dict[str, Any], purpose: str) -> dict[str, Any]:
    if result.get("isError") is True:
        raise ProbeError(f"{purpose} failed")
    value = result.get("structuredContent")
    if not isinstance(value, dict) or not value:
        raise ProbeError(f"{purpose} returned no structured data")
    return value


def _call_tool(connection: _Connection, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = connection.request("tools/call", {"name": name, "arguments": arguments})
    if result.get("isError") is True:
        raise ProbeError(f"the {name} read failed")
    return result


def _discover_tools(connection: _Connection, budget: _ProbeBudget) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    names: set[str] = set()
    seen_cursors: set[str] = set()
    cursor: str | None = None
    while True:
        params = {} if cursor is None else {"cursor": cursor}
        result = connection.request("tools/list", params)
        page = result.get("tools")
        if not isinstance(page, list):
            raise ProbeError("tool discovery returned an invalid page")
        budget.add_page(len(page))
        for tool in page:
            if not isinstance(tool, dict):
                raise ProbeError("tool discovery returned an invalid tool")
            name = tool.get("name")
            schema = tool.get("inputSchema")
            if not isinstance(name, str) or not name or not isinstance(schema, dict):
                raise ProbeError("tool discovery returned an inconsistent tool")
            if name in names:
                raise ProbeError("tool discovery returned a duplicate tool name")
            names.add(name)
            tools.append(tool)
        next_cursor = result.get("nextCursor")
        if next_cursor is None:
            break
        if not isinstance(next_cursor, str) or not next_cursor:
            raise ProbeError("tool discovery returned an invalid cursor")
        if next_cursor in seen_cursors:
            raise ProbeError("tool discovery repeated a cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    if missing := sorted(REQUIRED_TOOLS - names):
        del missing
        raise ProbeError("the MCP server is missing a required read tool")
    return tools


def _validate_active_project(structured: dict[str, Any], project_id: str) -> None:
    if structured.get("projectId") != project_id:
        raise ProbeError("the active project does not match the requested project")


def _validate_project_map(structured: dict[str, Any], project_id: str, timeline_id: str) -> None:
    project = structured.get("project")
    active = structured.get("activeTimeline")
    timelines = structured.get("timelines")
    if not isinstance(project, dict) or project.get("id") != project_id:
        raise ProbeError("the project read does not match the requested project")
    if not isinstance(active, dict) or active.get("id") != timeline_id:
        raise ProbeError("the project read does not match the requested timeline")
    if not isinstance(timelines, list):
        raise ProbeError("the project read returned an invalid timeline directory")
    if any(not isinstance(entry, dict) for entry in timelines):
        raise ProbeError("the project read returned an invalid timeline directory")
    visible = [entry for entry in timelines if not entry.get("hidden")]
    if len(visible) != 1:
        raise ProbeError("read-only qualification requires exactly one visible timeline")
    if visible[0].get("id") != timeline_id or visible[0].get("active") is not True:
        raise ProbeError("the visible timeline does not match the requested active timeline")


def _read_timeline(connection: _Connection, timeline_id: str, budget: _ProbeBudget) -> dict[str, Any]:
    offset = 0
    seen_offsets = {0}
    state: dict[str, Any] | None = None
    views: list[Any] | None = None
    tracks: list[Any] | None = None
    total_entries: int | None = None
    entries: list[Any] = []
    while True:
        arguments: dict[str, Any] = {
            "timelineId": timeline_id,
            "views": ["timeline"],
            "limit": 100,
        }
        if offset:
            arguments["offset"] = offset
        result = _call_tool(connection, "preview_timeline", arguments)
        structured = _structured(result, "timeline read")
        page_state = structured.get("state")
        page_views = structured.get("views")
        timeline = structured.get("timeline")
        if (
            not isinstance(page_state, dict)
            or not page_state
            or not isinstance(page_views, list)
            or not isinstance(timeline, dict)
        ):
            raise ProbeError("timeline read returned invalid structured data")
        page_entries = timeline.get("entries")
        page_tracks = timeline.get("tracks")
        page_total = timeline.get("totalEntries")
        if (
            not isinstance(page_entries, list)
            or not isinstance(page_tracks, list)
            or isinstance(page_total, bool)
            or not isinstance(page_total, int)
            or page_total < 0
        ):
            raise ProbeError("timeline read returned invalid structured data")
        budget.add_page(len(page_entries))
        if page_state.get("id") != timeline_id:
            raise ProbeError("timeline read returned a different timeline ID")
        if state is None:
            state = page_state
            views = page_views
            tracks = page_tracks
            total_entries = page_total
        elif (
            page_state != state or page_views != views or page_tracks != tracks or page_total != total_entries
        ):
            raise ProbeError("timeline state changed during pagination")
        entries.extend(page_entries)
        if len(entries) > page_total:
            raise ProbeError("timeline entry total changed during pagination")
        next_offset = timeline.get("nextOffset", structured.get("nextOffset"))
        if next_offset is None:
            break
        if isinstance(next_offset, bool) or not isinstance(next_offset, int) or next_offset < 0:
            raise ProbeError("timeline pagination returned an invalid offset")
        if next_offset in seen_offsets or next_offset <= offset:
            raise ProbeError("timeline pagination repeated an offset")
        seen_offsets.add(next_offset)
        offset = next_offset
    if total_entries is None or len(entries) != total_entries:
        raise ProbeError("timeline pagination ended before all entries were read")
    return {
        "state": state,
        "views": views,
        "entries": entries,
        "totalEntries": total_entries,
        "tracks": tracks,
    }


def _inspect_items(
    connection: _Connection,
    timeline_id: str,
    entries: list[Any],
    budget: _ProbeBudget,
) -> list[dict[str, Any]]:
    item_ids: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ProbeError("timeline read returned an invalid entry")
        if entry.get("kind") != "item":
            continue
        item_id = entry.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ProbeError("a placed item has no literal ID")
        if item_id in seen:
            raise ProbeError("the timeline contains a duplicate placed item ID")
        seen.add(item_id)
        item_ids.append(item_id)

    inspections: list[dict[str, Any]] = []
    for item_id in item_ids:
        budget.add_item()
        result = _call_tool(
            connection,
            "inspect_item",
            {"itemId": item_id, "timelineId": timeline_id},
        )
        content = result.get("content")
        readable = isinstance(content, list) and any(
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
            and bool(block["text"].strip())
            for block in content
        )
        if not readable:
            raise ProbeError("item inspection returned no readable content")
        inspections.append({"id": item_id, "inspection": result})
    return inspections


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ProbeError("the MCP snapshot was not valid JSON data") from error


def _render_report(report: dict[str, Any]) -> str:
    try:
        rendered = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    except (TypeError, ValueError, RecursionError) as error:
        raise ProbeError("could not serialize the probe report") from error
    if len(rendered.encode("utf-8")) > MAX_PRIOR_REPORT_BYTES:
        raise ProbeError("the probe report exceeds the size limit")
    return rendered


def probe(
    command: list[str],
    project_id: str,
    timeline_id: str,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Read and fingerprint one exact active ChatCut timeline without mutation."""

    _validate_inputs(command, project_id, timeline_id, timeout_s)
    deadline = time.monotonic() + float(timeout_s)
    budget = _ProbeBudget()
    connection = _Connection(command, deadline, budget)
    try:
        initialized = connection.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "takeone-chatcut-probe", "version": "1"},
            },
        )
        server_info = initialized.get("serverInfo")
        if not isinstance(server_info, dict) or not server_info:
            raise ProbeError("MCP initialization returned no server information")
        if initialized.get("protocolVersion") != PROTOCOL_VERSION:
            raise ProbeError("the MCP server selected an unexpected protocol version")
        connection.notify("notifications/initialized", {})
        tools = _discover_tools(connection, budget)

        active = _structured(_call_tool(connection, "get_active_project", {}), "active project read")
        _validate_active_project(active, project_id)
        project = _structured(_call_tool(connection, "read_project", {}), "project read")
        _validate_project_map(project, project_id, timeline_id)
        timeline = _read_timeline(connection, timeline_id, budget)
        items = _inspect_items(connection, timeline_id, timeline["entries"], budget)

        final_active = _structured(
            _call_tool(connection, "get_active_project", {}), "final active project read"
        )
        final_project = _structured(_call_tool(connection, "read_project", {}), "final project read")
        final_timeline = _read_timeline(connection, timeline_id, budget)
        final_items = _inspect_items(connection, timeline_id, final_timeline["entries"], budget)
        if (
            final_active != active
            or final_project != project
            or final_timeline != timeline
            or final_items != items
        ):
            raise ProbeError("the project or timeline changed during the read-only scan")

        snapshot = {
            "active_project": active,
            "project": project,
            "timeline": timeline,
            "items": items,
        }
        fingerprint = hashlib.sha256(_canonical(snapshot)).hexdigest()
        return {
            "schema_version": 1,
            "project_id": project_id,
            "timeline_id": timeline_id,
            "server_info": server_info,
            "tools": tools,
            "snapshot": snapshot,
            "fingerprint": fingerprint,
            "qualification": {"mode": "read-only", "production_ready": False},
        }
    finally:
        connection.close()


def _load_prior(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as source:
            encoded = source.read(MAX_PRIOR_REPORT_BYTES + 1)
        if len(encoded) > MAX_PRIOR_REPORT_BYTES:
            raise ProbeError("the prior report exceeds the size limit")
        value = json.loads(
            encoded.decode("utf-8"),
            parse_constant=_reject_nonfinite_json,
            parse_float=_finite_float,
        )
    except ProbeError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise ProbeError("the prior report is invalid") from error
    if not isinstance(value, dict):
        raise ProbeError("the prior report is invalid")
    required_types: tuple[tuple[str, type], ...] = (
        ("schema_version", int),
        ("project_id", str),
        ("timeline_id", str),
        ("server_info", dict),
        ("tools", list),
        ("snapshot", dict),
        ("fingerprint", str),
        ("qualification", dict),
    )
    if any(not isinstance(value.get(name), expected) for name, expected in required_types):
        raise ProbeError("the prior report is invalid")
    fingerprint = value["fingerprint"]
    snapshot = value["snapshot"]
    try:
        snapshot_fingerprint = hashlib.sha256(_canonical(snapshot)).hexdigest()
    except ProbeError as error:
        raise ProbeError("the prior report is invalid") from error
    if (
        value["schema_version"] != 1
        or isinstance(value["schema_version"], bool)
        or not value["server_info"]
        or not snapshot
        or len(fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint)
        or fingerprint != snapshot_fingerprint
        or value["qualification"].get("mode") != "read-only"
        or value["qualification"].get("production_ready") is not False
    ):
        raise ProbeError("the prior report is invalid")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        description="Read-only ChatCut qualification; this does not establish production readiness"
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--timeline-id", required=True)
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument(
        "--server",
        required=True,
        nargs="+",
        help="explicit MCP server executable and arguments; place this option last",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        _validate_inputs(
            arguments.server,
            arguments.project_id,
            arguments.timeline_id,
            arguments.timeout_s,
        )
        if arguments.output is not None and arguments.output.exists():
            raise ProbeError("the output file already exists")
        prior = _load_prior(arguments.compare) if arguments.compare is not None else None
        if prior is not None and (
            prior["project_id"] != arguments.project_id or prior["timeline_id"] != arguments.timeline_id
        ):
            raise ProbeError("the prior report targets a different project or timeline")

        report = probe(
            arguments.server,
            arguments.project_id,
            arguments.timeline_id,
            arguments.timeout_s,
        )
        if prior is not None and prior["fingerprint"] != report["fingerprint"]:
            raise ProbeError("the ChatCut timeline state changed")
        rendered = _render_report(report)
        if arguments.output is None:
            sys.stdout.write(rendered)
        else:
            try:
                with arguments.output.open("x", encoding="utf-8") as destination:
                    destination.write(rendered)
            except FileExistsError as error:
                raise ProbeError("the output file already exists") from error
            except OSError as error:
                raise ProbeError("could not create the output file") from error
        return 0
    except ProbeError as error:
        print(f"chatcut probe: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
