"""Provider provenance belongs to the instructions actually sent, never later files."""

import io
import json
import unittest
from unittest.mock import patch

from takeone.director.creative import digest
from takeone.director.provider import ResponsesPlanner


class InstructionSnapshotTests(unittest.TestCase):
    def test_request_snapshot_survives_a_skill_change_while_response_is_in_flight(self):
        planner = ResponsesPlanner(api_key="unit-test-placeholder")
        response = dict(
            model=planner.config["model"],
            id="response-test",
            status="completed",
            output=[dict(type="message", content=[dict(type="output_text", text="{}")])],
            usage=dict(input_tokens=1, output_tokens=1),
        )
        stream = io.BytesIO(json.dumps(response).encode())
        sent = []

        class Connection:
            sock = None
            status = 200

            def request(self, method, path, raw, headers):
                sent.append(json.loads(raw))

            def getresponse(self):
                return self

            def read1(self, size):
                return stream.read(size)

            def close(self):
                pass

        with patch("takeone.director.provider.skill_text", side_effect=["before-request", "after-request"]):
            with patch("takeone.director.provider.http.client.HTTPSConnection", return_value=Connection()):
                result = planner.generate({}, "creative_plan")
        self.assertIn("before-request", sent[0]["instructions"])
        self.assertNotIn("after-request", sent[0]["instructions"])
        self.assertEqual(result.provenance["filming_skill_digest"], digest("before-request"))
        self.assertEqual(result.provenance["request_instructions_digest"], digest(sent[0]["instructions"]))
        self.assertEqual(result.provenance["instructions_source"], "request_time_snapshot")

    def test_local_request_uses_current_skill_text_without_transmitting(self):
        from takeone.director.studio import skill_text

        planner = ResponsesPlanner(api_key="")
        body, reserved = planner.request({}, "creative_plan")
        self.assertIn(skill_text(), json.loads(body)["instructions"])
        self.assertGreater(reserved, 0)
        self.assertFalse(planner.status()["available"])
