"""Single-writer offline recording lifecycle and simulated acknowledgement polling."""

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

from .contracts import RecordingError, ZoomRamp
from .media import MediaWriteError, SyntheticMediaWriter
from .repository import FinalizationAdmission, RecordingRepository, RuntimeReplacedError, encode
from .simulated import SCENARIOS, SimulatedRecorder

UNRESOLVED_STATES = frozenset({"starting", "recording", "finalizing", "unknown"})


def _identity(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise RecordingError(
            400, "invalid_request_id", f"{name} must be a non-empty string of at most 200 characters."
        )
    return value


def _take_id(value):
    if not isinstance(value, str):
        raise RecordingError(400, "invalid_take_id", "Take ID must be a canonical UUID.")
    try:
        canonical = str(UUID(value))
    except ValueError:
        canonical = None
    if canonical != value:
        raise RecordingError(400, "invalid_take_id", "Take ID must be a canonical UUID.")
    return value


def _fingerprint(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def _error(code, message):
    return {"code": code, "message": message}


class RecordingService:
    def __init__(
        self,
        database: Path,
        media_root: Path,
        *,
        clock=time.monotonic_ns,
        notify=None,
        simulator=None,
        media_writer=None,
        phone_recorder=None,
    ):
        if not callable(clock):
            raise ValueError("Recording clock must be callable")
        if notify is not None and not callable(notify):
            raise ValueError("Recording notification hook must be callable")
        self.repository = RecordingRepository(Path(database))
        self.media_root = Path(media_root)
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.notify = notify
        self.simulator = simulator if simulator is not None else SimulatedRecorder()
        self.media_writer = media_writer if media_writer is not None else SyntheticMediaWriter()
        # Optional and inert. Without it, `source="phone"` is refused rather
        # than quietly falling back to the simulator.
        self.phone_recorder = phone_recorder
        self.epoch = str(uuid4())
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="takeone-media")
        self._futures = set()
        self._future_lock = threading.Lock()
        self._finalizer_lock = threading.Lock()
        self._finalizer_take_id = None
        self._finalizer_future = None
        self._finalizer_admission = FinalizationAdmission(self.repository.path)
        self._closed = False
        self.repository.claim(self.epoch, self.clock())

    def _owner(self, connection):
        try:
            self.repository.owner(connection, self.epoch)
        except RuntimeReplacedError as error:
            raise RecordingError(
                409, "runtime_replaced", "Another recording runtime owns this database."
            ) from error

    def _notify(self, snapshot, state):
        if self.notify is not None:
            self.notify(snapshot, state)

    def _snapshot(self, connection, take_id):
        row = self.repository.row(connection, take_id)
        if row is None:
            raise RecordingError(404, "take_not_found", "Take was not found.")
        return self.repository.snapshot(connection, row)

    def _duplicate(self, connection, request_id, digest):
        old = self.repository.operation(connection, request_id)
        if old is None:
            return None
        if old["fingerprint"] != digest:
            raise RecordingError(409, "operation_conflict", "This request ID was already used differently.")
        return self._snapshot(connection, old["take_id"])

    def _expected_operation(self, connection, request_id, kind, take_id):
        operation = self.repository.operation(connection, request_id)
        return bool(operation and operation["kind"] == kind and operation["take_id"] == take_id)

    def _expected_stop(self, connection, take_id, request_id, request_ns):
        row = self.repository.row(connection, take_id)
        if (
            row is None
            or row["state"] != "finalizing"
            or row["stop_request_ns"] != str(request_ns)
            or not self._expected_operation(connection, request_id, "stop", take_id)
        ):
            return None
        return row

    def _reserve_finalizer(self, take_id):
        with self._finalizer_lock:
            if self._closed or self._finalizer_take_id is not None or not self._finalizer_admission.acquire():
                return False
            self._finalizer_take_id = take_id
            self._finalizer_future = None
            return True

    def _release_finalizer(self, take_id, future=None):
        with self._finalizer_lock:
            if self._finalizer_take_id != take_id:
                return
            if future is not None and self._finalizer_future is not future:
                return
            self._finalizer_take_id = None
            self._finalizer_future = None
            self._finalizer_admission.release()

    def _cancel_finalizer(self, take_id):
        with self._finalizer_lock:
            if self._finalizer_take_id != take_id:
                return
            future = self._finalizer_future
            if future is None:
                self._finalizer_take_id = None
                self._finalizer_admission.release()
                return
        future.cancel()

    def _release_inactive_finalizer(self):
        with self._finalizer_lock:
            future = self._finalizer_future
            if self._finalizer_take_id is None or (future is not None and not future.done()):
                return
            self._finalizer_take_id = None
            self._finalizer_future = None
            self._finalizer_admission.release()

    def _poll(self, take_id):
        changed = None
        with self.repository.transaction() as connection:
            self._owner(connection)
            row = self.repository.row(connection, take_id)
            if row is None:
                raise RecordingError(404, "take_not_found", "Take was not found.")
            now = self.clock()
            if row["state"] == "starting":
                acknowledge_at = int(row["start_ack_due_ns"]) if row["start_ack_due_ns"] else None
                timeout_at = int(row["start_timeout_due_ns"]) if row["start_timeout_due_ns"] else None
                if acknowledge_at is not None and now >= acknowledge_at:
                    connection.execute(
                        "UPDATE recording_takes SET state='recording', error=NULL, start_ack_due_ns=NULL, "
                        "start_timeout_due_ns=NULL WHERE take_id=?",
                        (take_id,),
                    )
                    self.repository.event(
                        connection,
                        take_id,
                        "recording",
                        "start_acknowledged",
                        self.epoch,
                        row["start_request_ns"],
                        acknowledge_at if row["source"] == "phone" else now,
                        {"source": "device_reported" if row["source"] == "phone" else "simulated"},
                    )
                    changed = "recording"
                elif timeout_at is not None and now >= timeout_at:
                    connection.execute(
                        "UPDATE recording_takes SET state='unknown', error=?, start_ack_due_ns=NULL, "
                        "start_timeout_due_ns=NULL WHERE take_id=?",
                        (
                            encode(_error("start_timeout", "Simulated start acknowledgement timed out.")),
                            take_id,
                        ),
                    )
                    self.repository.event(
                        connection,
                        take_id,
                        "unknown",
                        "start_timeout",
                        self.epoch,
                        row["start_request_ns"],
                        None,
                        {"device_state_known": False},
                    )
                    changed = "unknown"
            elif row["state"] == "finalizing" and row["stop_timeout_due_ns"]:
                if now >= int(row["stop_timeout_due_ns"]):
                    connection.execute(
                        "UPDATE recording_takes SET state='unknown', error=?, stop_timeout_due_ns=NULL "
                        "WHERE take_id=?",
                        (
                            encode(_error("stop_timeout", "Simulated stop acknowledgement timed out.")),
                            take_id,
                        ),
                    )
                    self.repository.event(
                        connection,
                        take_id,
                        "unknown",
                        "stop_timeout",
                        self.epoch,
                        row["stop_request_ns"],
                        None,
                        {"device_state_known": False},
                    )
                    changed = "unknown"
            snapshot = self._snapshot(connection, take_id)
        if changed is not None:
            self._notify(snapshot, changed)
        return snapshot

    SOURCES = ("simulated", "phone")

    def start(self, request_id, context, zoom=None, scenario="normal", *, plan_id=None, source="simulated"):
        _identity(request_id, "Start request ID")
        if not isinstance(context, dict):
            raise RecordingError(400, "invalid_context", "Recording context must be a JSON object.")
        if source not in self.SOURCES:
            raise RecordingError(
                400, "invalid_source", "source must be one of: " + ", ".join(self.SOURCES) + "."
            )
        # A zoom ramp and a fault-injection scenario belong to the simulator. A
        # real device has neither, so both are optional and source-dependent
        # rather than an eighth scenario value called "phone".
        if source == "simulated":
            if not isinstance(zoom, ZoomRamp):
                raise RecordingError(400, "invalid_zoom", "A typed ZoomRamp is required.")
            if scenario not in SCENARIOS:
                raise RecordingError(400, "invalid_scenario", "Unknown simulated recording scenario.")
        else:
            if zoom is not None and not isinstance(zoom, ZoomRamp):
                raise RecordingError(400, "invalid_zoom", "A typed ZoomRamp is required.")
            if self.phone_recorder is None:
                raise RecordingError(
                    409, "phone_recorder_unavailable", "No phone capture adapter is connected."
                )
            scenario = ""
        try:
            context = json.loads(encode(context))
        except (TypeError, ValueError) as error:
            raise RecordingError(
                400, "invalid_context", "Recording context must contain finite JSON values."
            ) from error
        # The compiled plan that produced this take, when the caller names one —
        # explicitly, or through its scope. Stored as a real column so review can
        # join intent to result.
        if plan_id is None:
            scope = context.get("scope")
            plan_id = scope.get("plan_id") if isinstance(scope, dict) else None
        if plan_id is not None and not (
            isinstance(plan_id, str)
            and len(plan_id) == 64
            and all(character in "0123456789abcdef" for character in plan_id)
        ):
            raise RecordingError(400, "invalid_context", "plan_id must be a lowercase SHA-256 digest.")
        zoom_wire = zoom.wire() if isinstance(zoom, ZoomRamp) else None
        start_identity = {
            "kind": "start",
            "context": context,
            "zoom": zoom_wire,
            "scenario": scenario,
            "source": source,
        }
        if plan_id is not None:
            # Only added when present so pre-plan request fingerprints replay unchanged.
            start_identity["plan_id"] = plan_id
        digest = _fingerprint(start_identity)
        now = self.clock()
        take_id = str(uuid4())
        with self.repository.transaction() as connection:
            self._owner(connection)
            duplicate = self._duplicate(connection, request_id, digest)
            if duplicate is not None:
                return duplicate
            unresolved = connection.execute(
                "SELECT take_id FROM recording_takes WHERE state IN ('starting','recording','finalizing','unknown') "
                "LIMIT 1"
            ).fetchone()
            if unresolved:
                raise RecordingError(
                    409, "take_unresolved", "Resolve the active take before starting another."
                )
            connection.execute(
                "INSERT INTO recording_takes(take_id,state,scenario,start_request_id,context,zoom,media,error,"
                "created_ns,start_request_ns,start_ack_due_ns,start_timeout_due_ns,stop_request_ns,"
                "stop_timeout_due_ns,plan_id,source,media_location) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    take_id,
                    "starting",
                    scenario,
                    request_id,
                    encode(context),
                    encode(zoom_wire),
                    None,
                    None,
                    str(now),
                    str(now),
                    None,
                    None,
                    None,
                    None,
                    plan_id,
                    source,
                    "phone_internal_storage" if source == "phone" else None,
                ),
            )
            self.repository.add_operation(connection, request_id, "start", digest, take_id)
            self.repository.event(
                connection,
                take_id,
                "starting",
                "start_requested",
                self.epoch,
                now,
                None,
                {"scenario": scenario, "source": source},
            )
            snapshot = self._snapshot(connection, take_id)
        self._notify(snapshot, "requested")
        try:
            if source == "phone":
                # The adapter blocks on the device's own readback before
                # returning, so the acknowledgement time it reports is measured,
                # not predicted.
                attempt = self.phone_recorder.request_start(take_id, context, now)
            else:
                attempt = self.simulator.request_start(take_id, scenario, now)
        except Exception as error:
            applied = False
            with self.repository.transaction() as connection:
                self._owner(connection)
                row = self.repository.row(connection, take_id)
                if (
                    row is not None
                    and row["state"] == "starting"
                    and row["start_request_id"] == request_id
                    and self._expected_operation(connection, request_id, "start", take_id)
                ):
                    connection.execute(
                        "UPDATE recording_takes SET state='unknown', error=? WHERE take_id=?",
                        (
                            encode(
                                _error(
                                    "simulator_unavailable",
                                    str(error)[:200] or "Simulator unavailable.",
                                )
                            ),
                            take_id,
                        ),
                    )
                    self.repository.event(
                        connection,
                        take_id,
                        "unknown",
                        "start_dispatch_failed",
                        self.epoch,
                        now,
                        None,
                        {"device_state_known": False},
                    )
                    applied = True
                snapshot = self._snapshot(connection, take_id)
            if applied:
                self._notify(snapshot, "unknown")
            return snapshot
        applied = False
        with self.repository.transaction() as connection:
            self._owner(connection)
            row = self.repository.row(connection, take_id)
            if (
                row is not None
                and row["state"] == "starting"
                and row["start_request_id"] == request_id
                and self._expected_operation(connection, request_id, "start", take_id)
            ):
                connection.execute(
                    "UPDATE recording_takes SET start_ack_due_ns=?, start_timeout_due_ns=? WHERE take_id=?",
                    (
                        str(attempt.acknowledge_at_ns) if attempt.acknowledge_at_ns is not None else None,
                        str(attempt.timeout_at_ns),
                        take_id,
                    ),
                )
                applied = True
            snapshot = self._snapshot(connection, take_id)
        if applied:
            self._notify(snapshot, "starting")
        return snapshot

    def get(self, take_id):
        return self._poll(_take_id(take_id))

    def list_takes(self):
        with self.repository.connect() as connection:
            connection.execute("BEGIN")
            self._owner(connection)
            rows = connection.execute(
                "SELECT * FROM recording_takes ORDER BY rowid DESC LIMIT 100"
            ).fetchall()
            return [self.repository.snapshot(connection, row) for row in rows]

    def stop(self, take_id, request_id):
        take_id = _take_id(take_id)
        _identity(request_id, "Stop request ID")
        digest = _fingerprint({"kind": "stop", "take_id": take_id})
        current = self._poll(take_id)
        now = self.clock()
        reserved = False
        worker_owned = False
        try:
            with self.repository.transaction() as connection:
                self._owner(connection)
                duplicate = self._duplicate(connection, request_id, digest)
                if duplicate is not None:
                    return duplicate
                row = self.repository.row(connection, take_id)
                if row["state"] not in {"starting", "recording"}:
                    raise RecordingError(
                        409, "invalid_transition", "This take cannot be stopped from its current state."
                    )
                if row["state"] == "recording":
                    if not self._reserve_finalizer(take_id):
                        raise RecordingError(
                            409,
                            "finalization_busy",
                            "Wait for the previous synthetic finalization before stopping this take.",
                        )
                    reserved = True
                self.repository.add_operation(connection, request_id, "stop", digest, take_id)
                connection.execute(
                    "UPDATE recording_takes SET state='finalizing', stop_request_ns=?, error=NULL "
                    "WHERE take_id=?",
                    (str(now), take_id),
                )
                self.repository.event(
                    connection,
                    take_id,
                    "finalizing",
                    "stop_requested",
                    self.epoch,
                    now,
                    None,
                    {"source": row["source"], "previous_state": row["state"]},
                )
                snapshot = self._snapshot(connection, take_id)
                previous_state = row["state"]
                scenario = row["scenario"]
                source = row["source"]
            self._notify(snapshot, "finalizing")
            try:
                if source == "phone":
                    attempt = self.phone_recorder.request_stop(take_id, now)
                else:
                    attempt = self.simulator.request_stop(take_id, scenario, now)
            except Exception as failure:
                return self._uncertain_stop(
                    take_id,
                    request_id,
                    now,
                    "simulator_unavailable",
                    str(failure)[:200] or "Simulated stop request failed.",
                    "stop_dispatch_failed",
                )
            if attempt.outcome == "disconnect":
                return self._uncertain_stop(
                    take_id,
                    request_id,
                    now,
                    "disconnect",
                    "Simulated recorder disconnected before stop confirmation.",
                    "recorder_disconnected",
                )
            if attempt.outcome == "timeout":
                with self.repository.transaction() as connection:
                    self._owner(connection)
                    if self._expected_stop(connection, take_id, request_id, now) is not None:
                        connection.execute(
                            "UPDATE recording_takes SET stop_timeout_due_ns=? WHERE take_id=?",
                            (str(attempt.timeout_at_ns), take_id),
                        )
                    snapshot = self._snapshot(connection, take_id)
                return snapshot

            applied = False
            with self.repository.transaction() as connection:
                self._owner(connection)
                if self._expected_stop(connection, take_id, request_id, now) is not None:
                    if previous_state == "starting":
                        error = _error(
                            "retired_before_start", "Take was stopped before start acknowledgement."
                        )
                        connection.execute(
                            "UPDATE recording_takes SET state='failed', error=?, start_ack_due_ns=NULL, "
                            "start_timeout_due_ns=NULL WHERE take_id=?",
                            (encode(error), take_id),
                        )
                        state, kind = "failed", "start_retired"
                    else:
                        state, kind = "finalizing", "stop_acknowledged"
                    self.repository.event(
                        connection,
                        take_id,
                        state,
                        kind,
                        self.epoch,
                        now,
                        self.clock() if source == "phone" else now,
                        {
                            "source": "device_reported" if source == "phone" else source,
                            "media_pending": previous_state == "recording" and source != "phone",
                        },
                    )
                    applied = True
                snapshot = self._snapshot(connection, take_id)
            if not applied:
                return snapshot
            self._notify(snapshot, "stopped")
            if previous_state == "recording":
                if source == "phone":
                    # There is nothing here to validate: the clip is on the
                    # handset and this server has never seen those bytes.
                    return self._settle_phone_take(take_id, now)
                worker_owned = self._submit_finalizer(take_id, current["zoom"]["duration_ms"], scenario, now)
            return snapshot
        finally:
            if reserved and not worker_owned:
                self._release_finalizer(take_id)

    def _settle_phone_take(self, take_id, now):
        """A phone take finishes when the device confirms it stopped.

        `media` stays null, `media_location` says where the footage is, and
        `real_media_verified` stays false everywhere.
        """
        report = self.phone_recorder.report(take_id)
        with self.repository.transaction() as connection:
            self._owner(connection)
            connection.execute(
                "UPDATE recording_takes SET state='ready', media=NULL, error=NULL, "
                "media_location='phone_internal_storage', device_reported=?, "
                "stop_timeout_due_ns=NULL WHERE take_id=?",
                (encode(report), take_id),
            )
            self.repository.event(
                connection,
                take_id,
                "ready",
                "device_reported_stop",
                self.epoch,
                None,
                now,
                {
                    "source": "device_reported",
                    "media_verified": False,
                    "media_location": "phone_internal_storage",
                    "record_ack_clock_s": report.get("record_ack_clock_s"),
                    "zoom_mapping": "estimated_between_operator_measured_points",
                },
            )
            snapshot = self._snapshot(connection, take_id)
        self._notify(snapshot, "ready")
        return snapshot

    def _uncertain_stop(self, take_id, request_id, request_ns, code, message, kind):
        applied = False
        with self.repository.transaction() as connection:
            self._owner(connection)
            if self._expected_stop(connection, take_id, request_id, request_ns) is not None:
                connection.execute(
                    "UPDATE recording_takes SET state='unknown', error=? WHERE take_id=?",
                    (encode(_error(code, message)), take_id),
                )
                self.repository.event(
                    connection,
                    take_id,
                    "unknown",
                    kind,
                    self.epoch,
                    request_ns,
                    None,
                    {"device_state_known": False},
                )
                applied = True
            snapshot = self._snapshot(connection, take_id)
        if applied:
            self._notify(snapshot, "unknown")
        return snapshot

    def _submit_finalizer(self, take_id, duration_ms, scenario, request_ns):
        with self._finalizer_lock:
            if self._closed or self._finalizer_take_id != take_id or self._finalizer_future is not None:
                return False
            future = self._executor.submit(self._finalize, take_id, duration_ms, scenario, request_ns)
            self._finalizer_future = future
        with self._future_lock:
            self._futures.add(future)
        future.add_done_callback(lambda completed: self._forget_future(take_id, completed))
        return True

    def _forget_future(self, take_id, future):
        with self._future_lock:
            self._futures.discard(future)
        self._release_finalizer(take_id, future)

    def _finalize(self, take_id, duration_ms, scenario, request_ns):
        try:
            with self.repository.connect() as connection:
                connection.execute("BEGIN")
                self.repository.owner(connection, self.epoch)
                row = self.repository.row(connection, take_id)
                if row is None or row["state"] != "finalizing" or row["stop_timeout_due_ns"]:
                    return
        except RuntimeReplacedError:
            return
        try:
            media = self.media_writer.write(take_id, self.media_root, duration_ms, scenario)
            state, error, kind = "ready", None, "media_validated"
        except MediaWriteError as failure:
            media = None
            state, kind = "failed", "media_failed"
            error = _error(failure.code, str(failure)[:240])
        except Exception as failure:
            media = None
            state, kind = "failed", "media_failed"
            error = _error("media_write_failed", str(failure)[:240] or "Media writer failed.")
        try:
            with self.repository.transaction() as connection:
                self.repository.owner(connection, self.epoch)
                row = self.repository.row(connection, take_id)
                if row is None or row["state"] != "finalizing" or row["stop_timeout_due_ns"]:
                    return
                connection.execute(
                    "UPDATE recording_takes SET state=?, media=?, error=? WHERE take_id=?",
                    (state, encode(media) if media else None, encode(error) if error else None, take_id),
                )
                self.repository.event(
                    connection,
                    take_id,
                    state,
                    kind,
                    self.epoch,
                    request_ns,
                    self.clock(),
                    {"synthetic": True, "real_media_verified": False},
                )
                snapshot = self._snapshot(connection, take_id)
        except RuntimeReplacedError:
            return
        self._notify(snapshot, state)

    def recover(self, take_id, request_id):
        take_id = _take_id(take_id)
        _identity(request_id, "Recovery request ID")
        digest = _fingerprint({"kind": "recover", "take_id": take_id})
        now = self.clock()
        current = self.get(take_id)
        phone_idle = None
        if current["source"] == "phone" and current["state"] in UNRESOLVED_STATES:
            if self.phone_recorder is None:
                raise RecordingError(
                    409, "phone_recovery_required", "Reconnect the phone before resolving this take."
                )
            try:
                phone_idle = self.phone_recorder.recover(take_id)
            except Exception as error:
                raise RecordingError(409, "phone_recovery_required", str(error)) from error
        with self.repository.transaction() as connection:
            self._owner(connection)
            duplicate = self._duplicate(connection, request_id, digest)
            if duplicate is not None:
                return duplicate
            row = self.repository.row(connection, take_id)
            if row is None:
                raise RecordingError(404, "take_not_found", "Take was not found.")
            if row["state"] not in UNRESOLVED_STATES:
                raise RecordingError(409, "invalid_transition", "This take does not require recovery.")
            self.repository.add_operation(connection, request_id, "recover", digest, take_id)
            connection.execute(
                "UPDATE recording_takes SET state='failed', error=?, start_ack_due_ns=NULL, "
                "start_timeout_due_ns=NULL, stop_timeout_due_ns=NULL WHERE take_id=?",
                (encode(_error("recovered", "Unfinished take was retired explicitly.")), take_id),
            )
            self.repository.event(
                connection,
                take_id,
                "failed",
                "recovery_retired",
                self.epoch,
                now,
                now,
                {
                    "previous_state": row["state"],
                    "media_verified": False,
                    **({"phone_idle": phone_idle} if phone_idle else {}),
                },
            )
            snapshot = self._snapshot(connection, take_id)
        self._cancel_finalizer(take_id)
        self._notify(snapshot, "stopped")
        return snapshot

    def media_path(self, take_id):
        take_id = _take_id(take_id)
        snapshot = self.get(take_id)
        if snapshot["state"] != "ready" or snapshot["media"] is None:
            raise RecordingError(409, "media_unavailable", "Validated media is not available for this take.")
        expected_relative = f"{take_id}/synthetic.mp4"
        if snapshot["media"].get("relative_path") != expected_relative:
            raise RecordingError(409, "media_integrity_failed", "Persisted media identity is invalid.")
        path = (self.media_root / expected_relative).resolve()
        root = self.media_root.resolve()
        if path.parent != root / take_id or not path.is_file():
            raise RecordingError(409, "media_integrity_failed", "Persisted media file is missing.")
        content = path.read_bytes()
        if len(content) != snapshot["media"].get("size_bytes") or hashlib.sha256(
            content
        ).hexdigest() != snapshot["media"].get("sha256"):
            raise RecordingError(409, "media_integrity_failed", "Persisted media checksum changed.")
        return path

    def close(self):
        with self._finalizer_lock:
            if self._closed:
                return
            self._closed = True
        try:
            if self.phone_recorder is not None and hasattr(self.phone_recorder, "close"):
                self.phone_recorder.close()
        finally:
            try:
                self._executor.shutdown(wait=True, cancel_futures=True)
            finally:
                self._release_inactive_finalizer()
