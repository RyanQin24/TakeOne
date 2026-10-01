"""Local project storage. One transaction holds the operation, the new state and the event.

Follows the Director's storage discipline: an explicit schema, `PRAGMA user_version`
migrations, and a refusal to initialise a database that belongs to something else.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .contracts import encode
from .errors import EditorError

SCHEMA = """
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY, title TEXT NOT NULL, version INTEGER NOT NULL,
    document TEXT NOT NULL, created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL
);
CREATE TABLE operations (
    project_id TEXT NOT NULL REFERENCES projects(project_id), sequence INTEGER NOT NULL,
    operation_id TEXT NOT NULL UNIQUE, document TEXT NOT NULL, patch TEXT NOT NULL,
    PRIMARY KEY(project_id, sequence)
);
CREATE TABLE events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(project_id),
    kind TEXT NOT NULL, detail TEXT NOT NULL, created_utc TEXT NOT NULL
);
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
    kind TEXT NOT NULL, status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '{}',
    created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL
);
CREATE TABLE artifacts (
    node_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id),
    kind TEXT NOT NULL, path TEXT NOT NULL, bytes INTEGER NOT NULL,
    duration_s REAL NOT NULL, created_utc TEXT NOT NULL
);
CREATE INDEX events_project ON events(project_id, sequence);
CREATE INDEX jobs_project ON jobs(project_id, status);
PRAGMA user_version = 1;
"""

SUPPORTED_VERSION = 1


class ProjectRepository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                if tables:
                    raise EditorError("Refusing to initialise an unrelated database")
                connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
            elif version != SUPPORTED_VERSION:
                raise EditorError(f"Unsupported editor database schema {version}")
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

    # -- projects ----------------------------------------------------------

    def create(self, project, now_utc):
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO projects VALUES (?,?,?,?,?,?)",
                (
                    project.project_id,
                    project.title,
                    project.state.version,
                    encode(project.state.wire()),
                    now_utc,
                    now_utc,
                ),
            )
            connection.execute(
                "INSERT INTO events(project_id, kind, detail, created_utc) VALUES (?,?,?,?)",
                (project.project_id, "project_created", encode({"title": project.title}), now_utc),
            )
        return project

    def exists(self, project_id):
        with self.connect() as connection:
            row = connection.execute("SELECT 1 FROM projects WHERE project_id=?", (project_id,)).fetchone()
        return row is not None

    def list_projects(self, limit=100):
        with self.connect() as connection:
            return [
                {
                    "project_id": row["project_id"],
                    "title": row["title"],
                    "version": row["version"],
                    "created_utc": row["created_utc"],
                    "updated_utc": row["updated_utc"],
                }
                for row in connection.execute(
                    "SELECT * FROM projects ORDER BY updated_utc DESC LIMIT ?", (limit,)
                )
            ]

    def snapshot(self, project_id):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown project '{project_id}'")
        return {
            "project_id": row["project_id"],
            "title": row["title"],
            "version": row["version"],
            "state": json.loads(row["document"]),
            "created_utc": row["created_utc"],
            "updated_utc": row["updated_utc"],
        }

    def operations(self, project_id, since=0, limit=10000):
        with self.connect() as connection:
            return [
                {
                    "sequence": row["sequence"],
                    "operation": json.loads(row["document"]),
                    "patch": json.loads(row["patch"]),
                }
                for row in connection.execute(
                    "SELECT * FROM operations WHERE project_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                    (project_id, since, limit),
                )
            ]

    def append(self, project_id, operation, patch, state, now_utc):
        """The operation, its patch and the resulting state commit together or not at all."""
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence),0) AS last FROM operations WHERE project_id=?",
                (project_id,),
            ).fetchone()
            sequence = row["last"] + 1
            stamped = operation.executed(sequence, now_utc)
            connection.execute(
                "INSERT INTO operations VALUES (?,?,?,?,?)",
                (
                    project_id,
                    sequence,
                    stamped.operation_id,
                    encode(stamped.wire()),
                    encode(patch),
                ),
            )
            updated = connection.execute(
                "UPDATE projects SET version=?, document=?, updated_utc=? WHERE project_id=?",
                (state.version, encode(state.wire()), now_utc, project_id),
            )
            if updated.rowcount != 1:
                raise KeyError(f"Unknown project '{project_id}'")
            connection.execute(
                "INSERT INTO events(project_id, kind, detail, created_utc) VALUES (?,?,?,?)",
                (
                    project_id,
                    "operation_applied",
                    encode({"type": str(stamped.type), "sequence": sequence}),
                    now_utc,
                ),
            )
        return stamped, sequence

    def truncate(self, project_id, keep_sequence, state, now_utc):
        """Undo. Removing the tail of the log is the whole mechanism."""
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM operations WHERE project_id=? AND sequence>?",
                (project_id, keep_sequence),
            )
            connection.execute(
                "UPDATE projects SET version=?, document=?, updated_utc=? WHERE project_id=?",
                (state.version, encode(state.wire()), now_utc, project_id),
            )
            connection.execute(
                "INSERT INTO events(project_id, kind, detail, created_utc) VALUES (?,?,?,?)",
                (project_id, "operations_truncated", encode({"kept": keep_sequence}), now_utc),
            )

    # -- artifacts ---------------------------------------------------------

    def record_artifact(self, project_id, node_id, kind, path, size, duration_s, now_utc):
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO artifacts VALUES (?,?,?,?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET "
                "path=excluded.path, bytes=excluded.bytes, duration_s=excluded.duration_s",
                (node_id, project_id, kind, str(path), int(size), float(duration_s), now_utc),
            )

    def artifacts(self, project_id, limit=200):
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM artifacts WHERE project_id=? ORDER BY created_utc DESC LIMIT ?",
                    (project_id, limit),
                )
            ]

    def events(self, project_id, limit=200):
        with self.connect() as connection:
            return [
                {**dict(row), "detail": json.loads(row["detail"])}
                for row in connection.execute(
                    "SELECT * FROM events WHERE project_id=? ORDER BY sequence DESC LIMIT ?",
                    (project_id, limit),
                )
            ]
