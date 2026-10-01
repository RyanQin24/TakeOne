"""Build a separate authored ensemble exercise using the existing validated example.

No model generation and no robot action. --install saves a NEW local production
through the existing Director API and compiles its simulation; it never approves
or transmits a robot plan. This is test data, not a brief-to-fixed-story generator.
"""

import argparse
import copy
import json
from pathlib import Path

from cinematic_upgrade_demo import envelope, request
from shot_language_demo import project as base_project
from takeone.asset_library.catalog import AssetCatalog
from takeone.director.contracts import ProductionBrief
from takeone.director.creative import validate_plan

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "data/asset-scenes-demo"


def project():
    sample = copy.deepcopy(base_project())
    document = sample["document"]
    title = "The prototype wakes up Â· authored ensemble exercise"
    sample["brief"].update(
        title=title,
        objective="Authored exercise: a visitor discovers a working prototype, checks the result with its maker, and attracts a third teammate. Proposed inventory and actors require confirmation.",
    )
    document.update(title=title, logline=sample["brief"]["objective"])
    document["actors"].append(dict(actor_id="observer", name="Background teammate"))
    document["questions"] = [
        "Are three performers available?",
        "Which proposed props actually exist at the location?",
    ]
    catalogue = AssetCatalog.from_project(ROOT)
    # These are authored staging requests for this exercise, not model-specific rendering code.
    dressing = [("chair", [-2.5, 3.0, 0.45], [0.5, 0.5, 0.9]), ("plant", [2.7, 3.0, 0.6], [0.6, 0.6, 1.2])]
    for scene in document["scenes"]:
        scene["location_notes"] = (
            scene["location_notes"]
            + " All added dressing and the third performer are proposed, not confirmed. Imported meshes are visualization only."
        )[:1200]
        if scene["space_id"] == "room":
            scene["cast"].append(
                dict(actor_id="observer", offset_m=[-1.1, 1.4, 0], facing_rad=-1.2, motion="hold")
            )
            for word, position, size in dressing:
                matches = catalogue.search(word, limit=1, kind="prop")
                if matches:
                    scene["objects"].append(
                        dict(
                            object_id="imported-" + word,
                            asset_id=matches[0]["asset_id"],
                            label="Proposed " + matches[0]["name"],
                            position_m=position,
                            size_m=size,
                            yaw_rad=0,
                        )
                    )
    directions = [
        (
            "Discover the space before discovering the result.",
            "Hear activity beyond the doorway, pause, and look toward the work area.",
        ),
        (
            "Move attention from the visitor to the person with the answer.",
            "Look toward the prototype, then turn toward the maker only after recognizing a change.",
        ),
        (
            "Show two people reaching the same conclusion at different moments.",
            "The maker checks the visitor first, then looks toward the prototype. The background teammate notices afterward.",
        ),
        (
            "Show the real detail that caused their reactions.",
            "Leave the prototype untouched. Let the light expose the detail without inventing a result on its surface.",
        ),
        (
            "Let a reaction carry the cut back from the insert.",
            "The visitor releases a held breath. The observer stops their own task and looks toward the maker.",
        ),
        (
            "Resolve with an intention rather than another demonstration.",
            "The visitor turns toward the next task and holds the decision. End before the next action begins.",
        ),
    ]
    for index, scene in enumerate(document["scenes"]):
        shot = scene["shots"][0]
        purpose, action = directions[index]
        shot.update(action=action, edit_intent=purpose)
        shot["design"].update(
            purpose=purpose,
            continuity="Keep the prototype fixed and preserve each performerâ€™s eyeline across cuts.",
        )
        shot["design"]["beats"][0]["action"] = action
        if index in (1, 5):
            for parameter in shot["movement"]["parameters"]:
                if parameter["name"] == "height_start_m":
                    parameter["value"] = 1.42
                elif parameter["name"] == "height_end_m":
                    parameter["value"] = 1.60
        if index == 2:
            duration = (shot["end_ms"] - shot["start_ms"]) / 1000
            actors = ["visitor", "maker", "observer"]
            actions = [
                "Check the makerâ€™s expression before looking at the prototype.",
                "Meet the visitorâ€™s look, then follow it toward the prototype.",
                "Finish the current task, look up, and notice the shared reaction.",
            ]
            shot["design"]["beats"] = [
                dict(
                    start_s=i * duration / 3,
                    end_s=(i + 1) * duration / 3,
                    actor_id=actor,
                    action=actions[i],
                    motivation="Understand what changed.",
                    emotion="Interest becomes recognition.",
                    eyeline="The other performer, then the prototype.",
                    delivery="Natural room sound; no forced line.",
                )
                for i, actor in enumerate(actors)
            ]
        if index == 4:
            shot["design"]["beats"][-1].update(
                actor_id="observer",
                action="Stop the separate task, look toward the maker, and hold. Do not mirror the lead.",
            )
    # Fresh data is validated before it can enter a persistent production.
    validate_plan(document, ProductionBrief.parse(sample["brief"]), sample["context"])
    return sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    sample = project()
    DESTINATION.mkdir(parents=True, exist_ok=True)
    (DESTINATION / "authored-exercise.json").write_text(
        json.dumps(sample, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Wrote a separate authored exercise; no AI request or physical trial.")
    if not args.install:
        return
    if any(
        session["brief"]["title"] == sample["brief"]["title"]
        for session in request("/api/director/sessions")["sessions"]
    ):
        raise ValueError(
            "An exercise with this title already exists. Preserve its edits; open it in Director."
        )
    result = request("/api/director/sessions", envelope() | dict(brief=sample["brief"]))
    session = result["session"]
    scope = dict(
        session_id=session["session_id"],
        expected_revision=session["revision"],
        cancellation_generation=session["cancellation_generation"],
        take_id=session["take_id"],
        plan_id=None,
    )
    result = request(
        "/api/director/creative",
        envelope()
        | dict(
            scope=scope, action="start_script", payload={key: sample[key] for key in ("document", "context")}
        ),
    )
    if not result.get("ok"):
        raise ValueError("The new exercise could not be saved. Existing productions were not changed.")
    detail = request("/api/director/sessions/" + session["session_id"])
    reference = session["session_id"] + "/" + detail["creative"]["digest"]
    manifest = request("/api/director/studio/" + reference)
    program = request("/api/previs/sequence", manifest)
    (DESTINATION / "compiled-program.json").write_text(json.dumps(program, indent=2), encoding="utf-8")
    print("Open http://127.0.0.1:8766/?script=" + reference)
    print("Inspect all compiler diagnostics. Successful compilation is not physical qualification.")


if __name__ == "__main__":
    main()
