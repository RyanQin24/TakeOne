"""The orbit API serves the local editor and rejects malformed settings."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests.test_director_http import server_module


class OrbitHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.server = server_module.make_server(0, Path(cls.folder.name) / "sessions.sqlite3", {}, {})
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.folder.cleanup()

    def request(self, path, data=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = Request(self.base + path, data=data, headers=headers)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read().decode()

    def test_editor_defaults_compile_and_roundtrip(self):
        status, content = self.request("/api/previs/orbit")
        self.assertEqual(status, 200)
        defaults = json.loads(content)["defaults"]
        status, content = self.request("/api/previs/orbit", json.dumps(defaults).encode())
        self.assertEqual(status, 200)
        result = json.loads(content)
        self.assertEqual(result["settings"], defaults)
        self.assertEqual(result["kind"], "takeone_orbit_previs")
        self.assertEqual(result["frames"][-1]["time_s"], defaults["duration_s"] + result["orbit_start_s"])
        self.assertEqual(result["frames"][0]["raw_by_role"], result["initial_raw"])

    def test_rejects_nonobjects_invalid_fields_and_foreign_origin(self):
        for data in (b"null", b"[]", b'{"radius_m":NaN}', b'{"duration_s":0}'):
            with self.subTest(data=data):
                self.assertEqual(self.request("/api/previs/orbit", data)[0], 400)
        self.assertEqual(self.request("/api/previs/orbit", b"{}", "https://example.com")[0], 403)

    def test_homepage_and_motor_lab_have_distinct_working_entrypoints(self):
        status, page = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("/orbit.js", page)
        self.assertIn("/motor-test.html", page)
        status, lab = self.request("/motor-test.html")
        self.assertEqual(status, 200)
        self.assertIn("DIRECT MOTOR TEST", lab)


if __name__ == "__main__":
    unittest.main()
