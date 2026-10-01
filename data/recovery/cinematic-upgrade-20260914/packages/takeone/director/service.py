"""The only writer of Director sessions; providers return scoped proposals."""

import hashlib
import json
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from uuid import uuid4

from .contracts import (
    Command,
    Evidence,
    Mode,
    Phase,
    ProductionBrief,
    Scope,
    Session,
    ShotReference,
    encode,
    identity,
    integer,
)
from .repository import SessionRepository

COMMAND_TTL_NS = 15_000_000_000
TRANSITIONS = {
    "request_plan": (Phase.BRIEF, Phase.PLANNING, "plan"),
    "request_rehearsal": (Phase.PREVIEW, Phase.REHEARSAL, None),
    "mark_ready": (Phase.REHEARSAL, Phase.READY, None),
    "request_record": (Phase.READY, Phase.STARTING_RECORDING, "record_start"),
    "request_cut": (Phase.RECORDING, Phase.FINALIZING, "record_stop"),
    "request_review": (Phase.REVIEW, Phase.REVIEW, "review"),
    "accept_take": (Phase.REVIEW, Phase.ACCEPTED, None),
    "prepare_edit": (Phase.ACCEPTED, Phase.EDITING, "edit"),
}
COMPLETIONS = {
    "plan": Phase.PREVIEW,
    "record_start": Phase.RECORDING,
    "record_stop": Phase.REVIEW,
    "review": Phase.REVIEW,
    "edit": Phase.COMPLETE,
}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


class OwnerReplacedError(RuntimeError):
    """Another runtime took ownership; this instance must not keep writing."""


