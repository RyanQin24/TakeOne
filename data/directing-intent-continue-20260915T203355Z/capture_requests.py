"""Preserve exact UNSENT request bodies. This script never calls generate()."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from takeone.director.creative import PRIMITIVES
from takeone.director.provider import ResponsesPlanner
from takeone.director.skills import SKILLS, sample_project
from takeone.director.studio import movement_catalog, skill_text

folder = Path(__file__).parent / "unsent-requests-final"
folder.mkdir(exist_ok=False)
planner = ResponsesPlanner(api_key="")
records = []
for skill_id in SKILLS:
    sample = sample_project(skill_id)
    payload = dict(brief=sample["brief"], context=sample["context"], skill=SKILLS[skill_id],
                   capabilities=PRIMITIVES, movement_catalog=movement_catalog())
    snapshot = skill_text()
    captured = datetime.now(timezone.utc).isoformat()
    raw, reservation = planner.request(payload, "creative_plan", skill_snapshot=snapshot)
    request = json.loads(raw)
    filename = skill_id + ".json"
    (folder / filename).write_bytes(raw)
    records.append(dict(file=filename, bytes=len(raw), captured_utc=captured,
        request_sha256=hashlib.sha256(raw).hexdigest(),
        skill_snapshot_sha256=hashlib.sha256(snapshot.encode()).hexdigest(),
        instructions_sha256=hashlib.sha256(request["instructions"].encode()).hexdigest(),
        contains_complete_skill_snapshot=snapshot in request["instructions"],
        configured_model=request["model"], sent=False, reserved_microusd=reservation))
report = dict(requests_transmitted=0, source="authored representative briefs; local serialization only",
              limits=planner.config, requests=records)
(folder / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
