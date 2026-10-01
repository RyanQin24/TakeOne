"""Authored one-set benchmark: invitation, decision and visible fixed-tool contact.

The tool starts on the bench and stays there. No handoff, grasp, ownership transfer
or actual screw turn is claimed. The final proxy reach is an observable action.
"""

import copy
import math

from directing_intent_demo import actor_track, discovery, install, target
from takeone.director.cinematic import wire_settings
from takeone.previs.templates import defaults_for


def project():
    sample = discovery()
    doc = sample["document"]
    originals = [s for scene in doc["scenes"] for s in scene["shots"]]
    title = "The First Turn - fixed-tool contact (authored candidate)"
    doc.update(title=title, logline="A visitor accepts a maker's invitation and reaches the waiting tool.")
    sample["brief"].update(title=title, objective=doc["logline"])
    objects = [
        dict(
            object_id="bench",
            asset_id="table",
            label="Shared workbench",
            position_m=[0.3, -0.65, 0.5],
            size_m=[1.8, 0.6, 1.0],
            yaw_rad=0,
        ),
        dict(
            object_id="prototype",
            asset_id="plinth",
            label="Prototype housing proxy",
            position_m=[-0.15, -0.6, 1.08],
            size_m=[0.45, 0.28, 0.16],
            yaw_rad=0,
        ),
        dict(
            object_id="tool",
            asset_id="plinth",
            label="Fixed tool contact proxy",
            position_m=[-0.2, -0.45, 1.19],
            size_m=[0.12, 0.06, 0.06],
            yaw_rad=0,
        ),
    ]
    scene = dict(scene_id="first-turn", space_id="workshop", title="The waiting tool",
                 location="One assumed level workshop set", atmosphere="interior_warm",
                 location_notes="Bench, two floor marks and one fixed tool. Proxy geometry; measure before filming.",
                 objects=objects, cast=[dict(actor_id="maker", offset_m=[1.25,0,0], facing_rad=-math.pi+.65, motion="hold"),
                                      dict(actor_id="visitor", offset_m=[0,0,0], facing_rad=-math.pi/2, motion="hold")], shots=[])
    specs = [(0,4,"wide","Establish the waiting tool and the two people."),
             (4,7,"medium_close_up","The visitor notices the unfinished work."),
             (7,11,"close_up","Show the fixed tool and the detail awaiting attention."),
             (11,17,"medium","The maker invites; the visitor acknowledges."),
             (17,22,"close_up","A small head turn makes the decision visible."),
             (22,30,"medium","Reach the stationary tool and hold contact before the cut.")]
    marks = []
    for index, (start, end, framing, purpose) in enumerate(specs):
        shot = copy.deepcopy(originals[index])
        actor = "" if index == 2 else "visitor"
        template = "boom_up" if index == 1 else "static"
        shot.update(shot_id=f"turn-{index+1}", mark_id=f"turn-mark-{index+1}", actor_id=actor,
                    start_ms=start*1000, end_ms=end*1000, framing=framing, action=purpose,
                    camera_intent=purpose, edit_intent=purpose, transition="cut", lines=[], selected_line=0,
                    camera_target=dict(kind="actor" if actor else "object", target_id=actor or "tool"),
                    tracking=dict(cart="planned", phone="planned", on_loss="stop_and_hold", reason="Authored fixed-set rehearsal."),
                    capture=dict(take_id="", in_s=0), performers=[])
        settings = defaults_for(template)
        parameters = [dict(name="radius_m", value=3)]
        if template == "boom_up":
            parameters += [dict(name="height_start_m", value=1.52), dict(name="height_end_m", value=1.57)]
        shot["movement"] = dict(template_id=template, subject_motion="hold" if actor else "none",
                                parameters=parameters, cinematography=wire_settings(settings))
        shot["design"].update(
            purpose=purpose, attention=purpose, opening=purpose, ending="Hold the completed visible beat for the cut.",
            continuity="Same workbench, actors and fixed tool. No object handoff or transfer.",
            composition="two_shot" if index in (0,3) else "single" if actor else "insert",
            featured_actor_ids=["visitor","maker"] if index in (0,3) else [actor] if actor else [],
            practical_setup=scene["location_notes"], lens_policy="fit_subject", visibility="throughout",
            beats=[dict(start_s=0, end_s=end-start, actor_id=actor, action=purpose,
                        motivation="Accept the opportunity to begin.", emotion="Quiet attention.",
                        eyeline="Named target in the rehearsal.", delivery="No dialogue.")], screen_targets=[])
        for actor_id, other, heading in (("visitor","maker",-.65), ("maker","visitor",-math.pi+.65)):
            keys = [target("object", "tool", t) for t in (0,1)]
            if index in (0,3):
                keys = [target("actor", other, t) for t in (0,1)]
            gestures = []
            if index == 3 and actor_id == "maker":
                gestures = [target("forward", at=t) | dict(name="invite", weight=w)
                            for t,w in ((0,0),(.25,1),(.75,1),(1,0))]
            if index == 5 and actor_id == "visitor":
                heading = -math.pi/2
                gestures = [target("object", "tool", t) | dict(name="reach", weight=w)
                            for t,w in ((0,0),(.2,0),(.7,1),(1,1))]
            shot["performers"].append(actor_track(actor_id, heading, keys, gestures))
        scene["shots"].append(shot)
        marks.append(dict(mark_id=shot["mark_id"], scene_id=scene["scene_id"],
                          description="Visitor floor mark, fixed across the edit.", position_m=[0,0], facing_rad=-math.pi/2))
    doc.update(scenes=[scene], marks=marks)
    doc["visual_style"].update(
        visual_rules="One workshop and one fixed tool. Establish attention, invitation, decision, then contact.",
        palette="Rust visitor outfit, dark maker outfit and a neutral workbench.",
        lighting="Soft warm workshop preview; qualify actual light separately.",
        wardrobe="Visitor in rust, maker in dark blue. Persistent outfits across every shot.",
        sound="Quiet workshop room tone. No generated or recorded sound is part of this rehearsal.",
        continuity_locks=["The tool remains on the workbench.", "Actor marks and outfits remain fixed.",
                          "The final hand reaches the tool; no grasp, transfer or screw turn is simulated."],
    )
    sample["adaptation"] = "The original proposed handoff is replaced explicitly with a waiting fixed tool and an invitation gesture."
    return sample


if __name__ == "__main__":
    install(project(), "first-turn")