class DirectorService:
    def __init__(self, repository: SessionRepository, clock=time.monotonic_ns, utc=now_utc):
        self.repository = repository
        self.clock, self.utc = clock, utc
        self.epoch = str(uuid4())
        with repository.transaction() as connection:
            # Restart invalidates outstanding work without pretending it stopped a device.
            session_ids = connection.execute(
                "SELECT DISTINCT session_id FROM jobs WHERE status='pending'"
            ).fetchall()
            for row in session_ids:
                session = repository.get(connection, row["session_id"])
                recovered = replace(
                    session,
                    phase=Phase.FAULT,
                    revision=session.revision + 1,
                    cancellation_generation=session.cancellation_generation + 1,
                    updated_utc=utc(),
                )
                repository.save(connection, recovered)
                repository.event(
                    connection,
                    recovered,
                    "reconciliation_required",
                    {"reason": "Runtime restarted with unfinished work; no operation resumed"},
                    utc(),
                )
            connection.execute("UPDATE jobs SET status='reconciliation_required' WHERE status='pending'")
            connection.execute(
                "INSERT INTO runtime VALUES (1, ?) ON CONFLICT(singleton) DO UPDATE SET epoch=excluded.epoch",
                (self.epoch,),
            )

    def runtime(self):
        return {
            "schema_version": 1,
            "runtime_epoch": self.epoch,
            "now_monotonic_ns": str(self.clock()),
            "command_ttl_ns": str(COMMAND_TTL_NS),
            "mode": "local session foundation",
            "hardware_connected": False,
        }

    def _owner(self, connection):
        row = connection.execute("SELECT epoch FROM runtime WHERE singleton=1").fetchone()
        if row["epoch"] != self.epoch:
            raise OwnerReplacedError("Another Director runtime owns this database. Reload that runtime.")

    def _clock_error(self, epoch, expiry):
        now = self.clock()
        if epoch != self.epoch:
            return "runtime_changed", "The app restarted. Refresh before trying again."
        if expiry <= now:
            return "expired", "This request expired. Refresh and try again."
        if expiry > now + COMMAND_TTL_NS:
            return "invalid_deadline", "Request deadline exceeds the allowed window."
        return None

    @staticmethod
    def _duplicate(connection, operation_id, digest):
        old = connection.execute(
            "SELECT fingerprint, result FROM operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if old is None:
            return None
        if old["fingerprint"] != digest:
            return {
                "ok": False,
                "code": "operation_conflict",
                "message": "This request ID was already used for different content.",
            }
        return {**json.loads(old["result"]), "replayed": True}

    def _receipt(self, connection, operation_id, digest, session, result):
        connection.execute(
            "INSERT INTO operations VALUES (?, ?, ?, ?)",
            (operation_id, digest, session.session_id if session else None, encode(result)),
        )
        return result

    def _reject(self, connection, operation_id, digest, session, error):
        result = {"ok": False, "code": error[0], "message": error[1]}
        if session:
            result["session"] = session.wire()
            self.repository.event(connection, session, "request_rejected", {"code": error[0]}, self.utc())
        return self._receipt(connection, operation_id, digest, session, result)

    def create(self, operation_id, epoch, expiry, brief, mode=Mode.PLANNING):
        identity(operation_id, "Operation ID")
        identity(epoch, "Runtime epoch")
        integer(expiry, "Expiry")
        if not isinstance(brief, ProductionBrief) or not isinstance(mode, Mode):
            raise ValueError("Typed brief and mode required")
        digest = fingerprint(
            {"create": asdict(brief), "mode": mode, "runtime_epoch": epoch, "expiry": expiry}
        )
        with self.repository.transaction() as connection:
            self._owner(connection)
            duplicate = self._duplicate(connection, operation_id, digest)
            if duplicate is not None:
                return duplicate
            error = self._clock_error(epoch, expiry)
            if error:
                return self._reject(connection, operation_id, digest, None, error)
            timestamp = self.utc()
            session = Session(
                str(uuid4()),
                0,
                0,
                mode,
                Phase.BRIEF,
                brief,
                None,
                None,
                None,
                timestamp,
                timestamp,
            )
            self.repository.save(connection, session)
            self.repository.event(connection, session, "session_created", {"mode": mode}, timestamp)
            return self._receipt(
                connection,
                operation_id,
                digest,
                session,
                {"ok": True, "code": "created", "session": session.wire(), "replayed": False},
            )

    def submit(self, command: Command):
        if not isinstance(command, Command):
            raise ValueError("A typed command is required")
        digest = fingerprint(asdict(command))
        with self.repository.transaction() as connection:
            self._owner(connection)
            duplicate = self._duplicate(connection, command.operation_id, digest)
            if duplicate is not None:
                return duplicate
            session = self.repository.get(connection, command.scope.session_id)
            error = self._clock_error(command.runtime_epoch, command.expires_monotonic_ns)
            if error is None and command.scope != session.scope():
                error = ("stale_scope", "The session, take or plan changed. Refresh before applying this.")
            if error is None and command.action not in ("revise_brief", "cancel"):
                if session.mode != Mode.DEMONSTRATION:
                    error = ("unavailable", "This integration is not connected in the session foundation.")
                elif session.phase != TRANSITIONS[command.action][0]:
                    error = ("invalid_transition", "This action does not belong to the current stage.")
                elif command.action == "accept_take" and session.reviewed_take_id != session.take_id:
                    error = ("review_required", "Review this take before accepting it.")
                elif (
                    command.action == "request_review"
                    and connection.execute(
                        "SELECT 1 FROM jobs WHERE session_id=? AND status='pending'", (session.session_id,)
                    ).fetchone()
                ):
                    error = ("job_pending", "A review is already pending.")
            if (
                error is None
                and command.action == "revise_brief"
                and session.phase
                in (
                    Phase.STARTING_RECORDING,
                    Phase.RECORDING,
                    Phase.FINALIZING,
                )
            ):
                error = ("capture_active", "Finish or reconcile recording before changing the brief.")
            if error:
                return self._reject(connection, command.operation_id, digest, session, error)

            changes = {"revision": session.revision + 1, "updated_utc": self.utc()}
            job_kind = None
            if command.action in ("revise_brief", "cancel"):
                changes["cancellation_generation"] = session.cancellation_generation + 1
                connection.execute(
                    "UPDATE jobs SET status='cancelled' WHERE session_id=? AND status='pending'",
                    (session.session_id,),
                )
                if command.action == "revise_brief":
                    changes.update(
                        brief=command.brief,
                        phase=Phase.BRIEF,
                        shot=None,
                        take_id=None,
                        reviewed_take_id=None,
                    )
                else:
                    changes["phase"] = Phase.CANCELLED
            else:
                _, changes["phase"], job_kind = TRANSITIONS[command.action]
                if command.action == "request_record":
                    changes.update(take_id=str(uuid4()), reviewed_take_id=None)
            updated = replace(session, **changes)
            self.repository.save(connection, updated)
            job_id = None
            if job_kind:
                job_id = str(uuid4())
                connection.execute(
                    "INSERT INTO jobs VALUES (?, ?, ?, 'pending', ?, ?, NULL)",
                    (job_id, updated.session_id, job_kind, encode(asdict(updated.scope())), self.epoch),
                )
            self.repository.event(
                connection,
                updated,
                command.action,
                {"job_id": job_id, "mode": updated.mode},
                self.utc(),
            )
            return self._receipt(
                connection,
                command.operation_id,
                digest,
                updated,
                {
                    "ok": True,
                    "code": "applied",
                    "session": updated.wire(),
                    "job_id": job_id,
                    "replayed": False,
                },
            )

    def complete(self, operation_id, job_id, scope, epoch, expiry, evidence, shot=None):
        """Internal completion boundary. The HTTP API does not expose this method."""
        identity(operation_id, "Operation ID")
        identity(job_id, "Job ID")
        identity(epoch, "Runtime epoch")
        integer(expiry, "Completion expiry")
        if not isinstance(scope, Scope) or not isinstance(evidence, Evidence):
            raise ValueError("Typed scope and evidence required")
        if shot is not None and not isinstance(shot, ShotReference):
            raise ValueError("Typed shot reference required")
        digest = fingerprint(
            {
                "job_id": job_id,
                "scope": asdict(scope),
                "epoch": epoch,
                "expiry": expiry,
                "evidence": asdict(evidence),
                "shot": asdict(shot) if shot else None,
            }
        )
        with self.repository.transaction() as connection:
            self._owner(connection)
            duplicate = self._duplicate(connection, operation_id, digest)
            if duplicate is not None:
                return duplicate
            session = self.repository.get(connection, scope.session_id)
            job = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            error = self._clock_error(epoch, expiry)
            if error is None and (
                job is None
                or job["session_id"] != scope.session_id
                or job["status"] != "pending"
                or job["epoch"] != self.epoch
                or Scope.parse(json.loads(job["scope"])) != scope
                or scope != session.scope()
            ):
                error = ("stale_job", "This result no longer belongs to the active take and revision.")
            if error is None and (
                session.mode != Mode.DEMONSTRATION
                or evidence.source != "fixture"
                or evidence.runtime_epoch != self.epoch
                or not 0 <= self.clock() - evidence.captured_monotonic_ns <= COMMAND_TTL_NS
            ):
                error = (
                    "invalid_evidence",
                    "This foundation accepts only fresh, explicitly labeled fixtures.",
                )
            if error is None and (
                (job["kind"] == "plan") != (shot is not None)
                or (shot is not None and shot.source != "fixture")
            ):
                error = ("invalid_result", "Completion content does not match the pending job.")
            if error:
                return self._reject(connection, operation_id, digest, session, error)
            changes = {
                "revision": session.revision + 1,
                "phase": COMPLETIONS[job["kind"]],
                "updated_utc": self.utc(),
            }
            if shot:
                changes["shot"] = shot
            if job["kind"] == "review":
                changes["reviewed_take_id"] = session.take_id
            updated = replace(session, **changes)
            result_evidence = {
                **asdict(evidence),
                "captured_monotonic_ns": str(evidence.captured_monotonic_ns),
            }
            self.repository.save(connection, updated)
            connection.execute(
                "UPDATE jobs SET status='succeeded', result=? WHERE job_id=?",
                (encode({"evidence": result_evidence, "real_media_verified": False}), job_id),
            )
            self.repository.event(
                connection,
                updated,
                "fixture_" + job["kind"] + "_completed",
                {"job_id": job_id, "evidence": result_evidence, "real_media_verified": False},
                self.utc(),
            )
            return self._receipt(
                connection,
                operation_id,
                digest,
                updated,
                {"ok": True, "code": "applied", "session": updated.wire(), "replayed": False},
            )
