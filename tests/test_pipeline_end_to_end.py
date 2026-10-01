"""One document's journey: script -> shots -> simulator -> reviews -> plan -> preflight -> take.

This module is the audit's instrument. Every other work package in
`docs/ai-director/implementation/17-pipeline-audit-engineering-prompt.md` either extends it or
is measured by it. It joins the stages with the product's own code and asserts what each join
actually produces.

It proves the joins between the stages hold. **It proves nothing physical.** No serial port is
opened, no motor is reached, and every honesty-ledger field that must stay false is asserted
false rather than assumed.

Several assertions below pin *absence*. `review_motion` and `review_screen` return `None` on
every shot of the canonical fixture, and `travel_review`'s issues and `sampled_scene_clearance`
are never reached through `shot_review` because `motion_requirements` is false on all five.
That is not asserting less than the system does; the system does nothing there, and pinning it
is what makes the day a fixture changes shape a visible event rather than a silent one. See
section 1.4 of the audit prompt.

Cost: `PlanAndPreflightTests` runs the real solver -- about three minutes in `setUpClass`
(compile_shot 88 s, prepare_shot 94 s on the reference host). It is not mocked, because a
mocked preflight proves nothing about the gate it exists to defend.
"""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REQUIRED = ("numpy", "scipy", "mujoco")
MISSING = tuple(name for name in REQUIRED if importlib.util.find_spec(name) is None)
SIMULATION = not MISSING
SKIP_REASON = "the end-to-end pipeline needs the simulation extra; missing: " + ", ".join(
    MISSING or ("nothing",)
)

FIXTURE = Path(__file__).parent / "fixtures" / "director_arrival.json"

#: Templates whose catalog parameters include ``duration_s``. For these the authored edit
#: length is an *input* and reaches the settings. For the others it is an *output* of geometry
#: -- see work package B, which owns this distinction and names it in the wire.
DURATION_TEMPLATES = frozenset({"static", "tilt_up"})

#: Timebase strings are part of the contract a caller reads, so a change to one is a change to
#: the product, not a detail. The two reviews that declare a timebase do not share it.
SHOT_TIMEBASE = "seconds of this shot's filmed source, excluding setup"
TRAVEL_TIMEBASE = "edit-local seconds; source offsets retained; setup and unused source excluded"

#: Every field an issue must carry. A gate that fires without a recommendation cannot be acted
#: on; one without evidence cannot be checked.
ISSUE_FIELDS = frozenset({"code", "severity", "time_range_s", "observation", "evidence", "recommendation"})

#: A preflight blocker must name a quantity someone can go and measure. This vocabulary was
#: derived from the thirteen blockers the product actually emits (audit prompt section 1.5);
#: widen it only by adding a word that names a measurable thing, never by relaxing it.
MEASURABLE = re.compile(
    r"\d|measur|verif|qualif|align|toleran|clearanc|calibrat|residual|"
    r"derivativ|polygon|center of mass|centre of mass|"
    r"veloc|accelerat|jerk|torque|payload|voltage|temperature|timing|lag|response|limit",
    re.IGNORECASE,
)

#: A blocker whose entire text is one of these is a status, not a blocker.
VACUOUS = re.compile(r"^\W*(not ready|unavailable|failed|error|unknown|blocked)\W*$", re.IGNORECASE)


def document():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return raw, raw["document"]


