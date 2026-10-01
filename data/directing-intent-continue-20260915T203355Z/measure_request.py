"""Serialize representative requests locally. Never call generate or a network API."""
import hashlib
import json
from pathlib import Path

from takeone.director.creative import PRIMITIVES
from takeone.director.provider import PlanningError, ResponsesPlanner
from takeone.director.skills import SKILLS, sample_project
from takeone.director.studio import movement_catalog, skill_text

planner = ResponsesPlanner(api_key="")
records = []
for skill_id in SKILLS:
    sample = sample_project(skill_id)
    payload = dict(brief=sample["brief"], context=sample["context"], skill=SKILLS[skill_id],
                   capabilities=PRIMITIVES, movement_catalog=movement_catalog())
    record = dict(skill_id=skill_id, sent=False, byte_limit=planner.config["max_request_bytes"])
    try:
        raw, reserved = planner.request(payload, "creative_plan")
        request = json.loads(raw)
        record.update(bytes=len(raw), reserved_microusd=reserved,
                      skills_present=skill_text() in request["instructions"],
                      request_sha256=hashlib.sha256(raw).hexdigest(),
                      instructions_sha256=hashlib.sha256(request["instructions"].encode()).hexdigest())
    except PlanningError as error:
        record.update(error=error.code, message=str(error))
    records.append(record)
print(json.dumps(records, indent=2))
