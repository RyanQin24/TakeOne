"""Takes remember the compiled plan that produced them; verdicts append per prompt version."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from takeone.recording.repository import SCHEMA, RecordingRepository

V1_SCHEMA = (
    SCHEMA.replace(",\n    plan_id TEXT", "")
    .replace("CREATE INDEX recording_takes_plan ON recording_takes(plan_id);\n", "")
    .replace("PRAGMA user_version=2;", "PRAGMA user_version=1;")
)
V1_SCHEMA = (
    V1_SCHEMA[: V1_SCHEMA.index("CREATE TABLE take_verdicts")]
    + V1_SCHEMA[V1_SCHEMA.index("CREATE INDEX recording_takes_state") :]
)
PLAN_ID = "ab" * 32


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "takes.sqlite3"

    def test_version_1_database_gains_plan_column_and_verdicts(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(V1_SCHEMA)
            connection.execute(
                "INSERT INTO recording_takes(take_id,state,scenario,start_request_id,context,zoom,"
                "created_ns,start_request_ns) VALUES ('t1','ready','normal','r1','{}','{}','0','0')"
            )
        repository = RecordingRepository(self.path)
        with repository.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            row = repository.row(connection, "t1")
            self.assertIsNone(row["plan_id"])
            self.assertEqual(repository.snapshot(connection, row)["plan_id"], None)
            self.assertEqual(repository.verdicts(connection, "t1"), [])

    def test_fresh_database_and_existing_v2_both_open(self):
        RecordingRepository(self.path)
        repository = RecordingRepository(self.path)
        with repository.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_unrelated_database_still_refused(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE surprises (x)")
        with self.assertRaises(ValueError):
            RecordingRepository(self.path)

    def test_verdicts_replace_within_a_prompt_version_and_append_across(self):
        repository = RecordingRepository(self.path)
        with repository.transaction() as connection:
            connection.execute(
                "INSERT INTO recording_takes(take_id,state,scenario,start_request_id,context,zoom,"
                "created_ns,start_request_ns,plan_id) VALUES ('t1','ready','normal','r1','{}','{}','0','0',?)",
                (PLAN_ID,),
            )
            repository.record_verdict(connection, "t1", 1, 0.4, {"focus": 0.4}, "soft focus", "probe", 10)
            repository.record_verdict(connection, "t1", 1, 0.5, {"focus": 0.5}, "recomputed", "probe", 11)
            repository.record_verdict(connection, "t1", 2, 0.9, {"focus": 0.9}, "sharp", "probe", 12)
        with repository.connect() as connection:
            verdicts = repository.verdicts(connection, "t1")
        self.assertEqual([(v["prompt_version"], v["score"]) for v in verdicts], [(1, 0.5), (2, 0.9)])
        self.assertEqual(verdicts[0]["signals"], {"focus": 0.5})

    def test_migration_matches_fresh_schema(self):
        # A database migrated 1→2 and a fresh v2 database must agree on columns.
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(V1_SCHEMA)
        RecordingRepository(self.path)
        fresh_path = Path(self.folder.name) / "fresh.sqlite3"
        RecordingRepository(fresh_path)
        columns = {}
        for name, path in (("migrated", self.path), ("fresh", fresh_path)):
            with closing(sqlite3.connect(path)) as connection:
                columns[name] = {
                    table: [c[1] for c in connection.execute(f"PRAGMA table_info({table})")]
                    for table in ("recording_takes", "take_verdicts")
                }
        self.assertEqual(
            set(columns["migrated"]["recording_takes"]), set(columns["fresh"]["recording_takes"])
        )
        self.assertEqual(columns["migrated"]["take_verdicts"], columns["fresh"]["take_verdicts"])


if __name__ == "__main__":
    unittest.main()