@unittest.skipUnless(SIMULATION, SKIP_REASON)
class PipelineTests(unittest.TestCase):
    """Stages 1-4: the fixture through the seam, the simulator and the review layer."""

    @classmethod
    def setUpClass(cls):
        from takeone.director.studio import shot_settings
        from takeone.previs.cache import compile_preview

        cls.raw, cls.doc = document()
        cls.marks = {mark["mark_id"]: mark for mark in cls.doc["marks"]}
        cls.scene_of = {shot["shot_id"]: scene for scene in cls.doc["scenes"] for shot in scene["shots"]}
        cls.shots = [shot for scene in cls.doc["scenes"] for shot in scene["shots"]]
        cls.settings, cls.previews = {}, {}
        for shot in cls.shots:
            settings, _defaulted = shot_settings(shot)
            cls.settings[shot["shot_id"]] = settings
            cls.previews[shot["shot_id"]] = compile_preview(settings)

    def review_inputs(self, shot):
        sid = shot["shot_id"]
        return (
            self.settings[sid],
            self.scene_of[sid],
            self.marks[shot["mark_id"]],
            self.previews[sid],
        )

    # ---------------------------------------------------------------- 1. script -> shots

    def test_the_document_is_five_beats_over_five_distinct_spaces(self):
        scenes = self.doc["scenes"]
        self.assertEqual(len(scenes), 5)
        self.assertEqual(len({scene["space_id"] for scene in scenes}), 5)
        self.assertEqual(len({scene["scene_id"] for scene in scenes}), 5)
        self.assertEqual(len(self.shots), 5)

    def test_the_edit_covers_the_brief_with_no_gap_and_no_overlap(self):
        spans = sorted((shot["start_ms"], shot["end_ms"], shot["shot_id"]) for shot in self.shots)
        self.assertEqual(spans[0][0], 0)
        self.assertEqual(spans[-1][1], self.raw["brief"]["duration_ms"])
        for (_, end, left), (start, _, right) in zip(spans, spans[1:]):
            self.assertEqual(end, start, f"{left} ends at {end} ms but {right} starts at {start} ms")

    def test_every_mark_actor_and_target_reference_resolves(self):
        actors = {actor["actor_id"] for actor in self.doc["actors"]}
        for shot in self.shots:
            with self.subTest(shot=shot["shot_id"]):
                self.assertIn(shot["mark_id"], self.marks)
                self.assertIn(shot["actor_id"], actors)
                target = shot["camera_target"]
                if target["kind"] == "actor":
                    self.assertIn(target["target_id"], actors)
                elif target["kind"] == "object":
                    scene = self.scene_of[shot["shot_id"]]
                    self.assertIn(target["target_id"], {o["object_id"] for o in scene["objects"]})

    def test_at_least_one_shot_targets_an_object(self):
        # Object targeting is a distinct branch of `subject_points`; the person-tracking path
        # does not exercise it, and this fixture's one object shot is the suite's only cover.
        self.assertIn("object", [shot["camera_target"]["kind"] for shot in self.shots])

    # ------------------------------------------------------------ 2. shots -> simulator

    def test_every_shot_compiles_to_its_own_content_addressed_preview(self):
        seen = set()
        for shot in self.shots:
            preview = self.previews[shot["shot_id"]]
            with self.subTest(shot=shot["shot_id"]):
                self.assertTrue(preview["frames"], "no frames")
                self.assertRegex(preview["plan_id"], r"^[0-9a-f]{64}$")
            seen.add(preview["plan_id"])
        self.assertEqual(len(seen), len(self.shots), "two shots share a plan_id")

    def test_the_setup_phase_and_filmed_window_partition_the_prepared_clock(self):
        # NOT `orbit_start_s + orbit_duration_s <= duration_s`. `preview["duration_s"]` is the
        # whole prepared clock; `orbit_start_s` is setup that is excluded from the edit, and it
        # is 4.88 s on four of the five shots. The relation is equality.
        for shot in self.shots:
            preview = self.previews[shot["shot_id"]]
            with self.subTest(shot=shot["shot_id"]):
                self.assertGreater(preview["orbit_start_s"], 0.0, "no setup phase")
                self.assertGreater(preview["orbit_duration_s"], 0.0, "no filmed window")
                self.assertAlmostEqual(
                    preview["orbit_start_s"] + preview["orbit_duration_s"],
                    preview["duration_s"],
                    places=6,
                )

    # ------------------------------------------------------------- 3. the edit contract

    def test_the_authored_beat_reaches_the_settings_only_for_duration_templates(self):
        """Work package B owns this; the test is its home.

        For `static` and `tilt_up` the authored edit length is injected into `duration_s` and
        the filmed window matches it exactly. For `side_track` and `track_lead` it is not: the
        settings keep the catalog default and the filmed window falls out of actor travel and
        cart pace. That is defensible. It is currently invisible, which is not.
        """
        for shot in self.shots:
            sid, template = shot["shot_id"], shot["movement"]["template_id"]
            authored_s = (shot["end_ms"] - shot["start_ms"]) / 1000
            settings_s = self.settings[sid]["duration_s"]
            filmed_s = self.previews[sid]["orbit_duration_s"]
            with self.subTest(shot=sid, template=template):
                if template in DURATION_TEMPLATES:
                    self.assertAlmostEqual(settings_s, authored_s, places=6)
                    self.assertAlmostEqual(filmed_s, authored_s, places=6)
                else:
                    self.assertNotAlmostEqual(
                        settings_s,
                        authored_s,
                        places=6,
                        msg="a non-duration template received the authored beat; if the "
                        "catalog changed, this test and work package B change together",
                    )
                    # The derived window is near the authored beat but is not it. Pin the gap
                    # so a silent drift into disagreement is a failure.
                    self.assertLess(abs(filmed_s - authored_s), 1.0, "derived window drifted")

    # -------------------------------------------------------------------- 4. the reviews

    def test_shot_review_returns_its_declared_contract_on_every_shot(self):
        from takeone.previs.shot_review import review as review_shot

        for shot in self.shots:
            result = review_shot(shot, *self.review_inputs(shot))
            with self.subTest(shot=shot["shot_id"]):
                self.assertEqual(result["status"], "reviewable")
                self.assertEqual(result["timebase"], SHOT_TIMEBASE)
                self.assertEqual(result["source"], "simulated_geometry")
                self.assertGreater(result["samples_examined"], 0)
                self.assertEqual(result["samples_examined"], result["coverage_samples_examined"])
                self.assertTrue(result["unchecked"], "a review that checks everything is lying")

    def test_travel_review_carries_its_own_timebase_and_no_sample_count(self):
        from takeone.previs.travel_review import review_travel

        for shot in self.shots:
            sid = shot["shot_id"]
            result = review_travel(shot, self.settings[sid], self.previews[sid])
            with self.subTest(shot=sid):
                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "reviewable")
                self.assertEqual(result["timebase"], TRAVEL_TIMEBASE)
                self.assertTrue(result["scope"], "no scope disclaimer")
                # Asserted absent on purpose: adding a sample count here later should be a
                # decision someone makes, not a drift someone discovers.
                self.assertNotIn("samples_examined", result)

    def test_sampled_clearance_reports_samples_and_declares_no_timebase(self):
        from takeone.previs.scene_checks import sampled_scene_clearance

        for shot in self.shots:
            result = sampled_scene_clearance(shot, *self.review_inputs(shot))
            with self.subTest(shot=shot["shot_id"]):
                self.assertEqual(result["status"], "sampled_clear")
                self.assertGreater(result["samples"], 0)
                self.assertGreater(result["sampled_clearance_lower_bound_m"], 0.0)
                self.assertNotIn("timebase", result)
                self.assertTrue(result["scope"], "no scope disclaimer")

    def test_motion_review_is_inert_on_every_shot_of_the_canonical_fixture(self):
        """`motion_review.py:61` -- `if template not in BOOM_DIRECTIONS: return None`.

        None of `static`, `tilt_up`, `side_track` or `track_lead` is a boom template, so the
        boom-geometry gate never runs on the product's canonical example. Recorded, not
        approved: work package C asks whether a gate that never fires protects anyone.
        """
        from takeone.previs.motion_review import BOOM_DIRECTIONS, review_motion

        for shot in self.shots:
            sid, template = shot["shot_id"], shot["movement"]["template_id"]
            with self.subTest(shot=sid, template=template):
                self.assertNotIn(template, BOOM_DIRECTIONS)
                self.assertIsNone(
                    review_motion(shot, self.settings[sid], self.previews[sid]),
                    "motion_review fired: a fixture gained a boom template and work package "
                    "C's finding needs revisiting (motion_review.py:61)",
                )

    def test_screen_review_is_inert_because_no_fixture_declares_a_screen_target(self):
        """`screen_review.py:102` -- returns `None` when `design.screen_targets` is empty."""
        from takeone.previs.screen_review import review_screen

        for shot in self.shots:
            with self.subTest(shot=shot["shot_id"]):
                self.assertFalse((shot.get("design") or {}).get("screen_targets"))
                self.assertIsNone(
                    review_screen(shot, *self.review_inputs(shot)),
                    "screen_review fired: a fixture gained screen_targets and work package "
                    "C's finding needs revisiting (screen_review.py:102)",
                )

    def test_travel_and_clearance_are_unreachable_through_the_shot_review(self):
        """`shot_review.py:157` and `:160` both gate on `shot["motion_requirements"]`.

        It is false on all five shots, so neither the travel issues nor the clearance screen
        reaches a caller that runs only the shot review -- which is what the pipeline does.
        Both functions work; nothing calls them.
        """
        for shot in self.shots:
            with self.subTest(shot=shot["shot_id"]):
                self.assertFalse(shot.get("motion_requirements"))

    def test_every_issue_any_review_produces_can_be_acted_on(self):
        from takeone.previs.scene_checks import sampled_scene_clearance
        from takeone.previs.shot_review import review as review_shot
        from takeone.previs.travel_review import review_travel

        seen = 0
        for shot in self.shots:
            settings, scene, mark, preview = self.review_inputs(shot)
            results = (
                review_shot(shot, settings, scene, mark, preview),
                review_travel(shot, settings, preview),
                sampled_scene_clearance(shot, settings, scene, mark, preview),
            )
            for result in results:
                for issue in (result or {}).get("issues", ()):
                    seen += 1
                    with self.subTest(shot=shot["shot_id"], code=issue.get("code")):
                        self.assertEqual(ISSUE_FIELDS - set(issue), set())
                        self.assertTrue(issue["recommendation"].strip())
                        self.assertTrue(issue["observation"].strip())
                        start, end = issue["time_range_s"]
                        self.assertLessEqual(start, end)
        self.assertGreater(seen, 0, "no review produced an issue; the gate is not wired")

    def test_the_promised_region_is_cropped_on_every_shot_at_manual_severity(self):
        """The audit's headline, pinned.

        `promised_region_cropped` fires on 5 of 5 shots, four at 100 % of examined samples,
        because `focal_mm = 35` at `radius_m = 2.5` gives a 1.446 m vertical field while
        `REGIONS["wide"]` promises all 1.72 m of the actor. Every one is `severity: "manual"`,
        assigned by `shot_review.py:199` *because* the fixture carries no `design` block -- and
        per decision D3 a manual finding must not turn a test red.

        So this does not fail on the finding. It fails when the finding *changes*: when work
        package C fits the lens, defaults `lens_policy` or fixes the fixture, this goes red
        with the new set named, which is exactly when a human should look.
        """
        from takeone.previs.shot_review import review as review_shot

        cropped, saturated = [], []
        for shot in self.shots:
            result = review_shot(shot, *self.review_inputs(shot))
            for issue in result["issues"]:
                if issue["code"] != "promised_region_cropped":
                    continue
                cropped.append(shot["shot_id"])
                evidence = issue["evidence"]
                with self.subTest(shot=shot["shot_id"]):
                    self.assertEqual(issue["severity"], "manual")
                    self.assertEqual(evidence["visibility"], "unspecified_legacy")
                    self.assertLess(evidence["minimum_screen_margin"], 0.0)
                    self.assertEqual(evidence["examined_samples"], result["samples_examined"])
                if evidence["affected_samples"] == evidence["examined_samples"]:
                    saturated.append(shot["shot_id"])
        self.assertEqual(
            cropped,
            [shot["shot_id"] for shot in self.shots],
            "the set of cropped shots changed; if a fix landed, update work package C and "
            "this assertion together",
        )
        self.assertEqual(
            sorted(saturated),
            ["arrival-1", "arrival-3", "arrival-4", "arrival-5"],
            "the set of fully-cropped shots changed",
        )

    def test_the_lens_fitter_that_would_solve_this_is_never_reached(self):
        """`fit_opening` has one caller, gated on `design.lens_policy == "fit_subject"`.

        No fixture in the repository sets `design` at all, so the function that exists to pick
        a focal length holding the promised region never runs -- and the same missing key is
        what downgrades the resulting crop to `manual`. Work package C decides whether that
        default is right; this pins that it is currently the default.
        """
        for shot in self.shots:
            with self.subTest(shot=shot["shot_id"]):
                self.assertNotEqual(
                    (shot.get("design") or {}).get("lens_policy"),
                    "fit_subject",
                    "a fixture now requests lens fitting; revisit work package C",
                )


