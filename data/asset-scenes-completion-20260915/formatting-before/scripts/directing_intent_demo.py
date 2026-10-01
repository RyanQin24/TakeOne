"""Separate authored directing-intent candidates. No provider call or robot action."""

import argparse
import copy
import json
import math
from pathlib import Path

from cinematic_upgrade_demo import envelope, request
from takeone.director.performers import PALETTE

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "data/directing-intent-candidates-20260915"


def target(kind, target_id="", at=0, point=None, ease="smooth"):
    return dict(at=at, kind=kind, target_id=target_id, point_m=point or [0, 0, 0], ease=ease)


def actor_track(actor_id, heading, keys, gestures=None):
    return dict(actor_id=actor_id,
                body_heading_rad=[dict(at=t, value=heading, ease="smooth") for t in (0, 1)],
                look_at=keys, gestures=gestures or [])


def discovery():
    source = json.loads((ROOT / "data/shot-language-20260915/final-script.json").read_text(encoding="utf-8"))
    doc = copy.deepcopy(source["document"])
    doc["title"] = "A small discovery - visible interaction (authored candidate)"
    for actor in doc["actors"]:
        actor["appearance"] = PALETTE | dict(cloth="#17263c" if actor["actor_id"] == "maker" else "#b95f3e")
    for scene in doc["scenes"]:
        for shot in scene["shots"]:
            if shot["shot_id"] == "shot-2":
                values = {p["name"]: p["value"] for p in shot["movement"]["parameters"]}
                values.update(height_start_m=1.52, height_end_m=1.57)
                shot["movement"]["parameters"] = [dict(name=k, value=v) for k, v in values.items()]
            if shot["shot_id"] in ("shot-2", "shot-5"):
                for member in scene["cast"]:
                    if member["actor_id"] == "maker":
                        member["offset_m"] = [2.5, 0, 0]
            if shot["shot_id"] != "shot-3":
                continue
            scene["objects"].append(dict(object_id="shared-bench", asset_id="table", label="Shared workbench",
                position_m=[0.45, -0.5, 0.4], size_m=[1.4, 0.6, 0.8], yaw_rad=0))
            channels = shot["movement"]["cinematography"]["channels"]
            channels["gaze_yaw_rad"], channels["gaze_pitch_rad"] = [], []
            shot["performers"] = []
            for actor_id, other, heading in (("visitor", "maker", -0.65), ("maker", "visitor", -math.pi + 0.65)):
                keys = [target("actor", other, 0), target("actor", other, 0.5),
                        target("point", at=0.85, point=[0.45, -0.5, 0.8]),
                        target("point", at=1, point=[0.45, -0.5, 0.8])]
                shot["performers"].append(actor_track(actor_id, heading, keys))
    brief = dict(title=doc["title"], duration_ms=30000, aspect_ratio="16:9",
                 objective="Authored comparison with the preserved exercise: a real boom, distinct wardrobe and mutual attention.")
    return dict(brief=brief, document=doc, context=source["context"],
                source_document_digest=source["digest"], provenance="authored_candidate_not_model_generated")


def install(sample, name):
    destination = DESTINATION / name
    destination.mkdir(parents=True, exist_ok=True)
    installed = destination / "installed.json"
    if installed.exists():
        raise ValueError("This candidate is already installed; preserve its saved revision.")
    (destination / "authored.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    session = request("/api/director/sessions", envelope() | dict(brief=sample["brief"]))["session"]
    scope = dict(session_id=session["session_id"], expected_revision=session["revision"],
                 cancellation_generation=session["cancellation_generation"],
                 take_id=session["take_id"], plan_id=None)
    request("/api/director/creative", envelope() | dict(scope=scope, action="start_script",
            payload={k: sample[k] for k in ("document", "context")}))
    detail = request("/api/director/sessions/" + session["session_id"])
    ref = session["session_id"] + "/" + detail["creative"]["digest"]
    manifest = request("/api/director/studio/" + ref)
    program = request("/api/previs/sequence", manifest)
    installed.write_text(json.dumps(dict(reference=ref, program=program), indent=2), encoding="utf-8")
    print("http://127.0.0.1:8766/?script=" + ref)
    print("needs_revision:", program["needs_revision_shot_ids"])
    return ref, program


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    sample = discovery()
    if args.install:
        install(sample, "discovery")
    else:
        print(json.dumps(sample, indent=2))


if __name__ == "__main__":
    main()
