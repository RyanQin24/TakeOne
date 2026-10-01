"""Observed-shape fake ChatCut MCP peer for subprocess integration tests."""

from __future__ import annotations

import json
import sys
import time

PROJECT_ID = "project-1"
TIMELINE_ID = "timeline-1"
VIDEO_ID = "11111111-1111-4111-8111-111111111111"
AUDIO_ID = "22222222-2222-4222-8222-222222222222"


TOOLS = [
    {
        "name": "get_active_project",
        "description": "Read the active project.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_project",
        "description": "Read the project map.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "preview_timeline",
        "description": "Read timeline structure.",
        "inputSchema": {"type": "object", "properties": {"timelineId": {"type": "string"}}},
    },
    {
        "name": "inspect_item",
        "description": "Read a placed item.",
        "inputSchema": {"type": "object", "properties": {"itemId": {"type": "string"}}},
    },
    {
        "name": "unapproved_mutation",
        "description": "Must never be called.",
        "inputSchema": {"type": "object"},
    },
]


def emit(value: object) -> None:
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def result(request_id: object, payload: dict[str, object]) -> None:
    emit({"jsonrpc": "2.0", "id": request_id, "result": payload})


def tool_result(request_id: object, structured: object | None = None, text: str = "ok") -> None:
    payload: dict[str, object] = {"content": [{"type": "text", "text": text}]}
    if structured is not None:
        payload["structuredContent"] = structured
    result(request_id, payload)


def state(duration: int = 90) -> dict[str, object]:
    return {
        "canvas": {"height": 720, "width": 1280},
        "durationFrames": duration,
        "fps": 30,
        "id": TIMELINE_ID,
        "name": "Timeline",
        "range": {"fromFrame": 0, "toFrame": duration},
    }


TRACKS = [
    {
        "alias": "V1",
        "hidden": False,
        "id": "track-v",
        "muted": False,
        "name": None,
        "order": 0,
        "trackType": "video",
    },
    {
        "alias": "A1",
        "hidden": False,
        "id": "track-a",
        "muted": False,
        "name": None,
        "order": 0,
        "trackType": "audio",
    },
]

VIDEO_ENTRY = {
    "asset": {"id": "asset-video", "name": "shot.mp4", "type": "video"},
    "startFrame": 0,
    "id": VIDEO_ID,
    "itemType": "video",
    "kind": "item",
    "sourceRange": {"end": 2000000, "start": 0},
    "timelineRange": {"fromFrame": 0, "toFrame": 60},
    "trackAlias": "V1",
    "trackId": "track-v",
}

GAP_ENTRY = {
    "fromFrame": 0,
    "kind": "gap",
    "timelineRange": {"fromFrame": 0, "toFrame": 15},
    "trackAlias": "A1",
    "trackId": "track-a",
}

AUDIO_ENTRY = {
    "asset": {"id": "asset-audio", "name": "bed.ogg", "type": "audio"},
    "startFrame": 15,
    "id": AUDIO_ID,
    "itemType": "audio",
    "kind": "item",
    "sourceRange": {"end": 2500000, "start": 0},
    "timelineRange": {"fromFrame": 15, "toFrame": 90},
    "trackAlias": "A1",
    "trackId": "track-a",
}


def project_map(scenario: str, final: bool) -> dict[str, object]:
    timeline_id = "timeline-other" if scenario == "wrong_timeline" else TIMELINE_ID
    timelines: list[dict[str, object]] = [
        {"active": True, "hidden": False, "id": timeline_id, "name": "Timeline"}
    ]
    if scenario == "multiple_timelines":
        timelines.append({"active": False, "hidden": False, "id": "timeline-2", "name": "Alt"})
    project_id = "project-changed" if scenario == "changes_during_scan" and final else PROJECT_ID
    return {
        "activeTimeline": {
            "canvas": {"height": 720, "width": 1280},
            "captions": "absent",
            "durationInFrames": 90,
            "fps": 30,
            "id": timeline_id,
            "markerCount": 0,
            "name": "Timeline",
        },
        "assets": {"byType": {"audio": 1, "video": 1}, "total": 2},
        "project": {
            "description": None,
            "designStyle": {"status": "none"},
            "id": project_id,
            "name": "Fixture",
        },
        "timelines": timelines,
    }


