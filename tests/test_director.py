import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from takeone.director.api import DirectorAPI
from takeone.director.contracts import (
    Beat,
    Command,
    Evidence,
    Mode,
    Phase,
    ProductionBrief,
    Session,
    ShotReference,
)
from takeone.director.demo import run_demonstration
from takeone.director.repository import SessionRepository
from takeone.director.service import COMMAND_TTL_NS, DirectorService, OwnerReplacedError


def uid():
    return str(uuid4())


class Clock:
    value = 1_000_000_000_000_000_000  # Deliberately beyond JavaScript's exact Number range.

    def __call__(self):
        return self.value


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "sessions.sqlite3"
        self.repository = SessionRepository(self.path)
        self.clock = Clock()
        self.service = DirectorService(self.repository, self.clock)
        self.brief = ProductionBrief(
            "My product film", "Show my own product without invented claims.", 12000, "9:16"
        )
        self.api = DirectorAPI(self.service)

    def create(self, mode=Mode.PLANNING):
        result = self.service.create(
            uid(),
            self.service.epoch,
            self.clock() + COMMAND_TTL_NS,
            self.brief,
            mode,
        )
        self.assertTrue(result["ok"])
        return Session.parse(result["session"])

    def command(self, session, action, brief=None):
        return Command(
            uid(),
            self.service.epoch,
            self.clock() + COMMAND_TTL_NS,
            session.scope(),
            action,
            brief,
        )

    def evidence(self, source="fixture"):
        return Evidence(source, "test-fixture", 0, self.clock(), self.service.epoch, "session")

    def shot(self):
        return ShotReference(
            uid(),
            uid(),
            1,
            "a" * 64,
            12000,
            "fixture",
            (Beat(uid(), 1000, 4000, "Introduce the product."),),
        )

    def plan_job(self, session):
        result = self.service.submit(self.command(session, "request_plan"))
        self.assertTrue(result["ok"])
        return Session.parse(result["session"]), result["job_id"]

    def complete(self, session, job_id, shot=None, evidence=None):
        return self.service.complete(
            uid(),
            job_id,
            session.scope(),
            self.service.epoch,
            self.clock() + COMMAND_TTL_NS,
            evidence or self.evidence(),
            shot,
        )

    def test_brief_survives_restart_without_revision_or_content_changes(self):
        session = self.create()
        revised = self.service.submit(
            self.command(session, "revise_brief", replace(self.brief, objective="Use a quiet opening."))
        )["session"]
        restarted = DirectorService(SessionRepository(self.path), self.clock)
        self.assertNotEqual(restarted.epoch, self.service.epoch)
        self.assertEqual(restarted.repository.inspect(session.session_id)["session"], revised)
        self.assertEqual(len(restarted.repository.inspect(session.session_id)["events"]), 2)

    def test_completed_create_is_idempotent_even_after_restart_and_expiry(self):
        op = uid()
        args = (op, self.service.epoch, self.clock() + COMMAND_TTL_NS, self.brief)
        first = self.service.create(*args)
        self.clock.value += 2 * COMMAND_TTL_NS
        restarted = DirectorService(SessionRepository(self.path), self.clock)
        second = restarted.create(*args)
        self.assertTrue(second["replayed"])
        self.assertEqual(second["session"], first["session"])
        self.assertEqual(len(self.repository.list_sessions()), 1)

    def test_operation_id_cannot_be_reused_for_different_content(self):
        session = self.create()
        command = self.command(session, "revise_brief", self.brief)
        self.service.submit(command)
        conflict = self.service.submit(replace(command, brief=replace(self.brief, title="Different")))
        self.assertEqual(conflict["code"], "operation_conflict")
        self.assertEqual(
            self.repository.inspect(session.session_id)["session"]["brief"]["title"], self.brief.title
        )

    def test_stale_revision_cancel_generation_take_and_plan_are_rejected(self):
        session = self.create()
        scopes = (
            replace(session.scope(), expected_revision=1),
            replace(session.scope(), cancellation_generation=1),
            replace(session.scope(), take_id=uid()),
            replace(session.scope(), plan_id="b" * 64),
        )
        for scope in scopes:
            result = self.service.submit(replace(self.command(session, "cancel"), scope=scope))
            self.assertEqual(result["code"], "stale_scope")
        self.assertEqual(self.repository.inspect(session.session_id)["session"], session.wire())

    def test_expired_previous_runtime_and_excessive_deadlines_are_rejected(self):
        session = self.create()
        command = self.command(session, "cancel")
        for modified, expected in (
            (replace(command, expires_monotonic_ns=self.clock()), "expired"),
            (replace(command, runtime_epoch=uid()), "runtime_changed"),
            (replace(command, expires_monotonic_ns=self.clock() + COMMAND_TTL_NS + 1), "invalid_deadline"),
        ):
            result = self.service.submit(replace(modified, operation_id=uid()))
            self.assertEqual(result["code"], expected)
        self.assertEqual(self.repository.inspect(session.session_id)["session"]["revision"], 0)

    def test_concurrent_edits_have_one_winner(self):
        session = self.create()
        commands = [
            self.command(session, "revise_brief", replace(self.brief, title=f"Version {i}")) for i in range(2)
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.service.submit, commands))
        self.assertEqual(sum(result["ok"] for result in results), 1)
        self.assertEqual({r["code"] for r in results}, {"applied", "stale_scope"})
        self.assertEqual(self.repository.inspect(session.session_id)["session"]["revision"], 1)

    def test_concurrent_duplicate_creates_one_job_and_one_event(self):
        session = self.create(Mode.DEMONSTRATION)
        command = self.command(session, "request_plan")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.service.submit, [command, command]))
        self.assertTrue(all(r["ok"] for r in results))
        self.assertEqual(sum(r["replayed"] for r in results), 1)
        inspected = self.repository.inspect(session.session_id)
        self.assertEqual(len(inspected["jobs"]), 1)
        self.assertEqual([e["kind"] for e in inspected["events"]], ["session_created", "request_plan"])

    def test_database_failure_rolls_back_state_event_and_receipt_together(self):
        session = self.create()
        command = self.command(session, "revise_brief", replace(self.brief, title="Must not persist"))
        with self.repository.connect() as connection:
            connection.execute(
                "CREATE TRIGGER deny_revision BEFORE INSERT ON events WHEN NEW.kind='revise_brief' "
                "BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.submit(command)
        inspected = self.repository.inspect(session.session_id)
        self.assertEqual(inspected["session"], session.wire())
        self.assertEqual(len(inspected["events"]), 1)
        with self.repository.connect() as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT * FROM operations WHERE operation_id=?", (command.operation_id,)
                ).fetchone()
            )
            connection.execute("DROP TRIGGER deny_revision")
        self.assertTrue(self.service.submit(command)["ok"])

    def test_cancel_discards_pending_job_and_late_completion(self):
        session, job_id = self.plan_job(self.create(Mode.DEMONSTRATION))
        self.assertTrue(self.service.submit(self.command(session, "cancel"))["ok"])
        late = self.complete(session, job_id, self.shot())
        self.assertEqual(late["code"], "stale_job")
        inspected = self.repository.inspect(session.session_id)
        self.assertEqual(inspected["session"]["phase"], Phase.CANCELLED)
        self.assertEqual(inspected["jobs"][0]["status"], "cancelled")

    def test_restart_requires_reconciliation_and_old_owner_cannot_write(self):
        session, job_id = self.plan_job(self.create(Mode.DEMONSTRATION))
        restarted = DirectorService(SessionRepository(self.path), self.clock)
        inspected = restarted.repository.inspect(session.session_id)
        self.assertEqual(inspected["session"]["phase"], Phase.FAULT)
        self.assertEqual(inspected["jobs"][0]["status"], "reconciliation_required")
        self.assertEqual(inspected["session"]["cancellation_generation"], 1)
        with self.assertRaises(OwnerReplacedError):
            self.complete(session, job_id, self.shot())

    def test_other_session_completion_cannot_consume_this_job(self):
        session, job_id = self.plan_job(self.create(Mode.DEMONSTRATION))
        other, _ = self.plan_job(self.create(Mode.DEMONSTRATION))
        self.assertEqual(self.complete(other, job_id, self.shot())["code"], "stale_job")
        self.assertEqual(self.repository.inspect(session.session_id)["jobs"][0]["status"], "pending")

    def test_evidence_must_match_clock_source_freshness_and_job_kind(self):
        session, job_id = self.plan_job(self.create(Mode.DEMONSTRATION))
        for evidence in (
            self.evidence("observed"),
            replace(self.evidence(), runtime_epoch=uid()),
            replace(self.evidence(), captured_monotonic_ns=self.clock() + 1),
            replace(self.evidence(), captured_monotonic_ns=self.clock() - COMMAND_TTL_NS - 1),
        ):
            self.assertEqual(
                self.complete(session, job_id, self.shot(), evidence)["code"], "invalid_evidence"
            )
        self.assertEqual(self.complete(session, job_id)["code"], "invalid_result")
        self.assertEqual(self.repository.inspect(session.session_id)["session"]["phase"], Phase.PLANNING)

    def test_real_sessions_cannot_use_demo_as_a_live_integration(self):
        session = self.create()
        result = self.service.submit(self.command(session, "request_plan"))
        self.assertEqual(result["code"], "unavailable")
        self.assertEqual(self.repository.inspect(session.session_id)["jobs"], [])

    def test_phase_gate_rejects_recording_before_ready(self):
        session = self.create(Mode.DEMONSTRATION)
        self.assertEqual(
            self.service.submit(self.command(session, "request_record"))["code"], "invalid_transition"
        )
        self.assertIsNone(self.repository.inspect(session.session_id)["session"]["take_id"])

    def test_complete_demonstration_has_fixture_evidence_and_no_real_media(self):
        result = run_demonstration(self.service, uid(), self.service.epoch, self.clock() + COMMAND_TTL_NS)
        self.assertTrue(result["ok"])
        self.assertEqual(result["session"]["phase"], Phase.COMPLETE)
        self.assertEqual(result["session"]["mode"], Mode.DEMONSTRATION)
        self.assertFalse(result["real_media_verified"])
        jobs = self.repository.inspect(result["session"]["session_id"])["jobs"]
        self.assertEqual(len(jobs), 5)
        self.assertTrue(all(j["result"]["evidence"]["source"] == "fixture" for j in jobs))
        self.assertTrue(all(j["result"]["real_media_verified"] is False for j in jobs))

    def test_api_preserves_large_clock_values_and_rejects_unexpected_fields(self):
        runtime = self.api.get("/api/director/runtime")
        self.assertEqual(runtime["now_monotonic_ns"], str(self.clock()))
        body = {
            "schema_version": 1,
            "operation_id": uid(),
            "runtime_epoch": self.service.epoch,
            "expires_monotonic_ns": str(self.clock() + COMMAND_TTL_NS),
            "brief": asdict(self.brief),
        }
        result = self.api.post("/api/director/sessions", body)
        self.assertTrue(result["ok"])
        for changed in (
            {**body, "mode": "demonstration"},
            {**body, "expires_monotonic_ns": self.clock() + COMMAND_TTL_NS},
            {**body, "brief": {**body["brief"], "motor_command": 0.15}},
            {**body, "schema_version": True},
        ):
            with self.assertRaises(ValueError):
                self.api.post("/api/director/sessions", changed)
        with self.assertRaises(KeyError):
            self.api.post("/api/director/complete_job", body)

    def test_contracts_reject_bad_timing_types_and_unmeasured_pose_claims(self):
        for duration in (True, 0, float("nan"), "12000"):
            with self.assertRaises(ValueError):
                replace(self.brief, duration_ms=duration)
        for bounds in ((1000, 1000), (2000, 1000), (-1, 1000)):
            with self.assertRaises(ValueError):
                Beat(uid(), *bounds, "A beat")
        with self.assertRaises(ValueError):
            replace(self.shot(), duration_ms=1000)
        with self.assertRaises(ValueError):
            replace(self.shot(), source="measured")

    def test_unrelated_database_is_not_overwritten(self):
        path = Path(self.folder.name) / "other.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE unrelated (value TEXT)")
            connection.execute("INSERT INTO unrelated VALUES ('preserve me')")
            connection.commit()
        with self.assertRaises(ValueError):
            SessionRepository(path)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM unrelated").fetchone()[0], "preserve me")

    def test_capability_report_is_truthful_and_import_has_no_device_modules(self):
        report = self.api.get("/api/director/capabilities")
        self.assertTrue(report["hardware_blockers"])
        enabled = [c["name"] for c in report["capabilities"] if c["available"]]
        self.assertIn("Save and resume video ideas", enabled)
        self.assertNotIn("Phone preview and recording", enabled)
        self.assertNotIn("Robot execution", enabled)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import takeone.director.api; "
                "assert not {'serial', 'mujoco', 'cv2', 'lerobot'} & sys.modules.keys()",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_capability_report_uses_the_configured_gemini_provider(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "GEMINI_API_KEY": "test-key"}, clear=False):
            report = self.api.get("/api/director/capabilities")
        planning = next(item for item in report["capabilities"] if item["name"] == "AI script planning")
        self.assertTrue(planning["available"])
        self.assertEqual(planning["source"], "configured_unverified")
        self.assertNotIn("OPENAI_API_KEY", planning["explanation"])


if __name__ == "__main__":
    unittest.main()
