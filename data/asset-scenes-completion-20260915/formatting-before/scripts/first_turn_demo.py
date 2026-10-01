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
        dict(object_id="bench", asset_id="table", label="Shared workbench", position_m=[.3,-.65,.5],
             size_m=[1.8,.6,1.0], yaw_rad=0),
        dict(object_id="prototype", asset_id="plinth", label="Prototype housing proxy", position_m=[-.15,-.6,1.08],
             size_m=[.45,.28,.16], yaw_rad=0),
        dict(object_id="tool", asset_id="plinth", label="Fixed tool contact proxy", position_m=[-.2,-.45,1.19],
             size_m=[.12,.06,.06], yaw_rad=0),
    ]
