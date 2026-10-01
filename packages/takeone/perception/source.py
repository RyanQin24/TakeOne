"""Which camera decides the rig is aimed, and what that camera actually is.

Tracking ran on a witness webcam on the host. That camera is not the camera
recording the film, so every take carried `aim_reference: witness_camera` and
`witness_to_lens_offset: unmeasured`: the rig could report a settled framing the
phone did not have, and nothing could measure how wrong it was.

Blackmagic REST is transport control, not video — it never hands out a frame —
so the phone's own image reaches this computer as a video device: the handset's
USB-C/HDMI Video Feed through a capture card, or Continuity Camera where the
operating system offers it. Either way it appears to the browser as an ordinary
camera, and the browser is where detection already runs.

This records which device was chosen and what the operator says it is. When it
is the phone's own feed, the aim reference becomes the taking lens and the
offset is zero because there is only one lens; when it is a separate witness
camera the old, honest caveat stands. The operator's statement is the evidence
and is labelled as such — nothing here inspects pixels to verify the claim.
"""

import copy
import json
import threading
from pathlib import Path

from takeone.paths import CONFIGS

# `phone_lens_feed` means the frames being tracked are the frames the phone's
# lens is forming. It does not mean TakeOne has read the recorded clip.
KINDS = ("witness_camera", "phone_lens_feed")
FEEDS = ("usb_hdmi_capture", "continuity_camera", "other")
MAX_TEXT = 200


def defaults():
    return dict(
        schema_version=1,
        kind="witness_camera",
        feed="other",
        device_id="",
        device_label="",
        operator_confirmed=False,
    )


def _text(value, name, limit=MAX_TEXT):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{name} must be text of at most {limit} characters.")
    return value


def validate(value):
    if not isinstance(value, dict) or set(value) != set(defaults()):
        raise ValueError("Expected the perception source fields.")
    result = dict(value)
    if result["schema_version"] != 1:
        raise ValueError("Unsupported perception source schema.")
    if result["kind"] not in KINDS:
        raise ValueError("Tracking camera must be the witness camera or the phone's own feed.")
    if result["feed"] not in FEEDS:
        raise ValueError("Unknown phone feed route.")
    for key in ("device_id", "device_label"):
        result[key] = _text(result[key], key)
    if type(result["operator_confirmed"]) is not bool:
        raise ValueError("operator_confirmed must be true or false.")
    if result["kind"] == "phone_lens_feed" and not result["operator_confirmed"]:
        # Claiming the tracked frames are the taking lens removes the offset
        # caveat from every take. It is only ever the operator's claim to make.
        raise ValueError(
            "Confirm that the selected device is the phone's own video feed before selecting it."
        )
    forbidden = ("galaxy", "s23", "live streamer cam 313")
    if result["kind"] == "phone_lens_feed" and any(
        name in result["device_label"].casefold() for name in forbidden
    ):
        raise ValueError("The cart and Galaxy cameras are not permitted as the iPhone tracking feed.")
    if result["kind"] == "witness_camera":
        result["feed"] = "other"
    return result


def aim_facts(source):
    """What a take should record about the camera that judged its framing."""
    source = validate(source)
    phone = source["kind"] == "phone_lens_feed"
    return dict(
        aim_reference="phone_lens_feed" if phone else "witness_camera",
        # One lens forming both images means there is no offset to measure.
        witness_to_lens_offset="none_same_lens" if phone else "unmeasured",
        aim_source_device=source["device_label"],
        aim_source_feed=source["feed"],
        aim_source_evidence="operator_reported",
        # The frames were tracked. The recorded clip is still unread.
        optical_framing_verified=False,
    )


class PerceptionSource:
    """The one writer of `configs/perception-source.json`."""

    def __init__(self, path=None):
        self.path = Path(path) if path else CONFIGS / "perception-source.json"
        self.lock = threading.RLock()
        stored = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else defaults()
        self.config = validate(stored)

    def status(self):
        with self.lock:
            return dict(
                schema_version=1,
                ok=True,
                source=copy.deepcopy(self.config),
                kinds=list(KINDS),
                feeds=list(FEEDS),
                **aim_facts(self.config),
            )

    def update(self, body):
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object.")
        with self.lock:
            merged = validate({**self.config, **body, "schema_version": 1})
            self.config = merged
            self.path.parent.mkdir(parents=True, exist_ok=True)
            pending = self.path.with_suffix(".tmp")
            pending.write_text(json.dumps(merged, indent=2, allow_nan=False), encoding="utf-8")
            pending.replace(self.path)
            return self.status()

    def aim_facts(self):
        with self.lock:
            return aim_facts(self.config)
