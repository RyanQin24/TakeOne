"""Reproduce default movement metrics without contacting hardware."""
import json
import time
from pathlib import Path

from takeone.previs.templates import PRESETS, compile_template
from takeone.motion.studio_plan import validate

rows = []
for template in PRESETS:
    start = time.perf_counter()
    try:
        result = compile_template({"template_id": template["id"]})
        validate(result["plan"])
        p = result["preview"]
        frames = [f for f in p["frames"] if f["time_s"] >= p["orbit_start_s"]]
        row = dict(id=template["id"], seconds=round(time.perf_counter() - start, 3),
                   summary=p["summary"],
                   arm_spans={r: {n: max(f["raw_by_role"][r][n] for f in frames) - min(f["raw_by_role"][r][n] for f in frames) for n in frames[0]["raw_by_role"][r]} for r in ("phone", "light")},
                   camera_start=frames[0]["camera"], camera_end=frames[-1]["camera"],
                   actor_end=frames[-1]["actor"])
    except Exception as error:
        row = dict(id=template["id"], error=str(error))
    rows.append(row)
    print(json.dumps(row), flush=True)
Path(__file__).with_name("default-metrics.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
if any("error" in r for r in rows):
    raise SystemExit(1)