@unittest.skipUnless(SIMULATION, SKIP_REASON)
class PlanAndPreflightTests(unittest.TestCase):
    """Stage 5: a compiled shot becomes a robot plan, and preflight refuses to run it."""

    @classmethod
    def setUpClass(cls):
        from takeone.motion.limits import preflight
        from takeone.motion.plan import prepare_shot
        from takeone.planning.compiler import compile_shot

        cls.shot = compile_shot()
        cls.plan = prepare_shot(cls.shot)
        cls.result = preflight(cls.plan)

    def test_the_software_plan_is_valid_and_live_execution_is_still_refused(self):
        self.assertTrue(self.result["software_plan_valid"])
        self.assertTrue(self.result["shot_fidelity_passed"])
        self.assertIs(self.result["live_execution_allowed"], False)
        self.assertIs(self.result["serial_ports_opened"], False)
        self.assertIs(self.result["physical_tracking_verified"], False)
        self.assertTrue(self.result["blockers"], "a preflight with no blockers is not a preflight")

    def test_every_blocker_names_a_measurement_not_a_mood(self):
        for blocker in self.result["blockers"]:
            with self.subTest(blocker=blocker):
                self.assertIsNone(VACUOUS.match(blocker), "a bare status is not a blocker")
                self.assertRegex(blocker, MEASURABLE)

    def test_both_arms_are_blocked_separately(self):
        # A single "arms need measurement" blocker would hide that one arm can be qualified
        # while the other is not. Each role must appear on its own.
        joined = "\n".join(self.result["blockers"])
        for role in ("phone", "light"):
            self.assertIn(f"{role}:", joined, f"{role} has no blocker of its own")

    def test_preflight_opens_no_serial_port(self):
        from takeone.motion.devices import DeviceFactory
        from takeone.motion.limits import preflight

        with patch.object(DeviceFactory, "open") as opening:
            preflight(self.plan)
        opening.assert_not_called()


