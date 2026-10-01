"""SQLite persistence for simulated takes and their lifecycle evidence."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE recording_runtime (singleton INTEGER PRIMARY KEY CHECK(singleton=1), epoch TEXT NOT NULL);
CREATE TABLE recording_takes (
    take_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    scenario TEXT NOT NULL,
    start_request_id TEXT NOT NULL UNIQUE,
    context TEXT NOT NULL,
    zoom TEXT NOT NULL,
    media TEXT,
    error TEXT,
    created_ns TEXT NOT NULL,
    start_request_ns TEXT NOT NULL,
    start_ack_due_ns TEXT,
    start_timeout_due_ns TEXT,
    stop_request_ns TEXT,
    stop_timeout_due_ns TEXT,
    plan_id TEXT,
    source TEXT NOT NULL DEFAULT 'simulated' CHECK(source IN ('simulated','phone')),
    media_location TEXT,
    device_reported TEXT
);
CREATE TABLE recording_operations (
    request_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    take_id TEXT NOT NULL REFERENCES recording_takes(take_id)
);
CREATE TABLE recording_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    take_id TEXT NOT NULL REFERENCES recording_takes(take_id),
    state TEXT NOT NULL,
    kind TEXT NOT NULL,
    runtime_epoch TEXT NOT NULL,
    request_monotonic_ns TEXT,
    ack_monotonic_ns TEXT,
    detail TEXT NOT NULL
);
CREATE TABLE take_verdicts (
    take_id TEXT NOT NULL REFERENCES recording_takes(take_id),
    prompt_version INTEGER NOT NULL,
    score REAL NOT NULL,
    signals TEXT NOT NULL,
    reason TEXT NOT NULL,
    model TEXT NOT NULL,
    created_ns TEXT NOT NULL,
    PRIMARY KEY (take_id, prompt_version)
);
CREATE INDEX recording_takes_state ON recording_takes(state);
CREATE INDEX recording_takes_plan ON recording_takes(plan_id);
CREATE INDEX recording_events_take ON recording_events(take_id, sequence);
PRAGMA user_version=3;
"""

# The compiled plan that produced a take: intent-versus-result review joins on
# it, so it is a real column rather than a value buried inside the context JSON.
# The device class that acknowledged a take. Simulated takes keep synthetic
# media this server validated; phone takes keep their clip on the handset, so
# `media` is null, `media_location` says where the footage actually is, and
# `real_media_verified` stays false because TakeOne has never read those bytes.
MIGRATION_2_TO_3 = """
ALTER TABLE recording_takes ADD COLUMN source TEXT NOT NULL DEFAULT 'simulated';
ALTER TABLE recording_takes ADD COLUMN media_location TEXT;
ALTER TABLE recording_takes ADD COLUMN device_reported TEXT;
PRAGMA user_version=3;
"""

MIGRATION_1_TO_2 = """
ALTER TABLE recording_takes ADD COLUMN plan_id TEXT;
CREATE INDEX recording_takes_plan ON recording_takes(plan_id);
CREATE TABLE take_verdicts (
    take_id TEXT NOT NULL REFERENCES recording_takes(take_id),
    prompt_version INTEGER NOT NULL,
    score REAL NOT NULL,
    signals TEXT NOT NULL,
    reason TEXT NOT NULL,
    model TEXT NOT NULL,
    created_ns TEXT NOT NULL,
    PRIMARY KEY (take_id, prompt_version)
);
PRAGMA user_version=2;
"""


def encode(value):
    return json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class RuntimeReplacedError(RuntimeError):
    pass


class FinalizationAdmission:
    """A process-safe lease whose SQLite lock is released automatically on exit."""

    def __init__(self, database: Path):
        database = Path(database)
        self.path = database.with_name(f"{database.name}.finalization.sqlite3")
        self.connection = None

    def acquire(self):
        if self.connection is not None:
            return False
        connection = sqlite3.connect(
            self.path,
            timeout=0,
            isolation_level=None,
            check_same_thread=False,
        )
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            connection.close()
            if getattr(error, "sqlite_errorcode", None) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                return False
            raise
        self.connection = connection
        return True

    def release(self):
        connection, self.connection = self.connection, None
        if connection is None:
            return
        try:
            connection.rollback()
        finally:
            connection.close()


class RecordingRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            takes_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recording_takes'"
            ).fetchone()
            if version == 0:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                if tables:
                    raise ValueError("Refusing to initialize an unrelated database")
                connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
            elif version in (1, 2) and takes_table:
                if version == 1:
                    connection.executescript("BEGIN IMMEDIATE;\n" + MIGRATION_1_TO_2 + "\nCOMMIT;")
                connection.executescript("BEGIN IMMEDIATE;\n" + MIGRATION_2_TO_3 + "\nCOMMIT;")
            elif version != 3 or not takes_table:
                raise ValueError("Unsupported or unrelated recording database")
            connection.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def owner(connection, epoch):
        row = connection.execute("SELECT epoch FROM recording_runtime WHERE singleton=1").fetchone()
        if row is None or row["epoch"] != epoch:
            raise RuntimeReplacedError

    def claim(self, epoch, now_ns):
        with self.transaction() as connection:
            unfinished = connection.execute(
                "SELECT take_id, state, start_request_ns, stop_request_ns FROM recording_takes "
                "WHERE state IN ('starting','recording','finalizing')"
            ).fetchall()
            for row in unfinished:
                error = {"code": "runtime_restarted", "message": "Runtime restarted with unfinished work."}
                connection.execute(
                    "UPDATE recording_takes SET state='unknown', error=?, start_ack_due_ns=NULL, "
                    "start_timeout_due_ns=NULL, stop_timeout_due_ns=NULL WHERE take_id=?",
                    (encode(error), row["take_id"]),
                )
                self.event(
                    connection,
                    row["take_id"],
                    "unknown",
                    "runtime_restarted",
                    epoch,
                    None,
                    now_ns,
                    {"previous_state": row["state"], "work_resumed": False},
                )
            connection.execute(
                "INSERT INTO recording_runtime VALUES (1, ?) "
                "ON CONFLICT(singleton) DO UPDATE SET epoch=excluded.epoch",
                (epoch,),
            )

    @staticmethod
    def event(connection, take_id, state, kind, epoch, request_ns, ack_ns, detail):
        connection.execute(
            "INSERT INTO recording_events(take_id,state,kind,runtime_epoch,request_monotonic_ns,"
            "ack_monotonic_ns,detail) VALUES (?,?,?,?,?,?,?)",
            (
                take_id,
                state,
                kind,
                epoch,
                str(request_ns) if request_ns is not None else None,
                str(ack_ns) if ack_ns is not None else None,
                encode(detail),
            ),
        )

    @staticmethod
    def row(connection, take_id):
        return connection.execute("SELECT * FROM recording_takes WHERE take_id=?", (take_id,)).fetchone()

    @staticmethod
    def operation(connection, request_id):
        return connection.execute(
            "SELECT kind,fingerprint,take_id FROM recording_operations WHERE request_id=?", (request_id,)
        ).fetchone()

    @staticmethod
    def add_operation(connection, request_id, kind, fingerprint, take_id):
        connection.execute(
            "INSERT INTO recording_operations(request_id,kind,fingerprint,take_id) VALUES (?,?,?,?)",
            (request_id, kind, fingerprint, take_id),
        )

    def snapshot(self, connection, row):
        events = [
            {
                "sequence": event["sequence"],
                "state": event["state"],
                "kind": event["kind"],
                "runtime_epoch": event["runtime_epoch"],
                "request_monotonic_ns": event["request_monotonic_ns"],
                "ack_monotonic_ns": event["ack_monotonic_ns"],
                "detail": json.loads(event["detail"]),
            }
            for event in connection.execute(
                "SELECT * FROM recording_events WHERE take_id=? ORDER BY sequence", (row["take_id"],)
            )
        ]
        source = row["source"] if "source" in row.keys() and row["source"] else "simulated"
        device_reported = (
            json.loads(row["device_reported"])
            if "device_reported" in row.keys() and row["device_reported"]
            else None
        )
        return {
            "take_id": row["take_id"],
            "state": row["state"],
            "source": source,
            "plan_id": row["plan_id"],
            "context": json.loads(row["context"]),
            "zoom": json.loads(row["zoom"]),
            "events": events,
            "media": json.loads(row["media"]) if row["media"] else None,
            # Where the footage actually is. A phone take keeps its clip on the
            # handset; there is no local file and this server must not invent a path.
            "media_location": (row["media_location"] if "media_location" in row.keys() else None)
            or ("phone_internal_storage" if source == "phone" else None),
            "device_reported": device_reported,
            "optical_framing_verified": False,
            "zoom_mapping": ("estimated_between_operator_measured_points" if source == "phone" else None),
            "error": json.loads(row["error"]) if row["error"] else None,
            # TakeOne has not hashed phone footage and never validates it here.
            "real_media_verified": False,
        }

    @staticmethod
    def record_verdict(connection, take_id, prompt_version, score, signals, reason, model, created_ns):
        """Same prompt version replaces (deterministic recompute); a new version appends."""
        connection.execute(
            "INSERT OR REPLACE INTO take_verdicts VALUES (?,?,?,?,?,?,?)",
            (take_id, prompt_version, score, encode(signals), reason, model, str(created_ns)),
        )

    @staticmethod
    def recent_verdicts(connection, limit=3):
        """Newest verdicts across takes, for the bounded production-state block."""
        return [
            {
                "take_id": row["take_id"],
                "plan_id": row["plan_id"],
                "score": row["score"],
                "reason": row["reason"],
                "prompt_version": row["prompt_version"],
            }
            for row in connection.execute(
                "SELECT v.*, t.plan_id FROM take_verdicts v JOIN recording_takes t USING(take_id) "
                "ORDER BY CAST(v.created_ns AS INTEGER) DESC LIMIT ?",
                (int(limit),),
            )
        ]

    @staticmethod
    def verdicts(connection, take_id):
        return [
            {
                "take_id": row["take_id"],
                "prompt_version": row["prompt_version"],
                "score": row["score"],
                "signals": json.loads(row["signals"]),
                "reason": row["reason"],
                "model": row["model"],
                "created_ns": row["created_ns"],
            }
            for row in connection.execute(
                "SELECT * FROM take_verdicts WHERE take_id=? ORDER BY prompt_version", (take_id,)
            )
        ]
