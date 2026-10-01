import unittest
from dataclasses import FrozenInstanceError
from uuid import UUID

from takeone.voice import RecordingEvent, VoiceScope, VoiceState

RUNTIME_ID = "10000000-0000-4000-8000-000000000001"
SESSION_ID = "20000000-0000-4000-8000-000000000002"
TAKE_ID = "30000000-0000-4000-8000-000000000003"
PLAN_ID = "a" * 64


class Clock:
    def __init__(self, now_ns=1_000):
        self.now_ns = now_ns

    def __call__(self):
        return self.now_ns


class VoiceStateTests(unittest.TestCase):
    def test_generation_exhaustion_retires_without_overflow_and_reconciles_latch(self):
        from takeone.voice.contracts import MAX_INTEGER

        for mode in ("offline", "live"):
            with self.subTest(mode=mode):
                scope = VoiceScope(RUNTIME_ID, SESSION_ID, 0, MAX_INTEGER, None, None)
                state = VoiceState(scope, mode=mode, clock=self.clock)
                state.observe_recording(self.event(0, "idle", scope=scope, source="recorder"))
                state.begin("last")
                state.observe_recording(self.event(1, "requested", scope=scope, source="recorder"))
                retired = state.snapshot()
                self.assertEqual(retired["generation"], MAX_INTEGER)
                self.assertTrue(retired["quiet"])
                self.assertTrue(retired["recording_latch_active"])
                if mode == "live":
                    state.observe_recording(self.event(2, "stopped", scope=scope))
                    self.assertTrue(state.snapshot()["recording_latch_active"])
                state.observe_recording(self.event(2, "stopped", scope=scope, source="recorder"))
                self.assertFalse(state.snapshot()["recording_latch_active"])
                self.assertTrue(state.snapshot()["quiet"])
                with self.assertRaises(RuntimeError):
                    state.begin("overflow")

    def setUp(self):
        self.clock = Clock()
        self.scope = VoiceScope(RUNTIME_ID, SESSION_ID, 2, 4, PLAN_ID, TAKE_ID)

    def event(
        self,
        sequence,
        state,
        *,
        scope=None,
        source="fixture",
        observed_ns=900,
        expires_ns=2_000,
    ):
        return RecordingEvent(
            scope or self.scope,
            sequence,
            state,
            source,
            observed_ns,
            expires_ns,
        )

    @staticmethod
    def alternate_scope(index):
        return VoiceScope(
            RUNTIME_ID,
            str(UUID(int=10_000 + index)),
            index,
            index,
            PLAN_ID,
            None,
        )

    def test_scope_is_immutable_and_serializes_explicit_identity(self):
        scope = VoiceScope(RUNTIME_ID, SESSION_ID, 2, 4, PLAN_ID, TAKE_ID)

        self.assertEqual(
            scope.wire(),
            {
                "runtime_epoch": RUNTIME_ID,
                "session_id": SESSION_ID,
                "revision": 2,
                "cancellation_generation": 4,
                "plan_id": PLAN_ID,
                "take_id": TAKE_ID,
            },
        )
        with self.assertRaises(FrozenInstanceError):
            scope.revision = 3

    def test_scope_rejects_noncanonical_or_unbounded_identity_fields(self):
        invalid_fields = (
            ("runtime_epoch", "ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF"),
            ("runtime_epoch", "not-a-uuid"),
            ("session_id", None),
            ("revision", True),
            ("revision", -1),
            ("cancellation_generation", -1),
            ("plan_id", "A" * 64),
            ("plan_id", "a" * 63),
            ("take_id", "not-a-uuid"),
        )
        valid = {
            "runtime_epoch": RUNTIME_ID,
            "session_id": SESSION_ID,
            "revision": 2,
            "cancellation_generation": 4,
            "plan_id": PLAN_ID,
            "take_id": TAKE_ID,
        }

        for name, value in invalid_fields:
            with self.subTest(name=name, value=value):
                fields = {**valid, name: value}
                with self.assertRaises(ValueError):
                    VoiceScope(**fields)

    def test_recording_event_validates_and_serializes_wire_fields(self):
        scope = VoiceScope(RUNTIME_ID, SESSION_ID, 2, 4, PLAN_ID, TAKE_ID)
        event = RecordingEvent(scope, 7, "recording", "recorder", 900, 2_000)

        self.assertEqual(
            event.wire(),
            {
                "scope": scope.wire(),
                "sequence": 7,
                "state": "recording",
                "source": "recorder",
                "observed_monotonic_ns": 900,
                "expires_monotonic_ns": 2_000,
            },
        )

        invalid_fields = (
            ("scope", scope.wire()),
            ("sequence", True),
            ("sequence", -1),
            ("state", "paused"),
            ("state", []),
            ("source", "camera"),
            ("source", []),
            ("observed_monotonic_ns", -1),
            ("expires_monotonic_ns", 900),
        )
        valid = {
            "scope": scope,
            "sequence": 7,
            "state": "recording",
            "source": "recorder",
            "observed_monotonic_ns": 900,
            "expires_monotonic_ns": 2_000,
        }
        for name, value in invalid_fields:
            with self.subTest(name=name, value=value):
                fields = {**valid, name: value}
                with self.assertRaises(ValueError):
                    RecordingEvent(**fields)

    def test_recording_request_closes_gate_and_rejects_outstanding_reply(self):
        clock = Clock()
        scope = VoiceScope(RUNTIME_ID, SESSION_ID, 2, 4, PLAN_ID, TAKE_ID)
        state = VoiceState(scope, mode="offline", clock=clock)

        state.observe_recording(RecordingEvent(scope, 0, "idle", "fixture", 900, 2_000))
        generation = state.begin("request-one")
        state.observe_recording(RecordingEvent(scope, 1, "requested", "fixture", 950, 2_000))

        self.assertTrue(state.snapshot()["quiet"])
        self.assertFalse(state.complete("request-one", generation, "Old reply", source="fixture"))
        self.assertEqual(state.snapshot()["transcript"], [])

    def test_initial_state_needs_fresh_recording_authority(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)

        self.assertEqual(
            state.snapshot(),
            {
                "scope": self.scope.wire(),
                "mode": "offline",
                "generation": 4,
                "quiet": True,
                "quiet_reason": "recording_state_unknown",
                "recording_latch_active": False,
                "pending_request_id": None,
                "transcript": [],
                "transcript_bytes": 0,
            },
        )
        state.observe_recording(self.event(0, "idle", observed_ns=1_001, expires_ns=2_000))
        state.observe_recording(self.event(1, "idle", observed_ns=800, expires_ns=1_000))
        self.assertTrue(state.snapshot()["quiet"])

        state.observe_recording(self.event(2, "idle"))
        self.assertFalse(state.snapshot()["quiet"])

    def test_live_mode_does_not_trust_fixture_evidence_to_open_gate(self):
        state = VoiceState(self.scope, mode="live", clock=self.clock)

        state.observe_recording(self.event(0, "idle"))
        self.assertTrue(state.snapshot()["quiet"])

        state.observe_recording(self.event(1, "idle", source="recorder"))
        self.assertFalse(state.snapshot()["quiet"])

    def test_live_fixture_does_not_consume_recorder_sequence(self):
        state = VoiceState(self.scope, mode="live", clock=self.clock)

        state.observe_recording(self.event(99, "idle"))
        state.observe_recording(self.event(1, "idle", source="recorder"))

        self.assertFalse(state.snapshot()["quiet"])

    def test_live_fixture_stop_cannot_release_recorder_latch(self):
        state = VoiceState(self.scope, mode="live", clock=self.clock)
        state.observe_recording(self.event(0, "idle", source="recorder"))
        state.observe_recording(self.event(1, "requested", source="recorder"))

        state.observe_recording(self.event(2, "stopped", source="fixture"))
        self.assertTrue(state.snapshot()["quiet"])

        state.observe_recording(self.event(2, "stopped", source="recorder"))
        self.assertFalse(state.snapshot()["quiet"])

    def test_all_uncertain_and_active_recording_states_latch_gate(self):
        for recording_state in ("requested", "starting", "recording", "finalizing", "unknown"):
            with self.subTest(recording_state=recording_state):
                state = VoiceState(self.scope, mode="offline", clock=self.clock)
                state.observe_recording(self.event(0, "idle"))
                state.observe_recording(self.event(1, recording_state))
                state.observe_recording(self.event(2, "idle"))
                self.assertTrue(state.snapshot()["quiet"])

    def test_expired_authority_cannot_be_replayed_with_a_new_deadline(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(4, "idle", expires_ns=1_100))
        self.clock.now_ns = 1_100
        self.assertTrue(state.snapshot()["quiet"])

        state.observe_recording(self.event(4, "idle", observed_ns=900, expires_ns=2_000))

        self.assertTrue(state.snapshot()["quiet"])

    def test_latched_recording_rejects_idle_stale_and_unfresh_stop(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(2, "idle"))
        state.observe_recording(self.event(3, "requested"))

        state.observe_recording(self.event(4, "idle"))
        state.observe_recording(self.event(2, "stopped"))
        state.observe_recording(self.event(5, "stopped", observed_ns=1_001, expires_ns=2_000))
        state.observe_recording(self.event(6, "stopped", observed_ns=800, expires_ns=1_000))
        self.assertTrue(state.snapshot()["quiet"])

        state.observe_recording(self.event(7, "stopped"))
        self.assertFalse(state.snapshot()["quiet"])

    def test_scope_change_does_not_relabel_or_bypass_old_recording_latch(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        state.observe_recording(self.event(1, "recording"))
        revised = VoiceScope(RUNTIME_ID, SESSION_ID, 3, 5, PLAN_ID, None)

        state.set_scope(revised)
        self.assertTrue(state.snapshot()["recording_latch_active"])
        state.observe_recording(self.event(2, "stopped", scope=revised))
        self.assertTrue(state.snapshot()["quiet"])

        state.observe_recording(self.event(2, "stopped"))
        self.assertTrue(state.snapshot()["quiet"])

        state.observe_recording(self.event(3, "stopped", scope=revised))
        self.assertFalse(state.snapshot()["quiet"])
        self.assertFalse(state.snapshot()["recording_latch_active"])

    def test_expired_observation_does_not_hide_recording_latch(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(1, "recording", expires_ns=1_100))

        self.clock.now_ns = 1_100
        snapshot = state.snapshot()

        self.assertEqual(snapshot["quiet_reason"], "recording_observation_expired")
        self.assertTrue(snapshot["recording_latch_active"])

    def test_cleared_old_latch_cannot_be_recreated_by_replayed_event(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        state.observe_recording(self.event(1, "requested"))
        state.observe_recording(self.event(4, "recording"))
        revised = VoiceScope(RUNTIME_ID, SESSION_ID, 3, 5, PLAN_ID, None)
        state.set_scope(revised)
        state.observe_recording(self.event(5, "stopped"))

        state.set_scope(self.scope)
        state.observe_recording(self.event(4, "recording"))
        state.observe_recording(self.event(6, "idle"))

        self.assertFalse(state.snapshot()["quiet"])

    def test_scope_revision_invalidates_pending_work_and_requires_new_evidence(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        generation = state.begin("request-one")
        revised = VoiceScope(RUNTIME_ID, SESSION_ID, 3, 5, PLAN_ID, TAKE_ID)

        snapshot = state.set_scope(revised)

        self.assertTrue(snapshot["quiet"])
        self.assertEqual(snapshot["scope"], revised.wire())
        self.assertEqual(snapshot["generation"], 5)
        self.assertIsNone(snapshot["pending_request_id"])
        self.assertFalse(state.complete("request-one", generation, "Old", source="fixture"))
        state.observe_recording(self.event(1, "idle", scope=revised))
        self.assertFalse(state.snapshot()["quiet"])

    def test_state_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            VoiceState(self.scope, mode="automatic", clock=self.clock)

    def test_snapshot_expires_authority_and_invalidates_pending_reply_once(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle", expires_ns=1_100))
        generation = state.begin("request-one")

        self.clock.now_ns = 1_100
        expired = state.snapshot()

        self.assertTrue(expired["quiet"])
        self.assertEqual(expired["quiet_reason"], "recording_observation_expired")
        self.assertEqual(expired["generation"], 5)
        self.assertIsNone(expired["pending_request_id"])
        self.assertFalse(state.complete("request-one", generation, "Late", source="fixture"))
        self.assertEqual(state.snapshot()["generation"], 5)

    def test_begin_checks_recording_authority_deadline(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle", expires_ns=1_100))

        self.clock.now_ns = 1_100

        with self.assertRaises(RuntimeError):
            state.begin("request-one")
        self.assertEqual(state.snapshot()["quiet_reason"], "recording_observation_expired")

    def test_complete_checks_recording_authority_deadline(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle", expires_ns=1_100))
        generation = state.begin("request-one")

        self.clock.now_ns = 1_100

        self.assertFalse(state.complete("request-one", generation, "Late", source="fixture"))
        self.assertEqual(state.snapshot()["generation"], 5)
        self.assertIsNone(state.snapshot()["pending_request_id"])

    def test_wrong_completion_cannot_consume_current_request(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        generation = state.begin("request-one")

        self.assertFalse(state.complete("request-two", generation, "Wrong ID", source="fixture"))
        self.assertFalse(state.complete("request-one", generation + 1, "Wrong generation", source="fixture"))
        self.assertEqual(state.snapshot()["pending_request_id"], "request-one")
        self.assertTrue(state.complete("request-one", generation, "Current", source="fixture"))

    def test_boolean_generation_cannot_match_integer_generation(self):
        scope = VoiceScope(RUNTIME_ID, SESSION_ID, 2, 1, PLAN_ID, TAKE_ID)
        state = VoiceState(scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle", scope=scope))
        state.begin("request-one")

        self.assertFalse(state.complete("request-one", True, "Wrong", source="fixture"))
        self.assertEqual(state.snapshot()["pending_request_id"], "request-one")

    def test_interrupt_invalidates_only_one_pending_request(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        generation = state.begin("request-one")

        interrupted = state.interrupt("creator spoke")

        self.assertEqual(interrupted["generation"], 5)
        self.assertIsNone(interrupted["pending_request_id"])
        self.assertFalse(state.complete("request-one", generation, "Late", source="fixture"))
        self.assertEqual(state.interrupt("again")["generation"], 5)

    def test_request_identity_cannot_be_repeated_or_queued(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        state.begin("request-one")

        with self.assertRaises(RuntimeError):
            state.begin("request-two")
        state.interrupt("replace question")
        with self.assertRaises(ValueError):
            state.begin("request-one")

    def test_request_and_interrupt_inputs_are_bounded_text(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))

        for request_id in (None, "", " ", "x" * 201):
            with self.subTest(request_id=request_id):
                with self.assertRaises(ValueError):
                    state.begin(request_id)
        state.begin("request-one")
        for reason in (None, "", " ", "x" * 201):
            with self.subTest(reason=reason):
                with self.assertRaises(ValueError):
                    state.interrupt(reason)

    def test_transcript_preserves_exact_fragments_intervals_and_source(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)

        state.append_transcript("creator", "  Hello ", 0, 125)
        state.append_transcript("creator", "world  ", 125, 250)
        state.append_transcript("creator", "", 250, 250)

        self.assertEqual(
            state.snapshot()["transcript"],
            [
                {
                    "speaker": "creator",
                    "text": "  Hello ",
                    "start_ms": 0,
                    "end_ms": 125,
                    "source": "fixture",
                },
                {
                    "speaker": "creator",
                    "text": "world  ",
                    "start_ms": 125,
                    "end_ms": 250,
                    "source": "fixture",
                },
            ],
        )
        self.assertEqual(state.snapshot()["transcript_bytes"], 15)

    def test_live_and_system_transcripts_have_explicit_provenance(self):
        state = VoiceState(self.scope, mode="live", clock=self.clock)

        state.append_transcript("creator", "Question", 10, 20)
        state.append_transcript("system", "Disconnected", 20, 20)

        transcript = state.snapshot()["transcript"]
        self.assertEqual(transcript[0]["source"], "live")
        self.assertEqual(transcript[1]["source"], "system")

    def test_transcript_rejects_invalid_speaker_text_or_interval(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        invalid = (
            ("operator", "text", 0, 1),
            (None, "text", 0, 1),
            ([], "text", 0, 1),
            ("creator", None, 0, 1),
            ("creator", "text", True, 1),
            ("creator", "text", 0.0, 1),
            ("creator", "text", float("nan"), 1),
            ("creator", "text", float("inf"), 1),
            ("creator", "text", -1, 1),
            ("creator", "text", 2, 1),
            ("creator", "text", 0, 2**63),
        )

        for speaker, text, start_ms, end_ms in invalid:
            with self.subTest(speaker=speaker, text=text, start_ms=start_ms, end_ms=end_ms):
                with self.assertRaises(ValueError):
                    state.append_transcript(speaker, text, start_ms, end_ms)
        self.assertEqual(state.snapshot()["transcript"], [])

    def test_unicode_fragment_uses_utf8_byte_limit(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        exactly_16_kib = "🎬" * 4_096

        state.append_transcript("director", exactly_16_kib, 0, 1)

        self.assertEqual(state.snapshot()["transcript_bytes"], 16_384)
        with self.assertRaises(ValueError):
            state.append_transcript("director", exactly_16_kib + "x", 1, 2)

    def test_transcript_evicts_old_fragments_at_entry_and_byte_bounds(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        for index in range(33):
            state.append_transcript("creator", f"fragment-{index:02}", index, index + 1)

        snapshot = state.snapshot()
        self.assertEqual(len(snapshot["transcript"]), 32)
        self.assertEqual(snapshot["transcript"][0]["text"], "fragment-01")

        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.append_transcript("creator", "a" * 16_384, 0, 1)
        state.append_transcript("creator", "b" * 16_384, 1, 2)
        state.append_transcript("creator", "c", 2, 3)
        snapshot = state.snapshot()
        self.assertEqual([item["text"][0] for item in snapshot["transcript"]], ["b", "c"])
        self.assertEqual(snapshot["transcript_bytes"], 16_385)

    def test_snapshot_transcript_cannot_mutate_owned_state(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.append_transcript("creator", "Original", 0, 1)

        snapshot = state.snapshot()
        snapshot["transcript"][0]["text"] = "Changed"

        self.assertEqual(state.snapshot()["transcript"][0]["text"], "Original")

    def test_current_completion_appends_bounded_source_labelled_reply(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        generation = state.begin("request-one")

        self.assertTrue(
            state.complete(
                "request-one",
                generation,
                "  Say cut, then stop.  ",
                source="fixture",
            )
        )

        self.assertFalse(state.snapshot()["quiet"])
        self.assertEqual(
            state.snapshot()["transcript"],
            [
                {
                    "speaker": "director",
                    "text": "  Say cut, then stop.  ",
                    "start_ms": None,
                    "end_ms": None,
                    "source": "fixture",
                }
            ],
        )

    def test_invalid_completion_does_not_consume_pending_request(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        generation = state.begin("request-one")

        for text, source in ((None, "fixture"), ("", "fixture"), ("Reply", "provider")):
            with self.subTest(text=text, source=source):
                with self.assertRaises(ValueError):
                    state.complete("request-one", generation, text, source=source)
        with self.assertRaises(ValueError):
            state.complete("request-one", generation, "x" * 16_385, source="fixture")
        self.assertEqual(state.snapshot()["pending_request_id"], "request-one")

    def test_completion_source_must_match_voice_mode(self):
        for mode, evidence_source, wrong_source in (
            ("offline", "fixture", "live"),
            ("live", "recorder", "fixture"),
        ):
            with self.subTest(mode=mode):
                state = VoiceState(self.scope, mode=mode, clock=self.clock)
                state.observe_recording(self.event(0, "idle", source=evidence_source))
                generation = state.begin(f"request-{mode}")

                with self.assertRaises(ValueError):
                    state.complete(f"request-{mode}", generation, "Wrong provenance", source=wrong_source)
                self.assertEqual(state.snapshot()["pending_request_id"], f"request-{mode}")

    def test_one_uninterrupted_speaker_still_obeys_fragment_bound(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)

        for index in range(40):
            state.append_transcript("director", str(index), index, index + 1)

        self.assertEqual(len(state.snapshot()["transcript"]), 32)
        self.assertEqual(state.snapshot()["transcript"][0]["text"], "8")

    def test_request_history_pressure_rejects_late_and_repeated_identity(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        first_generation = state.begin("request-0")
        self.assertTrue(state.complete("request-0", first_generation, "reply-0", source="fixture"))

        for index in range(1, 40):
            generation = state.begin(f"request-{index}")
            self.assertTrue(
                state.complete(f"request-{index}", generation, f"reply-{index}", source="fixture")
            )

        self.assertEqual(len(state.snapshot()["transcript"]), 32)
        self.assertFalse(state.complete("request-0", first_generation, "late reply", source="fixture"))
        with self.assertRaises(ValueError):
            state.begin("request-0")

    def test_request_identity_limit_retires_state_closed(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        first_generation = None
        for index in range(1_024):
            generation = state.begin(f"request-{index}")
            if index == 0:
                first_generation = generation
            self.assertTrue(state.complete(f"request-{index}", generation, "reply", source="fixture"))

        with self.assertRaises(RuntimeError):
            state.begin("request-over-limit")

        snapshot = state.snapshot()
        self.assertTrue(snapshot["quiet"])
        self.assertEqual(snapshot["quiet_reason"], "request_history_exhausted")
        self.assertFalse(state.complete("request-0", first_generation, "late reply", source="fixture"))
        with self.assertRaises(ValueError):
            state.begin("request-0")
        with self.assertRaises(RuntimeError):
            state.begin("another-request")
        state.observe_recording(self.event(1, "stopped"))
        self.assertEqual(state.snapshot()["quiet_reason"], "request_history_exhausted")

    def test_scope_history_pressure_rejects_replayed_recording_event(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        original_idle = self.event(0, "idle")
        state.observe_recording(original_idle)

        for index in range(1, 40):
            scope = self.alternate_scope(index)
            state.set_scope(scope)
            state.observe_recording(self.event(0, "idle", scope=scope))

        state.set_scope(self.scope)
        state.observe_recording(original_idle)
        self.assertTrue(state.snapshot()["quiet"])

        state.observe_recording(self.event(1, "idle"))
        self.assertFalse(state.snapshot()["quiet"])

    def test_scope_identity_limit_retires_state_closed(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        for index in range(1, 256):
            scope = self.alternate_scope(index)
            state.set_scope(scope)
            state.observe_recording(self.event(0, "idle", scope=scope))

        overflow = self.alternate_scope(256)
        state.set_scope(overflow)
        exhausted = state.observe_recording(self.event(0, "idle", scope=overflow))

        self.assertTrue(exhausted["quiet"])
        self.assertEqual(exhausted["quiet_reason"], "scope_history_exhausted")
        with self.assertRaises(RuntimeError):
            state.set_scope(self.scope)
        state.observe_recording(self.event(1, "stopped", scope=overflow))
        self.assertEqual(state.snapshot()["quiet_reason"], "scope_history_exhausted")

    def test_unrelated_scope_does_not_exhaust_history_at_limit(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        current = self.scope
        for index in range(1, 256):
            current = self.alternate_scope(index)
            state.set_scope(current)
            state.observe_recording(self.event(0, "idle", scope=current))

        unrelated = self.alternate_scope(256)
        ignored = state.observe_recording(self.event(0, "idle", scope=unrelated))

        self.assertFalse(ignored["quiet"])
        self.assertIsNone(ignored["quiet_reason"])
        self.assertEqual(ignored["scope"], current.wire())

    def test_live_fixture_does_not_exhaust_current_scope_history_at_limit(self):
        state = VoiceState(self.scope, mode="live", clock=self.clock)
        state.observe_recording(self.event(0, "idle", source="recorder"))
        for index in range(1, 256):
            scope = self.alternate_scope(index)
            state.set_scope(scope)
            state.observe_recording(self.event(0, "idle", scope=scope, source="recorder"))

        overflow = self.alternate_scope(256)
        state.set_scope(overflow)
        ignored = state.observe_recording(self.event(0, "idle", scope=overflow))

        self.assertTrue(ignored["quiet"])
        self.assertEqual(ignored["quiet_reason"], "scope_changed")

        exhausted = state.observe_recording(self.event(0, "idle", scope=overflow, source="recorder"))
        self.assertEqual(exhausted["quiet_reason"], "scope_history_exhausted")

    def test_scope_exhaustion_latches_relevant_active_event_until_matching_stop(self):
        state = VoiceState(self.scope, mode="offline", clock=self.clock)
        state.observe_recording(self.event(0, "idle"))
        for index in range(1, 256):
            scope = self.alternate_scope(index)
            state.set_scope(scope)
            state.observe_recording(self.event(0, "idle", scope=scope))

        overflow = self.alternate_scope(256)
        state.set_scope(overflow)
        exhausted = state.observe_recording(self.event(0, "recording", scope=overflow))
        self.assertEqual(exhausted["quiet_reason"], "scope_history_exhausted_latch_pending")

        unrelated = self.alternate_scope(257)
        state.observe_recording(self.event(1, "stopped", scope=unrelated))
        self.assertEqual(state.snapshot()["quiet_reason"], "scope_history_exhausted_latch_pending")

        reconciled = state.observe_recording(self.event(1, "stopped", scope=overflow))
        self.assertTrue(reconciled["quiet"])
        self.assertEqual(reconciled["quiet_reason"], "scope_history_exhausted")


if __name__ == "__main__":
    unittest.main()
