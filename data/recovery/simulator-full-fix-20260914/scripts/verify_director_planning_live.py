"""Opt-in, budgeted public-sample acceptance for the selected planning provider. No hardware."""

import argparse
import json
import time
from dataclasses import asdict
from uuid import uuid4

from takeone.director.api import DirectorAPI
from takeone.director.contracts import Session
from takeone.director.provider import ResponsesPlanner
from takeone.director.repository import SessionRepository
from takeone.director.service import DirectorService
from takeone.director.skills import sample_project
from takeone.paths import DATA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-paid", action="store_true", help="Authorize one configured-budget live request"
    )
    parser.add_argument("--skill", choices=("product", "dialogue", "reaction"), default="product")
    args = parser.parse_args()
    provider = ResponsesPlanner()
    if not args.allow_paid:
        parser.error("Live verification requires --allow-paid; it is excluded from automatic tests.")
    if not provider.status()["available"]:
        parser.error("Set OPENAI_API_KEY and enable configs/director-planning.json before live verification.")
    service = DirectorService(SessionRepository(DATA / "verification/director-live.sqlite3"))
    api = DirectorAPI(service)
    api.planning.provider = provider

    def envelope():
        runtime = service.runtime()
        return {
            "schema_version": 1,
            "operation_id": str(uuid4()),
            "runtime_epoch": service.epoch,
            "expires_monotonic_ns": str(int(runtime["now_monotonic_ns"]) + int(runtime["command_ttl_ns"])),
        }

    sample = sample_project(args.skill)
    created = api.post("/api/director/sessions", {**envelope(), "brief": sample["brief"]})
    session = Session.parse(created["session"])
    result = api.post(
        "/api/director/creative",
        {
            **envelope(),
            "scope": asdict(session.scope()),
            "action": "request_plan",
            "payload": {"context": sample["context"], "budget_consent": True},
        },
    )
    if not result["ok"]:
        print(result["message"])
        return 1
    deadline = time.monotonic() + provider.config["timeout_seconds"] + 6
    while time.monotonic() < deadline:
        report = service.repository.inspect(session.session_id)
        job = next(item for item in report["jobs"] if item["job_id"] == result["job_id"])
        if job["status"] != "pending":
            destination = DATA / "verification" / f"director-live-{session.session_id}.json"
            destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Live planning: {job['status']}. Evidence: {destination}")
            print(
                "Inspect dialogue truthfulness, blocking and remaining questions before accepting the model."
            )
            return 0 if job["status"] == "succeeded" else 1
        time.sleep(0.2)
    print("No terminal job state observed. Inspect the job; do not retry blindly.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