def preview(scenario: str, offset: int, final_scan: bool) -> dict[str, object]:
    state_changed = (scenario == "timeline_changes_during_scan" and final_scan) or (
        scenario == "page_state_changes" and offset == 2
    )
    current_state = state(91 if state_changed else 90)
    total = 4 if scenario == "total_changes" and offset == 2 else 3
    page = [VIDEO_ENTRY, GAP_ENTRY] if offset == 0 else [AUDIO_ENTRY]
    timeline: dict[str, object] = {"entries": page, "totalEntries": total, "tracks": TRACKS}
    if offset == 0:
        timeline["nextOffset"] = 0 if scenario == "pagination_loop" else 2
    return {"state": current_state, "views": ["timeline"], "timeline": timeline}


def main() -> int:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "success"
    initialized = False
    preview_calls = 0
    read_project_calls = 0
    inspected: set[str] = set()
    inspection_counts: dict[str, int] = {}

    for raw in sys.stdin:
        request = json.loads(raw)
        method = request.get("method")
        request_id = request.get("id")

        if method == "notifications/initialized":
            initialized = True
            continue

        if scenario == "timeout" and method == "initialize":
            time.sleep(5)
            continue
        if scenario == "eof" and method == "initialize":
            return 0
        if scenario == "malformed" and method == "initialize":
            sys.stdout.write('{"provider_secret":"do-not-leak"\n')
            sys.stdout.flush()
            return 0
        if scenario == "excessive_nesting" and method == "initialize":
            sys.stdout.write("[" * 20_000 + "0" + "]" * 20_000 + "\n")
            sys.stdout.flush()
            return 0

        if method == "initialize":
            if request.get("params", {}).get("protocolVersion") != "2024-11-05":
                emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "wrong protocol"}})
            elif scenario == "finite_number_overflow":
                sys.stdout.write(
                    '{"jsonrpc":"2.0","id":'
                    + str(request_id)
                    + ',"result":{"protocolVersion":"2024-11-05","capabilities":{},'
                    '"serverInfo":{"name":"chatcut-fixture","version":"0.1.6",'
                    '"magnitude":1e999}}}\n'
                )
                sys.stdout.flush()
            elif scenario == "missing_jsonrpc":
                emit({"id": request_id, "result": {"serverInfo": {"name": "bad"}}})
            elif scenario == "result_and_error":
                emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"serverInfo": {"name": "bad"}},
                        "error": {"code": -32000, "message": "bad"},
                    }
                )
            else:
                result(
                    request_id,
                    {
                        "protocolVersion": ("2025-01-01" if scenario == "wrong_protocol" else "2024-11-05"),
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "chatcut-fixture", "version": "0.1.6"},
                    },
                )
            continue

        if not initialized:
            emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "not initialized"}})
            continue

        if method == "tools/list":
            cursor = request.get("params", {}).get("cursor")
            if scenario == "unbounded_tool_pages":
                page = int(cursor or "0")
                result(request_id, {"tools": [], "nextCursor": str(page + 1)})
                continue
            if cursor is None:
                if scenario == "malformed_notification":
                    emit({"jsonrpc": "2.0", "method": ""})
                if scenario == "notification_flood":
                    for index in range(5_000):
                        emit(
                            {
                                "jsonrpc": "2.0",
                                "method": "notifications/progress",
                                "params": {"index": index},
                            }
                        )
                if scenario == "non_reading":
                    result(request_id, {"tools": TOOLS[:3], "nextCursor": "x" * 2_000_000})
                    time.sleep(2)
                    return 0
                if scenario == "large_request":
                    result(request_id, {"tools": TOOLS[:3], "nextCursor": "x" * 2_000_000})
                    continue
                first = TOOLS[:3]
                if scenario == "missing_tool":
                    first = [tool for tool in first if tool["name"] != "preview_timeline"]
                result(request_id, {"tools": first, "nextCursor": "page-2"})
            else:
                second = TOOLS[3:]
                if scenario == "duplicate_tool":
                    second = [TOOLS[0], *second]
                next_cursor = "page-2" if scenario == "tool_cursor_loop" else None
                payload: dict[str, object] = {"tools": second}
                if next_cursor is not None:
                    payload["nextCursor"] = next_cursor
                result(request_id, payload)
            continue

        if method != "tools/call":
            emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "unsupported"}})
            continue

        name = request.get("params", {}).get("name")
        arguments = request.get("params", {}).get("arguments", {})
        if name == "unapproved_mutation":
            emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "mutation called"}})
        elif name == "get_active_project":
            if arguments:
                emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "unexpected arguments"}})
                continue
            project_id = "wrong-project" if scenario == "wrong_project" else PROJECT_ID
            if scenario == "changes_during_scan" and read_project_calls >= 1:
                project_id = "project-changed"
            tool_result(request_id, {"projectId": project_id, "surface": "desktop"})
        elif name == "read_project":
            if arguments:
                emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "read_project retargeted"}})
                continue
            read_project_calls += 1
            if scenario == "tool_error":
                result(
                    request_id,
                    {
                        "isError": True,
                        "content": [{"type": "text", "text": "provider raw secret do-not-leak"}],
                    },
                )
            elif scenario == "missing_project_structured":
                tool_result(request_id, None, "Project read successfully")
            else:
                tool_result(request_id, project_map(scenario, read_project_calls > 1))
        elif name == "preview_timeline":
            if arguments.get("timelineId") != TIMELINE_ID or "projectId" in arguments:
                emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "wrong preview target"}})
                continue
            preview_calls += 1
            if scenario == "missing_snapshot":
                tool_result(request_id, None, "Timeline read successfully")
                continue
            offset = arguments.get("offset", 0)
            tool_result(request_id, preview(scenario, offset, preview_calls > 2))
        elif name == "inspect_item":
            item_id = arguments.get("itemId")
            if arguments.get("timelineId") != TIMELINE_ID or "projectId" in arguments:
                emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "wrong inspect target"}})
                continue
            inspected.add(item_id)
            inspection_counts[item_id] = inspection_counts.get(item_id, 0) + 1
            if scenario == "missing_inspection_content":
                result(request_id, {})
                continue
            if scenario == "empty_inspection_content":
                result(request_id, {"content": []})
                continue
            if scenario == "malformed_inspection_content":
                result(request_id, {"content": [{}]})
                continue
            if item_id == VIDEO_ID:
                transition = (
                    "Cross Dissolve duration=18f"
                    if scenario == "changed_transition"
                    else "Cross Dissolve duration=12f"
                )
                tool_result(
                    request_id,
                    None,
                    f"Item: {VIDEO_ID}\nProperties:\n  decibelAdjustment: 0\nAttached:\n  transition-out {transition}",
                )
            elif item_id == AUDIO_ID:
                gain = (
                    -9
                    if scenario == "changed_gain"
                    or (scenario == "item_changes_during_scan" and inspection_counts[item_id] > 1)
                    else -6
                )
                tool_result(
                    request_id,
                    None,
                    f"Item: {AUDIO_ID}\nProperties:\n  decibelAdjustment: {gain}\n  audioFadeIn: 0.25\n  audioFadeOut: 0.5",
                )
            else:
                emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "unknown item"}})
        else:
            emit({"jsonrpc": "2.0", "id": request_id, "error": {"message": "unapproved tool called"}})

        if name == "inspect_item" and len(inspected) == 2:
            emit({"jsonrpc": "2.0", "method": "notifications/progress", "params": {"message": "ignored"}})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