class FakePhone:
    """A device that answers, so the test measures the service and not a network."""

    def __init__(self):
        self.calls = []

    def request_start(self, take_id, context, requested_ns):
        from takeone.recording.simulated import StartAttempt

        self.calls.append(("start", take_id))
        return StartAttempt(requested_ns, requested_ns + 2_000_000_000)

    def request_stop(self, take_id, requested_ns):
        from takeone.recording.simulated import StopAttempt

        self.calls.append(("stop", take_id))
        return StopAttempt("acknowledged")

    def report(self, take_id):
        return {
            "source": "device_reported",
            "start_attempted": True,
            "recording_confirmed": True,
            "stop_confirmed": True,
            "media_verified": False,
        }


class TakeTests(unittest.TestCase):
    """Stage 6: a take runs against a fake device and reports exactly what it knows."""

    def setUp(self):
        from takeone.recording.service import RecordingService

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.phone = FakePhone()
        self.service = RecordingService(root / "takes.sqlite3", root / "media", phone_recorder=self.phone)
        self.addCleanup(self.service.close)

    def test_a_phone_take_is_recorded_as_a_phone_take_and_claims_no_media(self):
        context = {"source": "embodied_behavior", "behavior_id": "behavior-1"}
        started = self.service.start("request-1", context, None, source="phone")
        take = self.service.get(started["take_id"])
        self.assertEqual(take["source"], "phone")
        self.assertEqual(take["state"], "recording")
        self.assertEqual([call[0] for call in self.phone.calls], ["start"])
        # The device said it is rolling. That is a transmitted claim, not a measurement, and
        # every field that would assert otherwise stays false.
        self.assertIs(take["real_media_verified"], False)
        self.assertIs(take["optical_framing_verified"], False)
        self.assertIsNone(take["media"])
        self.assertEqual(take["media_location"], "phone_internal_storage")
        self.assertEqual(take["zoom_mapping"], "estimated_between_operator_measured_points")

    def test_the_acknowledgement_is_timed_not_predicted(self):
        # `PhoneRecorder` blocks on the device's own confirmation before returning, so the ack
        # timestamp is measured. A take that reached `recording` must carry one.
        started = self.service.start("request-2", {"source": "embodied_behavior"}, None, source="phone")
        take = self.service.get(started["take_id"])
        acks = [e for e in take["events"] if e["kind"] == "start_acknowledged"]
        self.assertEqual(len(acks), 1)
        self.assertEqual(acks[0]["detail"]["source"], "device_reported")
        self.assertTrue(acks[0]["ack_monotonic_ns"])


class ShutGateTests(unittest.TestCase):
    """Stage 7: the gate that must stay shut, whatever else this module proves."""

    def test_the_physical_path_is_never_verified(self):
        from takeone.motion.studio import RobotPlayback

        self.assertIs(RobotPlayback().status()["physical_path_verified"], False)

    def test_a_fresh_behavior_manager_is_not_armed_and_owns_no_motion(self):
        from takeone.embodied import BehaviorManager

        snapshot = BehaviorManager().snapshot()
        self.assertFalse(snapshot["armed"])
        self.assertIsNone(snapshot["behavior"])
        self.assertEqual(snapshot["motion_authority"], "none")
        self.assertIsNone(snapshot["motion_source"])
        # `physical_motion` is hardcoded False in `behavior.py`. Observing never moves
        # anything and arming is blocked elsewhere; this pins the literal, not the mood.
        self.assertIs(snapshot["physical_motion"], False)


if __name__ == "__main__":
    unittest.main()
