"""Give natural-language direction concrete staged targets, not invented motor IDs."""

from takeone.previs.program import subject


def staged_head_targets(shot, scene, actors):
    from .studio import shot_settings

    try:
        settings, _ = shot_settings(shot)
    except ValueError as error:
        return {"available": False, "reason": str(error)}
    lead = shot.get("actor_id")
    names = {a["actor_id"]: a["name"] for a in actors}
    members = {m["actor_id"]: m for m in scene.get("cast", [])}
    ids = ([lead] if lead else []) + [a for a in members if a != lead]
    times = sorted({0, 0.5, 1, *(k["at"] for k in settings.get("channels", {}).get("actor_position_m", []))})
    targets = []
    for actor_id in ids:
        samples = []
        for at in times:
            body, _ = subject(settings, at, settings["subject_height_m"])
            position = list(body["position_m"])
            if actor_id != lead:
                member = members[actor_id]
                position = [
                    v + (position[i] if member["motion"] == "with_lead" else 0)
                    for i, v in enumerate(member["offset_m"])
                ]
            position[2] += settings["subject_height_m"] * 0.925
            samples.append({"at": at, "position_m": [round(v, 4) for v in position]})
        targets.append({"actor_id": actor_id, "name": names.get(actor_id, actor_id), "head_samples": samples})
    return {
        "available": True,
        "coordinate_frame": "shot-local XYZ metres before mark placement; Z up",
        "time": "normalized source filming time, not setup time",
        "scope": "Authored staging estimates, not live face detection. Recompute if blocking changes. Interpolate continuous camera/light target tracks; hold each speaker, move during the reply transition.",
        "targets": targets,
    }
