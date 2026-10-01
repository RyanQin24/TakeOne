"""A local transaction contains a session change, its event and command receipt."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .contracts import Session, encode

SCHEMA = """
CREATE TABLE runtime (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), epoch TEXT NOT NULL);
CREATE TABLE sessions (session_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL);
CREATE TABLE operations (
    operation_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
    session_id TEXT REFERENCES sessions(session_id), result TEXT NOT NULL
);
CREATE TABLE events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(session_id),
    revision INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL, created_utc TEXT NOT NULL
);
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id),
    kind TEXT NOT NULL, status TEXT NOT NULL, scope TEXT NOT NULL, epoch TEXT NOT NULL,
    result TEXT
);
CREATE INDEX events_session ON events(session_id, sequence);
CREATE INDEX jobs_session ON jobs(session_id, status);
PRAGMA user_version = 1;
"""

CREATIVE_SCHEMA = """
CREATE TABLE creative_briefs (
    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id), context TEXT NOT NULL
);
CREATE TABLE creative_revisions (
    session_id TEXT NOT NULL REFERENCES sessions(session_id), revision INTEGER NOT NULL,
    generation INTEGER NOT NULL, document TEXT NOT NULL, context TEXT NOT NULL,
    provenance TEXT NOT NULL, approved INTEGER NOT NULL CHECK(approved IN (0,1)),
    PRIMARY KEY(session_id, revision)
);
CREATE TABLE planning_requests (
    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id), payload TEXT NOT NULL,
    capability_digest TEXT NOT NULL, deadline_ns TEXT NOT NULL, reserved_microusd INTEGER NOT NULL
);
PRAGMA user_version = 2;
"""


class SessionRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                if tables:
                    raise ValueError("Refusing to initialize an unrelated database")
                connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
                version = 1
            if version == 1:
                connection.executescript("BEGIN IMMEDIATE;\n" + CREATIVE_SCHEMA + "\nCOMMIT;")
            elif version != 2:
                raise ValueError(f"Unsupported Director database schema {version}")
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
    def get(connection, session_id):
        row = connection.execute("SELECT document FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError("Session not found")
        return Session.parse(json.loads(row["document"]))

    @staticmethod
    def save(connection, session):
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
            "revision=excluded.revision, document=excluded.document",
            (session.session_id, session.revision, encode(session.wire())),
        )

    @staticmethod
    def event(connection, session, kind, detail, now_utc):
        connection.execute(
            "INSERT INTO events(session_id, revision, kind, detail, created_utc) VALUES (?, ?, ?, ?, ?)",
            (session.session_id, session.revision, kind, encode(detail), now_utc),
        )

    def list_sessions(self):
        with self.connect() as connection:
            return [
                json.loads(row["document"])
                for row in connection.execute("SELECT document FROM sessions ORDER BY rowid DESC LIMIT 100")
            ]

    def inspect(self, session_id):
        with self.connect() as connection:
            # One read snapshot keeps session, events and jobs mutually consistent.
            connection.execute("BEGIN")
            session = self.get(connection, session_id)
            events = [
                {**dict(row), "detail": json.loads(row["detail"])}
                for row in connection.execute(
                    "SELECT * FROM (SELECT * FROM events WHERE session_id=? "
                    "ORDER BY sequence DESC LIMIT 100) ORDER BY sequence",
                    (session_id,),
                )
            ]
            jobs = [
                {
                    **dict(row),
                    "scope": json.loads(row["scope"]),
                    "result": json.loads(row["result"]) if row["result"] else None,
                }
                for row in connection.execute(
                    "SELECT * FROM jobs WHERE session_id=? ORDER BY rowid DESC LIMIT 100", (session_id,)
                )
            ]
            creative = self.creative(connection, session)
            budget = connection.execute(
                "SELECT COALESCE(SUM(reserved_microusd),0) FROM planning_requests p "
                "JOIN jobs j ON j.job_id=p.job_id WHERE j.session_id=?",
                (session_id,),
            ).fetchone()[0]
            revisions = [
                dict(row)
                for row in connection.execute(
                    "SELECT revision, generation, approved FROM creative_revisions WHERE session_id=? "
                    "ORDER BY revision DESC LIMIT 100",
                    (session_id,),
                )
            ]
            context = connection.execute(
                "SELECT context FROM creative_briefs WHERE session_id=?", (session_id,)
            ).fetchone()
            return {
                "session": session.wire(),
                "events": events,
                "jobs": jobs,
                "creative": creative,
                "creative_history": revisions,
                "reserved_microusd": budget,
                "creative_context": json.loads(context["context"])
                if context
                else creative["context"]
                if creative
                else None,
            }

    @staticmethod
    def creative(connection, session):
        row = connection.execute(
            "SELECT * FROM creative_revisions WHERE session_id=? AND generation=? "
            "ORDER BY revision DESC LIMIT 1",
            (session.session_id, session.cancellation_generation),
        ).fetchone()
        if row is None:
            return None
        from .creative import constraints, digest

        document = json.loads(row["document"])
        return {
            "revision": row["revision"],
            "document": document,
            "digest": digest(document),
            "context": json.loads(row["context"]),
            "provenance": json.loads(row["provenance"]),
            "approved": bool(row["approved"] and row["revision"] == session.revision),
            "constraints": constraints(document),
            "timing_source": "proposed",
        }
