"""Authored asset/inventory acceptance exercise, not a story generator or robot run."""

import argparse
import json
from pathlib import Path

from cinematic_upgrade_demo import envelope, request
from scene_assets_demo import project as ensemble_project
from takeone.asset_library.catalog import AssetCatalog
from takeone.director.contracts import ProductionBrief
from takeone.director.creative import digest, validate_plan

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/asset-scenes-completion-20260915/showcase"


def project():
    sample = ensemble_project()
    document = sample["document"]
    title = "A shared discovery - installed-model showcase"
    document["title"] = sample["brief"]["title"] = title
    catalog = AssetCatalog.from_project(ROOT)
    wardrobe = [("#b66b46", "#293e53"), ("#417f91", "#30383e"), ("#8b836c", "#3b4144")]
    for actor, (cloth, pants) in zip(document["actors"], wardrobe):
        actor["appearance"] = dict(cloth=cloth, pants=pants, skin="#cfa783", hair="#382f27", shoe="#ddd8ca")
    for scene in document["scenes"]:
        for item in scene["objects"]:
            item["availability"] = "virtual_only" if item["asset_id"].startswith("lib:") else "unconfirmed"
        if scene["space_id"] != "room":
            continue
        for query, position, size in (
            ("table", [0.0, 1.9, 0.375], [1.4, 0.7, 0.75]),
            ("mug", [0.4, 1.9, 0.85], [0.12, 0.12, 0.2]),
        ):
            matches = catalog.search(query, limit=1, kind="prop")
            if not matches:
                raise ValueError(f"Install the reviewed furniture/food packs before this exercise: {query}")
            scene["objects"].append(
                dict(
                    object_id="shared-" + query,
                    asset_id=matches[0]["asset_id"],
                    label="Proposed shared " + query,
                    position_m=position,
                    size_m=size,
                    yaw_rad=0,
                    availability="proposed",
                )
            )
        for item in scene["objects"]:
            if item["object_id"] == "imported-chair":
                item["position_m"] = [-2.4, 1.4, 0.45]
        scene["location_notes"] = (
            "Proposed workshop lounge: the table is the shared task surface; the mug marks a pause in work. "
            "Keep the maker beside the visitor and the teammate on a separate background task. "
            "Confirmed physical inventory: none. Arrange proposed dressing before filming; imported chair/plant "
            "are visualization references only. Keep the camera lane and performer marks clear."
        )
    validate_plan(document, ProductionBrief.parse(sample["brief"]), sample["context"])
    return sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    sample = project()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "authored-exercise.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    if not args.install:
        return
    sessions = request("/api/director/sessions")["sessions"]
    existing = [s for s in sessions if s["brief"]["title"] == sample["brief"]["title"]]
    session = (
        existing[0]
        if existing
        else request("/api/director/sessions", envelope() | dict(brief=sample["brief"]))["session"]
    )
    detail = request("/api/director/sessions/" + session["session_id"])
    if detail.get("creative"):
        if detail["creative"]["digest"] != digest(sample["document"]):
            raise ValueError("This showcase has user edits. Preserve them; open it in Director.")
    else:
        scope = dict(
            session_id=session["session_id"],
            expected_revision=session["revision"],
            cancellation_generation=session["cancellation_generation"],
            take_id=None,
            plan_id=None,
        )
        result = request(
            "/api/director/creative",
            envelope()
            | dict(
                scope=scope,
                action="start_script",
                payload={key: sample[key] for key in ("document", "context")},
            ),
        )
        if not result.get("ok"):
            raise ValueError("The showcase was not saved: " + str(result))
    detail = request("/api/director/sessions/" + session["session_id"])
    reference = session["session_id"] + "/" + detail["creative"]["digest"]
    manifest = request("/api/director/studio/" + reference)
    program = request("/api/previs/sequence", manifest)
    for name, value in (
        ("reference.json", dict(reference=reference)),
        ("manifest.json", manifest),
        ("program.json", program),
    ):
        (OUT / name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    print("http://127.0.0.1:8766/?script=" + reference)
    print("Shot assessments:", [(s["segment_id"], s["assessment"]) for s in program["segments"]])


if __name__ == "__main__":
    main()
