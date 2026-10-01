"""Local preparation receipts keep IK and full reconstruction out of live startup."""

import json
from datetime import datetime, timezone

from takeone.paths import DATA

from .plan import digest, load_plan


def record_check(plan, method="canonical_reconstruction"):
    document = plan.to_dict()
    receipt = dict(
        schema="takeone.checked-plan.v1",
        plan_id=plan.plan_id,
        provenance_sha256=digest(document["provenance"]),
        method=method,
        checked_utc=datetime.now(timezone.utc).isoformat(),
        physical_motion_verified=False,
    )
    path = DATA / "checked-plans" / f"{plan.plan_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    plan_path = path.with_suffix(".plan.json")
    plan_path.write_bytes(plan.payload)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    temporary.replace(path)
    return str(path)


def require_checked(plan):
    """Recheck content and current sources; never infer qualification from receipt."""
    plan = load_plan(plan.to_dict())
    path = DATA / "checked-plans" / f"{plan.plan_id}.json"
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("Plan needs one offline check: motion.cli check --plan <this-plan>") from error
    if (
        receipt.get("schema") != "takeone.checked-plan.v1"
        or receipt.get("plan_id") != plan.plan_id
        or receipt.get("provenance_sha256") != digest(plan.to_dict()["provenance"])
        or receipt.get("method")
        not in ("canonical_preparation", "canonical_reconstruction", "checked_approach")
    ):
        raise ValueError("Checked-plan receipt does not match; run offline check again")
    return plan
