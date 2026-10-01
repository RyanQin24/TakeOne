"""Transactional creative use cases and one bounded, untimed provider worker."""

import copy
import json
import threading
from dataclasses import asdict, replace
from uuid import uuid4

from .capabilities import inspect_capabilities
from .contracts import Mode, Phase, ProductionBrief, Scope, encode, fields, identity, text
from .creative import (
    LINES_SCHEMA,
    PRIMITIVES,
    all_shots,
    constraints,
    digest,
    validate,
    validate_context,
    validate_lines,
    validate_plan,
    plan_schema,
    repair_schema,
)
from .provider import PlanningError, ResponsesPlanner
from .service import OwnerReplacedError
from .skills import SKILLS, sample_project
from .studio import movement_catalog, shot_diagnostic, shot_settings, skill_text


class CreativePlanning:
    """Shares the session owner's lease/receipts; no independent session owner or device access."""

    def __init__(self, service, provider=None):
        self.service = service
        self.repository = service.repository
        self.provider = provider if provider is not None else ResponsesPlanner()
        self._worker_lock = threading.Lock()

    def capabilities_digest(self):
        snapshot = inspect_capabilities(self.service.epoch, self.service.clock())
        return digest({"configuration_hashes": snapshot.configuration_hashes, "primitives": PRIMITIVES,
                       "movements": movement_catalog(), "filming_skill": skill_text()})

    def status(self):
        return {
            "provider": self.provider.status(),
            "skills": list(SKILLS.values()),
            "primitives": PRIMITIVES,
            "preview_compiler_connected": True,
            "movement_catalog": movement_catalog(),
        }

    def _save(self, connection, session, document, context, provenance, approved=False):
        connection.execute(
            "INSERT INTO creative_revisions VALUES (?,?,?,?,?,?,?)",
            (
                session.session_id,
                session.revision,
                session.cancellation_generation,
                encode(document),
                encode(context),
                encode(provenance),
                int(approved),
            ),
        )

    def submit(self, body, expiry):
        fields(
            body,
            (
                "schema_version",
                "operation_id",
                "runtime_epoch",
                "expires_monotonic_ns",
                "scope",
                "action",
                "payload",
            ),
        )
        if type(body["schema_version"]) is not int or body["schema_version"] != 1:
            raise ValueError("Unsupported creative request schema")
        operation = identity(body["operation_id"])
        identity(body["runtime_epoch"])
        scope = Scope.parse(body["scope"])
        action, payload = body["action"], body["payload"]
        if action not in (
            "load_sample",
            "save_document",
            "approve_script",
            "request_plan",
            "request_lines",
            "save_brief",
            "start_script",
            "cancel_planning",
            "repair_shots",
        ):
            raise ValueError("Unknown creative action")
        request_digest = digest(body)
        service = self.service
        job_id = None
        with self.repository.transaction() as connection:
            service._owner(connection)
            duplicate = service._duplicate(connection, operation, request_digest)
            if duplicate is not None:
                return duplicate
            session = self.repository.get(connection, scope.session_id)
            error = service._clock_error(body["runtime_epoch"], expiry)
            if error is None and session.scope() != scope:
                error = ("stale_scope", "This production changed. Reload it before applying your edit.")
            editable_phases = (
                Phase.BRIEF,
                Phase.SCRIPT,
                Phase.PLANNING,
                Phase.FAULT,
                Phase.PREVIEW,
                Phase.REHEARSAL,
                Phase.READY,
                Phase.REVIEW,
                Phase.ACCEPTED,
            )
            if action == "save_brief":
                editable_phases += (Phase.CANCELLED,)
            if error is None and (session.mode != Mode.PLANNING or session.phase not in editable_phases):
                error = ("invalid_stage", "Creative editing is not available in this production stage.")
            if error:
                return service._reject(connection, operation, request_digest, session, error)
            current = self.repository.creative(connection, session)
            try:
                if action in ("request_plan", "request_lines", "repair_shots"):
                    updated, job_id = self._start(connection, session, current, action, payload)
                else:
                    updated = self._edit(connection, session, current, action, payload)
            except PlanningError as exc:
                return service._reject(connection, operation, request_digest, session, (exc.code, str(exc)))
            self.repository.save(connection, updated)
            self.repository.event(connection, updated, action, {"job_id": job_id}, service.utc())
            result = service._receipt(
                connection,
                operation,
                request_digest,
                updated,
                {
                    "ok": True,
                    "code": "planning" if job_id else "saved",
                    "session": updated.wire(),
                    "job_id": job_id,
                    "replayed": False,
                },
            )
        if job_id:
            self._dispatch(job_id)
        return result

    def _edit(self, connection, session, current, action, payload):
        approved = action == "approve_script"
        if action == "save_brief":
            fields(payload, ("brief", "context"))
            brief = ProductionBrief.parse(payload["brief"])
            context = validate_context(payload["context"])
            connection.execute(
                "INSERT INTO creative_briefs VALUES (?,?) ON CONFLICT(session_id) "
                "DO UPDATE SET context=excluded.context",
                (session.session_id, encode(context)),
            )
            connection.execute(
                "UPDATE jobs SET status='cancelled' WHERE session_id=? AND status='pending'",
                (session.session_id,),
            )
            return replace(
                session,
                brief=brief,
                revision=session.revision + 1,
                phase=Phase.BRIEF,
                cancellation_generation=session.cancellation_generation + 1,
                shot=None,
                take_id=None,
                reviewed_take_id=None,
                updated_utc=self.service.utc(),
            )
        if action == "cancel_planning":
            fields(payload, ())
            if session.phase != Phase.PLANNING:
                raise PlanningError("not_planning", "There is no pending plan to cancel.")
            connection.execute(
                "UPDATE jobs SET status='cancelled' WHERE session_id=? AND status='pending'",
                (session.session_id,),
            )
            updated = replace(
                session,
                revision=session.revision + 1,
                cancellation_generation=session.cancellation_generation + 1,
                phase=Phase.SCRIPT if current else Phase.BRIEF,
                updated_utc=self.service.utc(),
            )
            if current:
                self._save(
                    connection, updated, current["document"], current["context"], current["provenance"]
                )
            return updated
        if action == "load_sample":
            fields(payload, ("skill_id",))
            if payload["skill_id"] not in SKILLS:
                raise ValueError("Unknown sample")
            if session.revision != 0 or session.phase != Phase.BRIEF:
                raise PlanningError("sample_requires_new", "Open samples in a new production.")
            sample = sample_project(payload["skill_id"])
            # Samples are selected explicitly and cannot be presented as analysis of a custom brief.
            if asdict(session.brief) != sample["brief"]:
                raise PlanningError("sample_brief_mismatch", "Create the sample with its supplied brief.")
            document, context = sample["document"], sample["context"]
            provenance = {
                "source": "curated_sample",
                "skill_id": context["skill_id"],
                "skill_version": SKILLS[context["skill_id"]]["version"],
            }
        elif action == "start_script":
            fields(payload, ("document", "context"))
            if current is not None:
                raise PlanningError("script_exists", "Edit the existing script instead of replacing it.")
            context = validate_context(payload["context"])
            document = payload["document"]
            provenance = {"source": "manual_draft", "last_change": "user_edit"}
        else:
            if current is None:
                raise PlanningError("script_required", "Create a script before editing or approving it.")
            if approved:
                fields(payload, ("document_digest",))
                if payload["document_digest"] != current["digest"]:
                    raise PlanningError("stale_document", "The script changed before approval.")
                document = current["document"]
                if any(c["status"] == "unsupported" for c in constraints(document)):
                    raise PlanningError(
                        "unsupported_move", "Revise the unsupported camera moves before approval."
                    )
            else:
                fields(payload, ("document",))
                document = payload["document"]
            context = current["context"]
            provenance = {
                **current["provenance"],
                "last_change": "user_approval" if approved else "user_edit",
            }
        validate_plan(document, session.brief, context)
        connection.execute(
            "INSERT INTO creative_briefs VALUES (?,?) ON CONFLICT(session_id) "
            "DO UPDATE SET context=excluded.context",
            (session.session_id, encode(context)),
        )
        connection.execute(
            "UPDATE jobs SET status='cancelled' WHERE session_id=? AND status='pending'",
            (session.session_id,),
        )
        updated = replace(
            session,
            revision=session.revision + 1,
            phase=Phase.SCRIPT,
            cancellation_generation=session.cancellation_generation + 1,
            shot=None,
            take_id=None,
            reviewed_take_id=None,
            updated_utc=self.service.utc(),
        )
        self._save(connection, updated, document, context, provenance, approved)
        return updated

    REPAIR_ATTEMPT_LIMIT = 2

    def _start(self, connection, session, current, action, payload):
        required = (
            ("context", "budget_consent")
            if action == "request_plan"
            else ("budget_consent",)
            if action == "repair_shots"
            else ("shot_id", "instruction", "budget_consent")
        )
        fields(payload, required)
        if payload["budget_consent"] is not True:
            raise PlanningError(
                "consent_required", "Confirm the displayed request budget before using live AI."
            )
        if not self.provider.status()["available"]:
            raise PlanningError("provider_unavailable", "Live AI is not configured. Your draft is saved.")
        if (
            self._worker_lock.locked()
            or connection.execute(
                "SELECT 1 FROM jobs WHERE status='pending' AND kind IN "
                "('creative_plan','creative_lines','creative_repair')"
            ).fetchone()
        ):
            raise PlanningError(
                "planner_busy", "The planner is finishing another request. Try again shortly."
            )
        if action == "request_plan":
            context = validate_context(payload["context"])
            request = {
                "brief": asdict(session.brief),
                "context": context,
                "skill": SKILLS[context["skill_id"]],
                "capabilities": PRIMITIVES,
                "movement_catalog": movement_catalog(),
            }
            kind = "creative_plan"
        elif action == "request_lines":
            if current is None:
                raise PlanningError("script_required", "Create a script before requesting line alternatives.")
            shot_id = text(payload["shot_id"], "Shot ID", 40)
            text(payload["instruction"], "Line assistance", 400)
            shots = {shot["shot_id"]: shot for shot in all_shots(current["document"])}
            if shot_id not in shots:
                raise ValueError("Unknown shot")
            context = current["context"]
            request = {
                "brief": asdict(session.brief),
                "context": context,
                "skill": SKILLS[context["skill_id"]],
                "shot": shots[shot_id],
                "instruction": payload["instruction"],
                "capabilities": PRIMITIVES,
            }
            kind = "creative_lines"
        if action == "repair_shots":
            if current is None:
                raise PlanningError("script_required", "Create a script before repairing its movements.")
            attempts = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE session_id=? AND kind='creative_repair' "
                "AND status IN ('succeeded','failed')",
                (session.session_id,),
            ).fetchone()[0]
            if attempts >= self.REPAIR_ATTEMPT_LIMIT:
                raise PlanningError(
                    "repair_limit",
                    "This script has used both automatic repair attempts. Adjust the shot yourself.",
                )
            broken = [
                {"shot": shot, "diagnostic": diagnostic.wire()}
                for shot, diagnostic in (
                    (shot, shot_diagnostic(shot)) for shot in all_shots(current["document"])
                )
                if diagnostic is not None
            ]
            if not broken:
                raise PlanningError("nothing_to_repair", "Every shot already translates for the simulator.")
            context = current["context"]
            request = {
                "brief": asdict(session.brief),
                "context": context,
                "skill": SKILLS[context["skill_id"]],
                "shots": broken,
                "attempt": attempts + 1,
                "movement_catalog": movement_catalog(),
            }
            kind = "creative_repair"
        _, reserved = self.provider.request(request, kind)
        spent = connection.execute(
            "SELECT COALESCE(SUM(p.reserved_microusd),0) FROM planning_requests p "
            "JOIN jobs j ON p.job_id=j.job_id WHERE j.session_id=?",
            (session.session_id,),
        ).fetchone()[0]
        if spent + reserved > self.provider.config["session_budget_microusd"]:
            raise PlanningError("session_budget", "This production has reached its planning budget.")
        updated = replace(
            session,
            revision=session.revision + 1,
            phase=Phase.PLANNING,
            shot=None,
            take_id=None,
            reviewed_take_id=None,
            updated_utc=self.service.utc(),
        )
        connection.execute(
            "INSERT INTO creative_briefs VALUES (?,?) ON CONFLICT(session_id) "
            "DO UPDATE SET context=excluded.context",
            (session.session_id, encode(context)),
        )
        job_id = str(uuid4())
        connection.execute(
            "INSERT INTO jobs VALUES (?,?,?,'pending',?,?,NULL)",
            (
                job_id,
                session.session_id,
                kind,
                encode(asdict(updated.scope())),
                self.service.epoch,
            ),
        )
        deadline = self.service.clock() + self.provider.config["timeout_seconds"] * 1_000_000_000
        connection.execute(
            "INSERT INTO planning_requests VALUES (?,?,?,?,?)",
            (
                job_id,
                encode(request),
                self.capabilities_digest(),
                str(deadline),
                reserved,
            ),
        )
        return updated, job_id

    def _dispatch(self, job_id):
        # No queue: one outstanding provider call. A cancelled call retains its slot until it returns.
        if not self._worker_lock.acquire(blocking=False):
            self._finish(job_id, error=PlanningError("planner_busy", "The planning worker is occupied."))
            return
        threading.Thread(target=self._run, args=(job_id,), name="takeone-creative", daemon=True).start()

    def _run(self, job_id):
        deadline = threading.Timer(self.provider.config["timeout_seconds"], self._expire, args=(job_id,))
        deadline.daemon = True
        deadline.start()
        try:
            with self.repository.connect() as connection:
                row = connection.execute(
                    "SELECT j.*,p.payload FROM jobs j JOIN planning_requests p ON j.job_id=p.job_id "
                    "WHERE j.job_id=?",
                    (job_id,),
                ).fetchone()
            if row["status"] != "pending" or row["epoch"] != self.service.epoch:
                return
            try:
                result = self.provider.generate(json.loads(row["payload"]), row["kind"])
                self._finish(job_id, result=result)
            except PlanningError as exc:
                self._finish(job_id, error=exc)
            except Exception:
                # Error state is explicit; provider internals/secrets never enter the UI or logs.
                self._finish(job_id, error=PlanningError("planning_failed", "Planning failed unexpectedly."))
        except OwnerReplacedError:
            pass  # The new owner has already invalidated all pending jobs.
        finally:
            deadline.cancel()
            self._worker_lock.release()

    def _expire(self, job_id):
        try:
            self._finish(
                job_id,
                error=PlanningError(
                    "provider_timeout", "Planning reached its deadline. Any later result will be discarded."
                ),
            )
        except OwnerReplacedError:
            pass  # Reconciliation belongs to the replacement runtime.

    def _finish(self, job_id, result=None, error=None):
        with self.repository.transaction() as connection:
            self.service._owner(connection)
            row = connection.execute(
                "SELECT j.*,p.payload,p.capability_digest,p.deadline_ns FROM jobs j "
                "JOIN planning_requests p ON p.job_id=j.job_id WHERE j.job_id=?",
                (job_id,),
            ).fetchone()
            session = self.repository.get(connection, row["session_id"])
            if row["status"] != "pending":
                return
            if row["epoch"] != self.service.epoch or Scope.parse(json.loads(row["scope"])) != session.scope():
                connection.execute("UPDATE jobs SET status='discarded' WHERE job_id=?", (job_id,))
                return
            if self.service.clock() >= int(row["deadline_ns"]):
                error = PlanningError(
                    "provider_timeout", "The result missed its deadline and was not applied."
                )
            if row["capability_digest"] != self.capabilities_digest():
                error = PlanningError(
                    "capabilities_changed", "Rig capabilities changed during planning. Re-plan."
                )
            request = json.loads(row["payload"])
            current = self.repository.creative(connection, session)
            context = request["context"]
            if error is None:
                try:
                    if row["kind"] == "creative_lines":
                        validate(result.document, LINES_SCHEMA)
                        validate_lines(result.document["lines"], context)
                        document = copy.deepcopy(current["document"])
                        shot = next(
                            s for s in all_shots(document) if s["shot_id"] == request["shot"]["shot_id"]
                        )
                        shot.update(lines=result.document["lines"], selected_line=0)
                    elif row["kind"] == "creative_repair":
                        validate(result.document, repair_schema())
                        document = copy.deepcopy(current["document"])
                        shots = {shot["shot_id"]: shot for shot in all_shots(document)}
                        applied, refused = [], []
                        for repair in result.document["repairs"]:
                            shot = shots.get(repair["shot_id"])
                            if shot is None:
                                refused.append(repair["shot_id"])
                                continue
                            candidate = {**shot, "movement": repair["movement"]}
                            try:
                                # The proposal is never trusted: the compiler decides.
                                shot_settings(candidate)
                            except ValueError:
                                refused.append(repair["shot_id"])
                                continue
                            shot["movement"] = repair["movement"]
                            shot["primitive"] = "template"
                            applied.append(repair["shot_id"])
                        if not applied:
                            raise ValueError("No repaired movement passed the simulator's own validation.")
                    else:
                        document = result.document
                        validate(document, plan_schema(require_marks=False))
                    refused = [] if row["kind"] == "creative_plan" else None
                    validate_plan(document, session.brief, context, refused)
                except (ValueError, KeyError, TypeError, StopIteration):
                    error = PlanningError(
                        "invalid_proposal", "The proposal failed scene validation. It was not applied."
                    )
            updated = replace(
                session,
                revision=session.revision + 1,
                phase=Phase.SCRIPT if error is None or current else Phase.BRIEF,
                updated_utc=self.service.utc(),
            )
            if error is None:
                provenance = {
                    **result.provenance,
                    "skill_id": context["skill_id"],
                    "skill_version": request["skill"]["version"],
                    "capability_digest": row["capability_digest"],
                }
                self._save(connection, updated, document, context, provenance)
                outcome = {"code": "proposal_saved", "provenance": provenance}
                if refused:
                    outcome["unresolved_shot_ids"] = [d.shot_id for d in refused]
                    outcome["diagnostics"] = [d.wire() for d in refused]
                if row["kind"] == "creative_repair":
                    outcome = {
                        "code": "shots_repaired",
                        "provenance": provenance,
                        "repaired_shot_ids": applied,
                        "still_blocked_shot_ids": refused,
                    }
            else:
                outcome = {"code": error.code, "message": str(error)}
            self.repository.save(connection, updated)
            connection.execute(
                "UPDATE jobs SET status=?,result=? WHERE job_id=?",
                (
                    "failed" if error else "succeeded",
                    encode(outcome),
                    job_id,
                ),
            )
            self.repository.event(
                connection,
                updated,
                "planning_failed" if error else "planning_finished",
                {"job_id": job_id, **outcome},
                self.service.utc(),
            )
