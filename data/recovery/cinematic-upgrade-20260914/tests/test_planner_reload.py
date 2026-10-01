"""Source changes recover preview loading without interrupting a running take."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from takeone import config

from tests.test_director_http import server_module


class ReloadTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.server = server_module.make_server(0, Path(self.folder.name) / "sessions.sqlite3", {}, {})

    def tearDown(self):
        self.server.server_close()
        self.folder.cleanup()

    def test_import_snapshot_detects_an_edit_before_the_watcher_starts(self):
        with patch.object(config, "_PROCESS_INPUTS", {"solver.py": "loaded"}):
            with patch.object(config, "current_process_inputs", return_value={"solver.py": "edited"}):
                self.assertTrue(config.process_inputs_changed())
            with patch.object(config, "current_process_inputs", return_value={"solver.py": "loaded"}):
                self.assertFalse(config.process_inputs_changed())

    def test_compile_finishes_before_reload_can_be_requested(self):
        with self.server.compile_lock:
            self.assertFalse(self.server.request_reload())
            self.assertFalse(self.server.restart_requested.is_set())
        self.assertTrue(self.server.request_reload())

    def test_active_robot_take_defers_reload_until_it_finishes(self):
        with patch.object(self.server.robot, "status", return_value={"active": True}):
            self.assertFalse(self.server.request_reload())
            self.assertFalse(self.server.restart_requested.is_set())
        self.assertTrue(self.server.request_reload())

    def test_changed_sources_request_clean_shutdown_instead_of_exec_in_the_watcher(self):
        with (
            patch.object(server_module, "process_inputs_changed", return_value=True),
            patch.object(self.server, "shutdown") as shutdown,
            patch.object(server_module.os, "execv") as execute,
        ):
            server_module.restart_when_sources_change(self.server, interval_s=0.001)
        self.assertTrue(self.server.restart_requested.is_set())
        shutdown.assert_called_once()
        execute.assert_not_called()

    def test_editing_the_server_itself_also_reloads(self):
        with (
            patch.object(server_module, "process_inputs_changed", return_value=False),
            patch.object(server_module, "file_hash", return_value="edited-server"),
            patch.object(self.server, "shutdown") as shutdown,
        ):
            server_module.restart_when_sources_change(self.server, interval_s=0.001)
        shutdown.assert_called_once()

    def test_closed_server_stops_its_watcher(self):
        self.server.reload_stop.set()
        with patch.object(server_module, "process_inputs_changed") as changed:
            server_module.restart_when_sources_change(self.server, interval_s=0.001)
        changed.assert_not_called()

    def test_robot_start_and_queued_preview_are_rejected_after_reload_is_chosen(self):
        self.assertTrue(self.server.request_reload())
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ("/api/robot/start", "/api/previs/templates"):
                request = Request(
                    f"http://127.0.0.1:{self.server.server_port}{path}",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(HTTPError) as raised:
                    urlopen(request, timeout=5)
                with raised.exception as response:
                    self.assertEqual(response.status, 503)
                    self.assertEqual(json.load(response)["code"], "planner_restarting")
            self.assertIsNone(self.server.robot.process)
        finally:
            self.server.shutdown()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
