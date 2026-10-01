"""Optional authored screen-space requirements; empty lists preserve old direction."""


def schema():
    from .creative import array, obj, string

    unit = dict(type="number", minimum=0, maximum=1)
    pair = array(unit, 2, 2)
    return array(
        obj(
            kind=dict(type="string", enum=["actor", "object"]),
            target_id=string(40),
            region=dict(type="string", enum=["face", "body", "object"]),
            start_at=unit,
            end_at=unit,
            center_uv=pair,
            tolerance_uv=pair,
            height_range=pair,
            min_visible_s=dict(type="number", minimum=0, maximum=600),
            allow_occlusion=dict(type="boolean"),
            allow_crop=dict(type="boolean"),
            allowed_foreground_actor_ids=array(string(40), 0, 6),
        ),
        0,
        12,
    )


def validate_links(document):
    for scene in document["scenes"]:
        cast = {m["actor_id"] for m in scene.get("cast", [])}
        objects = {o["object_id"] for o in scene.get("objects", [])}
        for shot in scene["shots"]:
            actors = cast | ({shot["actor_id"]} if shot["actor_id"] else set())
            for contract in shot.get("design", {}).get("screen_targets", []):
                if "space_id" not in scene:
                    raise ValueError("Screen contracts require explicit scene-local coordinates.")
                available = actors if contract["kind"] == "actor" else objects
                if contract["target_id"] not in available:
                    raise ValueError("Screen targets must name a staged actor or scene object.")
                if (contract["kind"] == "object") != (contract["region"] == "object"):
                    raise ValueError("Object regions need an object target; face/body regions need an actor.")
                if not contract["start_at"] <= contract["end_at"]:
                    raise ValueError("Screen interval end must not precede its start.")
                if contract["height_range"][0] > contract["height_range"][1]:
                    raise ValueError("Screen subject-size minimum must not exceed its maximum.")
                allowed = contract["allowed_foreground_actor_ids"]
                if len(allowed) != len(set(allowed)) or not set(allowed) <= actors:
                    raise ValueError("Allowed foreground people must be distinct staged actor IDs.")


def catalog():
    return dict(
        coordinates="Normalized screen UV, (0,0) top-left and (1,1) bottom-right.",
        timebase="Full-take filming fractions, excluding setup. Checks use only the edited source window.",
        visibility="Sampled line of sight to face/object center against oriented box proxies. "
        "This does not establish pixel visibility, readable text or complete mesh clearance.",
        dwell="Longest consecutive fully contained, unoccluded sampled interval; no hold-frame footage is invented.",
        exceptions="Explicit allow_crop, allow_occlusion and allowed_foreground_actor_ids retain artistic exceptions.",
    )
