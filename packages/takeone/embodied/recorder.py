"""The two-method recorder `BehaviorManager` expects, over `RecordingService`.

`BehaviorManager` calls exactly `start(plan_id, goal, behavior_id) -> take_id`
and `stop(take_id, reason)`. `RecordingService.start` wants a request identity,
a context and a source. Bridging those two is this file's whole job.

Request identities are derived, not generated: a duplicated settle event has to
replay idempotently through `recording_operations` instead of opening a second
take. The codebase already uses `uuid5` over a namespace for Director operation
identities, and this follows that pattern.
"""

from uuid import NAMESPACE_URL, uuid5

from takeone.recording.contracts import RecordingError
from takeone.voice.contracts import VoiceScope
from takeone.voice.service import MUTATION_TTL_NS, VoiceServiceError

RECORDER_OPERATIONS = uuid5(NAMESPACE_URL, "https://takeone.local/recording/behavior-operations")


def start_request_id(behavior_id, plan_id):
    return str(uuid5(RECORDER_OPERATIONS, f"{behavior_id}:{plan_id}"))


def stop_request_id(take_id, reason):
    return str(uuid5(RECORDER_OPERATIONS, f"stop:{take_id}:{reason}"))


class BehaviorRecordingAdapter:
    def __init__(
        self,
        service,
        *,
        source="phone",
        aim_reference="witness_camera",
        motion_source=None,
        bridge=None,
        perception_source=None,
    ):
        self.service = service
        self.source = source
        # Every take records which camera decided it was settled. That is a
        # separate camera from the taking lens unless the operator has routed
        # the phone's own video feed into this computer and said so, which is
        # what `perception_source` answers.
        self.aim_reference = aim_reference
        self.perception_source = perception_source
        self.motion_source = motion_source
        self.bridge = bridge
        self.owner = None

    def _aim_facts(self):
        if self.perception_source is None:
            return {
                "aim_reference": self.aim_reference,
                "witness_to_lens_offset": "unmeasured",
            }
        return self.perception_source.aim_facts()

    def bind_owner(self, token, envelope, motion_source):
        self.owner = (token, envelope[0], envelope[1].wire())
        self.motion_source = motion_source

    def context(self, plan_id, goal, behavior_id):
        wire = goal.wire()
        return {
            "source": "embodied_behavior",
            "behavior_id": behavior_id,
            "plan_id": plan_id,
            "subject_track_ids": list(wire["subject_track_ids"]),
            "screen_target_uv": list(wire["screen_target_uv"]),
            "desired_subject_size_range": list(wire["desired_subject_size_range"]),
            "camera_relation": wire["camera_relation"],
            "recording_policy": wire["recording_policy"],
            "motion_source": self.motion_source,
            **self._aim_facts(),
            "identity_scope": "transient_visual_tracks_not_person_identity",
        }

    def start(self, plan_id, goal, behavior_id):
        request_id = start_request_id(behavior_id, plan_id)
        try:
            if self.bridge is not None:
                if self.owner is None:
                    return None
                token, session_id, scope = self.owner
                authority = self.bridge.voice.recording_authority(token)
                state = authority["snapshot"]
                if authority["voice_session_id"] != session_id or state["scope"] != scope:
                    return None
                envelope = (
                    session_id,
                    VoiceScope(**scope),
                    state["generation"],
                    self.bridge.voice.clock() + MUTATION_TTL_NS,
                )
                response = self.bridge.mutate(
                    "start",
                    token,
                    envelope,
                    request_id,
                    source=self.source,
                    plan_id=plan_id,
                    behavior_context=self.context(plan_id, goal, behavior_id),
                )
                take = self.service.get(response["take"]["take_id"])
                return take["take_id"] if take["state"] in {"starting", "recording"} else None
            snapshot = self.service.start(
                request_id,
                self.context(plan_id, goal, behavior_id),
                None,
                source=self.source,
                plan_id=plan_id if isinstance(plan_id, str) and len(plan_id) == 64 else None,
            )
        except (RecordingError, VoiceServiceError):
            # BehaviorManager maps a missing take identity to recording_rejected.
            return None
        return snapshot.get("take_id") if isinstance(snapshot, dict) else None

    def stop(self, take_id, reason):
        try:
            # The reason travels into the event detail, so `target_lost:person-0004`
            # survives into the evidence trail rather than being flattened.
            self.service.stop(take_id, stop_request_id(take_id, reason))
        except RecordingError:
            return None
        return take_id
