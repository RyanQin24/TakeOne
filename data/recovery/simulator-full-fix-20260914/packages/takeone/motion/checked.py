"""Local preparation receipts keep IK and full reconstruction out of live startup."""

import hashlib
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
        not in (
            "canonical_preparation",
            "canonical_reconstruction",
            "checked_approach",
            "runtime_provenance_refresh",
        )
    ):
        raise ValueError("Checked-plan receipt does not match; run offline check again")
    return plan


def refresh_runtime_sources(plan):
    """Keep the exact solved shot when only files outside its compiler changed.

    Model, calibration, configuration and planning changes always require normal
    preparation. Runtime preflight is repeated before recording this new identity.
    """
    from takeone.config import provenance

    document = plan.to_dict()
    if document.get("staging"):
        return None
    current = provenance()
    previous = document["provenance"]
    changed = {name for name in current.keys() | previous.keys() if current.get(name) != previous.get(name)}
    runtime_only = {
        "packages/takeone/execution.py",
        "packages/takeone/cart/runtime.py",
        "packages/takeone/adapters/lerobot_arm.py",
        "packages/takeone/motion/arm.py",
        "packages/takeone/motion/checked.py",
        "packages/takeone/motion/observed_maxima.py",
        "packages/takeone/motion/service.py",
        "packages/takeone/motion/devices.py",
    }
    if not changed or not changed <= runtime_only:
        return None
    # The old canonical result must be the locally saved, checked artifact.
    path = DATA / "checked-plans" / f"{plan.plan_id}.json"
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        saved = path.with_suffix(".plan.json").read_bytes()
    except (OSError, ValueError):
        return None
    if (
        saved != plan.payload
        or receipt.get("plan_id") != plan.plan_id
        or receipt.get("provenance_sha256") != digest(previous)
    ):
        return None
    if receipt.get("method") not in (
        "canonical_preparation",
        "canonical_reconstruction",
        "runtime_provenance_refresh",
    ):
        return None
    document["provenance"] = current
    identity = json.dumps({"settings": document["settings"], "provenance": current}, sort_keys=True).encode()
    document["source_shot_id"] = hashlib.sha256(identity).hexdigest()[:12]
    del document["plan_id"]
    return load_plan(document | {"plan_id": digest(document)})
