"""The repair loop: bounded, re-validated, and unable to touch anything creative."""

import copy
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from takeone.director.contracts import ProductionBrief, Session
from takeone.director.creative import all_shots, repair_schema, validate
from takeone.director.planning import CreativePlanning
from takeone.director.provider import ProviderResult, ResponsesPlanner
from takeone.director.repository import SessionRepository
from takeone.director.service import COMMAND_TTL_NS, DirectorService
from takeone.director.skills import sample_project
from takeone.director.studio import shot_diagnostic


class Clock:
    value = 1_000_000_000_000_000_000

    def __call__(self):
        return self.value


def movement(template_id, **parameters):
    return dict(
        template_id=template_id,
        subject_motion="hold",
        parameters=[dict(name=n, value=v) for n, v in parameters.items()],
    )


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = SessionRepository(Path(self.temp.name) / "sessions.sqlite3")
        self.clock = Clock()
        self.owner = DirectorService(self.repo, clock=self.clock)
        config = ResponsesPlanner(api_key="").config
        self.provider = ResponsesPlanner({**config, "enabled": True}, api_key="offline-test-not-a-key")
        self.planner = CreativePlanning(self.owner, self.provider)
        self.dispatched = []
        self.planner._dispatch = self.dispatched.append
        self.sample = sample_project("dialogue")
        self.session = Session.parse(
            self.owner.create(
                str(uuid4()),
                self.owner.epoch,
                self.clock() + COMMAND_TTL_NS,
                ProductionBrief.parse(self.sample["brief"]),
            )["session"]
        )
        self.submit("load_sample", {"skill_id": "dialogue"})
        self.resolve_all()

    def resolve_all(self):
        """The curated samples ship without movements. Give every shot a real one first."""
        document = copy.deepcopy(self.document())
        for shot in all_shots(document):
            shot["primitive"] = "template"
            shot["movement"] = movement("push_in", speed_m_s=0.3, distance_m=1.0)
        self.submit("save_document", {"document": document})

    def submit(self, action, payload):
        body = {
            "schema_version": 1,
            "operation_id": str(uuid4()),
            "runtime_epoch": self.owner.epoch,
            "expires_monotonic_ns": str(self.clock() + COMMAND_TTL_NS),
            "scope": asdict(self.session.scope()),
            "action": action,
            "payload": payload,
        }
        result = self.planner.submit(body, int(body["expires_monotonic_ns"]))
        if result.get("session"):
            self.session = Session.parse(result["session"])
        return result

    def document(self):
        return self.repo.inspect(self.session.session_id)["creative"]["document"]

    def break_first_shot(self):
        """The real blocked state: the model said it could not express this movement."""
        document = copy.deepcopy(self.document())
        shot = all_shots(document)[0]
        shot["primitive"] = "other_requested"
        shot["movement"] = movement("unresolved", speed_m_s=9.0)
        self.submit("save_document", {"document": document})
        return shot["shot_id"]

    def finish(self, job_id, repairs, document=None):
        self.planner._finish(
            job_id,
            ProviderResult(
                document if document is not None else {"repairs": repairs},
                {"source": "fixture", "provider": "offline_acceptance", "input_digest": "fixture"},
            ),
        )
        detail = self.repo.inspect(self.session.session_id)
        self.session = Session.parse(detail["session"])
        return detail

    def start_repair(self):
        result = self.submit("repair_shots", {"budget_consent": True})
        self.assertTrue(result["ok"], result)
        return result["job_id"]

    # --- payload -----------------------------------------------------------------
    def test_only_the_shots_that_failed_are_sent(self):
        broken = self.break_first_shot()
        job_id = self.start_repair()
        with self.repo.connect() as connection:
            payload = connection.execute(
                "SELECT payload FROM planning_requests WHERE job_id=?", (job_id,)
            ).fetchone()["payload"]
        import json

        request = json.loads(payload)
        self.assertEqual([entry["shot"]["shot_id"] for entry in request["shots"]], [broken])
        self.assertEqual(request["shots"][0]["diagnostic"]["code"], "unresolved_movement")
        self.assertEqual(request["shots"][0]["diagnostic"]["severity"], "blocking")
        self.assertIn("movement_catalog", request)
        self.assertEqual(request["attempt"], 1)

    def test_a_script_that_already_translates_has_nothing_to_repair(self):
        result = self.submit("repair_shots", {"budget_consent": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "nothing_to_repair")

    def test_the_budget_gate_still_applies(self):
        self.break_first_shot()
        result = self.submit("repair_shots", {"budget_consent": False})
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "consent_required")

    # --- applying ----------------------------------------------------------------
    def test_a_valid_repair_is_applied_and_the_shot_then_translates(self):
        broken = self.break_first_shot()
        job_id = self.start_repair()
        before = next(s for s in all_shots(self.document()) if s["shot_id"] == broken)
        detail = self.finish(
            job_id,
            [
                dict(
                    shot_id=broken,
                    explanation="Within the cart range",
                    movement=movement("push_in", speed_m_s=0.3, distance_m=1.0),
                )
            ],
        )
        shot = next(s for s in all_shots(detail["creative"]["document"]) if s["shot_id"] == broken)
        self.assertIsNone(shot_diagnostic(shot))
        self.assertEqual(shot["primitive"], "template")
        for field in (
            "action",
            "camera_intent",
            "light_intent",
            "edit_intent",
            "framing",
            "start_ms",
            "end_ms",
            "lines",
            "selected_line",
            "mark_id",
            "actor_id",
        ):
            self.assertEqual(shot[field], before[field], field)

    def test_a_repair_that_still_breaks_the_rig_is_refused_by_the_compiler(self):
        broken = self.break_first_shot()
        job_id = self.start_repair()
        detail = self.finish(
            job_id,
            [dict(shot_id=broken, explanation="Still wrong", movement=movement("push_in", speed_m_s=7.0))],
        )
        shot = next(s for s in all_shots(detail["creative"]["document"]) if s["shot_id"] == broken)
        self.assertIsNotNone(shot_diagnostic(shot))
        with self.repo.connect() as connection:
            row = connection.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        self.assertEqual(row["status"], "failed")

    def test_a_repair_for_an_unknown_shot_cannot_add_one(self):
        broken = self.break_first_shot()
        job_id = self.start_repair()
        before = len(all_shots(self.document()))
        detail = self.finish(
            job_id, [dict(shot_id="not-a-shot", explanation="…", movement=movement("push_in", speed_m_s=0.3))]
        )
        self.assertEqual(len(all_shots(detail["creative"]["document"])), before)
        self.assertIsNotNone(
            shot_diagnostic(
                next(s for s in all_shots(detail["creative"]["document"]) if s["shot_id"] == broken)
            )
        )

    def test_repair_cannot_change_a_shot_that_was_not_requested(self):
        broken = self.break_first_shot()
        untouched = copy.deepcopy(all_shots(self.document())[1])
        job_id = self.start_repair()
        detail = self.finish(
            job_id,
            [
                dict(shot_id=broken, explanation="Resolved", movement=movement("push_in", speed_m_s=0.3)),
                dict(shot_id=untouched["shot_id"], explanation="Unrequested", movement=movement("pan_left")),
            ],
        )
        saved = all_shots(detail["creative"]["document"])
        self.assertIsNone(shot_diagnostic(saved[0]))
        self.assertEqual(saved[1], untouched)

    # --- bounds ------------------------------------------------------------------
    def test_repair_stops_after_two_attempts(self):
        self.break_first_shot()
        for _ in range(CreativePlanning.REPAIR_ATTEMPT_LIMIT):
            job_id = self.start_repair()
            self.finish(
                job_id,
                [dict(shot_id="not-a-shot", explanation="…", movement=movement("push_in", speed_m_s=0.3))],
            )
        result = self.submit("repair_shots", {"budget_consent": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "repair_limit")

    def test_one_refused_number_does_not_discard_the_whole_proposal(self):
        """A model proposal with one bad value keeps its other eleven shots."""
        proposal = copy.deepcopy(self.document())
        shots = all_shots(proposal)
        for shot in shots:
            shot["primitive"] = "template"
            shot["movement"] = movement("push_in", speed_m_s=0.3, distance_m=1.0)
        shots[1]["movement"] = movement("push_in", speed_m_s=9.0)
        started = self.submit("request_plan", {"context": self.sample["context"], "budget_consent": True})
        self.assertTrue(started["ok"], started)
        job_id = started["job_id"]
        detail = self.finish(job_id, None, document=proposal)
        saved = all_shots(detail["creative"]["document"])
        self.assertEqual(len(saved), len(shots))
        self.assertEqual(saved[1]["movement"]["template_id"], "unresolved")
        self.assertEqual(saved[1]["primitive"], "other_requested")
        self.assertIsNone(shot_diagnostic(saved[0]))
        self.assertIsNone(shot_diagnostic(saved[2]))
        with self.repo.connect() as connection:
            import json

            outcome = json.loads(
                connection.execute("SELECT result FROM jobs WHERE job_id=?", (job_id,)).fetchone()["result"]
            )
        self.assertEqual(outcome["code"], "proposal_saved")
        self.assertEqual(outcome["unresolved_shot_ids"], [saved[1]["shot_id"]])
        self.assertEqual(outcome["diagnostics"][0]["parameter"], "speed_m_s")

    def test_the_repair_schema_is_the_one_the_provider_would_send(self):
        schema = repair_schema()
        validate(
            {"repairs": [dict(shot_id="s1", explanation="x", movement=movement("push_in", speed_m_s=0.3))]},
            schema,
            "repair",
        )
        with self.assertRaises(ValueError):
            validate(
                {
                    "repairs": [
                        dict(
                            shot_id="s1", explanation="x", movement=movement("not_a_template", speed_m_s=0.3)
                        )
                    ]
                },
                schema,
                "repair",
            )


if __name__ == "__main__":
    unittest.main()
