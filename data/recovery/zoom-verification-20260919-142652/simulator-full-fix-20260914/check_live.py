"""Read-only compilation evidence from the running local app. Never starts a take."""

import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path(__file__).resolve().parent


def request(path, value=None):
    body = None if value is None else json.dumps(value).encode()
    with urlopen(Request("http://127.0.0.1:8766" + path, data=body,
                         headers={"Content-Type": "application/json"}), timeout=90) as response:
        return json.load(response)


evidence = {"health": request("/api/health"), "templates": len(request("/api/previs/templates")["templates"])}
cases = {
    "saved_truck": json.loads((OUT / "saved-truck.json").read_text())["settings"],
    "drawn_path": json.loads((OUT / "drawn-path.json").read_text())["settings"],
    "hero": {"mode": "template", "template_id": "hero_orbit"},
    "dolly_zoom": {"mode": "template", "template_id": "dolly_zoom_in"},
    "walking": {"mode": "path", "points_m": [[-0.5, -2], [0.5, -2]], "scene": {
        "actor_position_m": [0.3, 0.1], "actor_motion": "walk", "walk_distance_m": 0.6, "walk_heading_rad": math.pi/2}},
}
for name, settings in cases.items():
    endpoint = "/api/previs/path" if settings["mode"] == "path" else "/api/previs/templates"
    preview = request(endpoint, settings)
    frames = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"]]
    first, last = frames[0], frames[-1]
    evidence[name] = {
        "settings": preview["settings"], "plan_id": preview["plan_id"],
        "duration_s": preview["duration_s"], "summary": preview["summary"],
        "cart_start_m": preview["frames"][0]["axle_m"],
        "actor_start_m": first["actor"]["position_m"], "actor_end_m": last["actor"]["position_m"],
        "actor_headings": [first["actor"]["heading_rad"], last["actor"]["heading_rad"]],
        "camera_height_m": [first["camera"]["pos"][2], last["camera"]["pos"][2]],
        "focal_mm": [first["focal_mm"], last["focal_mm"]],
        "motor_goals_changed": {r: first["raw_by_role"][r] != last["raw_by_role"][r] for r in ("phone", "light")},
        "minimum_cart_actor_separation_m": min(math.dist(f["q"][:2], f["face"][:2]) for f in frames),
    }
evidence["robot_after"] = request("/api/robot/status")
(OUT / "live-results.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps({"templates": evidence["templates"], "cases": list(cases), "health": evidence["health"]["ok"]}))
