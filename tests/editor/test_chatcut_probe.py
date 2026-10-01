from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from takeone.editor import chatcut_probe
from takeone.editor.chatcut_probe import ProbeError, main, probe

PROJECT_ID = "project-1"
TIMELINE_ID = "timeline-1"
HERE = Path(__file__).resolve().parent
PEER = HERE / "chatcut_peer.py"


class ChatCutProbeTests(unittest.TestCase):
    def command(self, scenario: str = "success") -> list[str]:
        return [sys.executable, str(PEER), scenario]

    def test_reads_every_tool_page_timeline_page_and_actual_item(self) -> None:
        report = probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=2)

        self.assertEqual(1, report["schema_version"])
        self.assertEqual(PROJECT_ID, report["project_id"])
        self.assertEqual(TIMELINE_ID, report["timeline_id"])
        self.assertEqual("chatcut-fixture", report["server_info"]["name"])
        self.assertEqual(5, len(report["tools"]))
        self.assertEqual(3, len(report["snapshot"]["timeline"]["entries"]))
        self.assertEqual(2, len(report["snapshot"]["items"]))
        self.assertIn(
            "transition-out",
            report["snapshot"]["items"][0]["inspection"]["content"][0]["text"],
        )
        self.assertTrue(all("inputSchema" in tool for tool in report["tools"]))
        self.assertEqual(64, len(report["fingerprint"]))
        self.assertEqual({"mode": "read-only", "production_ready": False}, report["qualification"])

    def test_identical_state_has_identical_fingerprint(self) -> None:
        first = probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=2)
        second = probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=2)
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_audio_gain_change_changes_fingerprint(self) -> None:
        first = probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=2)
        changed = probe(self.command("changed_gain"), PROJECT_ID, TIMELINE_ID, timeout_s=2)
        self.assertNotEqual(first["fingerprint"], changed["fingerprint"])

    def test_attached_transition_change_changes_fingerprint(self) -> None:
        first = probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=2)
        changed = probe(self.command("changed_transition"), PROJECT_ID, TIMELINE_ID, timeout_s=2)
        self.assertNotEqual(first["fingerprint"], changed["fingerprint"])

    def test_rejects_wrong_project_before_any_targeted_read(self) -> None:
        with self.assertRaisesRegex(ProbeError, "project"):
            probe(self.command("wrong_project"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_wrong_timeline(self) -> None:
        with self.assertRaisesRegex(ProbeError, "timeline"):
            probe(self.command("wrong_timeline"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_requires_exactly_one_visible_timeline(self) -> None:
        with self.assertRaisesRegex(ProbeError, "exactly one visible timeline"):
            probe(self.command("multiple_timelines"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_tool_error_without_provider_text(self) -> None:
        with self.assertRaises(ProbeError) as caught:
            probe(self.command("tool_error"), PROJECT_ID, TIMELINE_ID, timeout_s=2)
        self.assertNotIn("do-not-leak", str(caught.exception))

    def test_rejects_missing_project_structured_data(self) -> None:
        with self.assertRaisesRegex(ProbeError, "structured"):
            probe(self.command("missing_project_structured"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_missing_structured_timeline_snapshot(self) -> None:
        with self.assertRaisesRegex(ProbeError, "structured"):
            probe(self.command("missing_snapshot"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_repeated_tool_cursor(self) -> None:
        with self.assertRaisesRegex(ProbeError, "cursor"):
            probe(self.command("tool_cursor_loop"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_cumulative_pagination_beyond_the_page_limit(self) -> None:
        with mock.patch.object(chatcut_probe, "MAX_PROBE_PAGES", 2):
            with self.assertRaisesRegex(ProbeError, "page limit"):
                probe(self.command("unbounded_tool_pages"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_cumulative_items_across_the_consistency_scan(self) -> None:
        with mock.patch.object(chatcut_probe, "MAX_PROBE_ITEMS", 14):
            with self.assertRaisesRegex(ProbeError, "item limit"):
                probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_cumulative_response_bytes(self) -> None:
        with mock.patch.object(chatcut_probe, "MAX_PROBE_BYTES", 1_000):
            with self.assertRaisesRegex(ProbeError, "data limit"):
                probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_duplicate_tool_name(self) -> None:
        with self.assertRaisesRegex(ProbeError, "duplicate"):
            probe(self.command("duplicate_tool"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_an_initialize_protocol_mismatch(self) -> None:
        with self.assertRaisesRegex(ProbeError, "protocol"):
            probe(self.command("wrong_protocol"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_missing_required_tool(self) -> None:
        with self.assertRaisesRegex(ProbeError, "required"):
            probe(self.command("missing_tool"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_repeated_timeline_offset(self) -> None:
        with self.assertRaisesRegex(ProbeError, "offset"):
            probe(self.command("pagination_loop"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_timeline_total_change_between_pages(self) -> None:
        with self.assertRaisesRegex(ProbeError, "changed"):
            probe(self.command("total_changes"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_timeline_state_change_between_pages(self) -> None:
        with self.assertRaisesRegex(ProbeError, "changed"):
            probe(self.command("page_state_changes"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rechecks_identity_after_scan(self) -> None:
        with self.assertRaisesRegex(ProbeError, "changed"):
            probe(self.command("changes_during_scan"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rechecks_timeline_after_scan(self) -> None:
        with self.assertRaisesRegex(ProbeError, "changed"):
            probe(self.command("timeline_changes_during_scan"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rechecks_item_details_after_scan(self) -> None:
        with self.assertRaisesRegex(ProbeError, "changed"):
            probe(self.command("item_changes_during_scan"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_timeout_eof_and_malformed_json_are_sanitized(self) -> None:
        for scenario in ("timeout", "eof", "malformed"):
            with self.subTest(scenario=scenario), self.assertRaises(ProbeError) as caught:
                probe(self.command(scenario), PROJECT_ID, TIMELINE_ID, timeout_s=0.1)
            self.assertNotIn("do-not-leak", str(caught.exception))

    def test_excessively_nested_subprocess_response_is_sanitized(self) -> None:
        with self.assertRaisesRegex(ProbeError, "malformed JSON"):
            probe(self.command("excessive_nesting"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_excessively_nested_snapshot_cannot_escape_canonicalization(self) -> None:
        nested: object = 0
        for _ in range(20_000):
            nested = [nested]
        with self.assertRaisesRegex(ProbeError, "snapshot"):
            chatcut_probe._canonical(nested)

    def test_excessively_nested_report_cannot_escape_final_serialization(self) -> None:
        nested: object = 0
        for _ in range(20_000):
            nested = [nested]
        with self.assertRaisesRegex(ProbeError, "serialize"):
            chatcut_probe._render_report({"server_info": nested})

    def test_rendered_report_must_fit_the_prior_report_limit(self) -> None:
        report = probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=2)
        with mock.patch.object(chatcut_probe, "MAX_PRIOR_REPORT_BYTES", 100):
            with self.assertRaisesRegex(ProbeError, "size limit"):
                chatcut_probe._render_report(report)

    def test_rejects_malformed_json_rpc_envelopes(self) -> None:
        for scenario in ("missing_jsonrpc", "result_and_error", "malformed_notification"):
            with self.subTest(scenario=scenario), self.assertRaisesRegex(ProbeError, "invalid"):
                probe(self.command(scenario), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_rejects_notification_flood_without_an_unbounded_backlog(self) -> None:
        with self.assertRaisesRegex(ProbeError, "notifications|backlog"):
            probe(self.command("notification_flood"), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_blocked_request_write_obeys_the_probe_timeout(self) -> None:
        started = time.monotonic()
        with self.assertRaisesRegex(ProbeError, "timed out"):
            probe(self.command("non_reading"), PROJECT_ID, TIMELINE_ID, timeout_s=0.1)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_close_stops_a_writer_that_has_not_consumed_its_queued_request(self) -> None:
        original = chatcut_probe._Connection._write_stdin
        writers: list[threading.Thread] = []

        def delayed_writer(connection: chatcut_probe._Connection) -> None:
            writers.append(threading.current_thread())
            time.sleep(0.15)
            original(connection)

        with mock.patch.object(chatcut_probe._Connection, "_write_stdin", delayed_writer):
            with self.assertRaisesRegex(ProbeError, "timed out"):
                probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=0.05)

        self.assertEqual(1, len(writers))
        writers[0].join(timeout=0.5)
        self.assertFalse(writers[0].is_alive())

    def test_large_request_is_written_completely_within_the_timeout(self) -> None:
        report = probe(self.command("large_request"), PROJECT_ID, TIMELINE_ID, timeout_s=3)
        self.assertEqual(5, len(report["tools"]))

    def test_item_inspection_requires_nonempty_observed_text(self) -> None:
        for scenario in (
            "missing_inspection_content",
            "empty_inspection_content",
            "malformed_inspection_content",
        ):
            with self.subTest(scenario=scenario), self.assertRaisesRegex(ProbeError, "readable"):
                probe(self.command(scenario), PROJECT_ID, TIMELINE_ID, timeout_s=2)

    def test_requires_finite_positive_timeout(self) -> None:
        for timeout in (0, -1, float("nan"), float("inf"), -float("inf")):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ProbeError, "timeout"):
                probe(self.command(), PROJECT_ID, TIMELINE_ID, timeout_s=timeout)


class ChatCutProbeCliTests(unittest.TestCase):
    def argv(self, scenario: str = "success", *prefix: str) -> list[str]:
        return [
            "--project-id",
            PROJECT_ID,
            "--timeline-id",
            TIMELINE_ID,
            "--timeout-s",
            "2",
            *prefix,
            "--server",
            sys.executable,
            str(PEER),
            scenario,
        ]

    def run_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_success_writes_explicit_read_only_report(self) -> None:
        code, stdout, stderr = self.run_main(self.argv())
        report = json.loads(stdout)
        self.assertEqual(0, code)
        self.assertEqual("read-only", report["qualification"]["mode"])
        self.assertFalse(report["qualification"]["production_ready"])
        self.assertEqual("", stderr)

    def test_cli_compare_accepts_same_state_and_rejects_changed_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior = Path(directory) / "prior.json"
            prior.write_text(
                json.dumps(probe([sys.executable, str(PEER), "success"], PROJECT_ID, TIMELINE_ID, 2)),
                encoding="utf-8",
            )
            same, _, _ = self.run_main(self.argv("success", "--compare", str(prior)))
            changed, stdout, stderr = self.run_main(self.argv("changed_gain", "--compare", str(prior)))
        self.assertEqual(0, same)
        self.assertNotEqual(0, changed)
        self.assertEqual("", stdout)
        self.assertIn("changed", stderr.lower())

    def test_cli_rejects_wrong_target_and_invalid_prior_report(self) -> None:
        wrong, stdout, stderr = self.run_main(self.argv("wrong_project"))
        self.assertNotEqual(0, wrong)
        self.assertEqual("", stdout)
        self.assertIn("project", stderr.lower())

        with tempfile.TemporaryDirectory() as directory:
            prior = Path(directory) / "bad.json"
            prior.write_text('{"schema_version": 1}', encoding="utf-8")
            invalid, stdout, stderr = self.run_main(self.argv("success", "--compare", str(prior)))
        self.assertNotEqual(0, invalid)
        self.assertEqual("", stdout)
        self.assertIn("prior report", stderr.lower())

    def test_cli_rejects_a_prior_report_whose_snapshot_does_not_match_its_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior = Path(directory) / "corrupt.json"
            report = probe([sys.executable, str(PEER), "success"], PROJECT_ID, TIMELINE_ID, 2)
            report["snapshot"]["items"] = []
            prior.write_text(json.dumps(report), encoding="utf-8")
            code, stdout, stderr = self.run_main(self.argv("success", "--compare", str(prior)))
        self.assertNotEqual(0, code)
        self.assertEqual("", stdout)
        self.assertIn("prior report", stderr.lower())

    def test_cli_rejects_valid_prior_report_for_another_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior = Path(directory) / "other-target.json"
            report = probe([sys.executable, str(PEER), "success"], PROJECT_ID, TIMELINE_ID, 2)
            report["project_id"] = "project-other"
            report["snapshot"]["active_project"]["projectId"] = "project-other"
            report["snapshot"]["project"]["project"]["id"] = "project-other"
            canonical = json.dumps(
                report["snapshot"],
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            report["fingerprint"] = hashlib.sha256(canonical).hexdigest()
            prior.write_text(json.dumps(report), encoding="utf-8")
            code, stdout, stderr = self.run_main(self.argv("success", "--compare", str(prior)))
        self.assertNotEqual(0, code)
        self.assertEqual("", stdout)
        self.assertIn("different project or timeline", stderr.lower())

    def test_cli_rejects_oversized_prior_report_before_json_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior = Path(directory) / "oversized.json"
            prior.write_bytes(b"{" + b" " * 9_000_000 + b"}")
            code, stdout, stderr = self.run_main(self.argv("success", "--compare", str(prior)))
        self.assertNotEqual(0, code)
        self.assertEqual("", stdout)
        self.assertIn("size limit", stderr.lower())

    def test_cli_sanitizes_excessively_nested_prior_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior = Path(directory) / "nested.json"
            prior.write_text("[" * 20_000 + "0" + "]" * 20_000, encoding="utf-8")
            code, stdout, stderr = self.run_main(self.argv("success", "--compare", str(prior)))
        self.assertNotEqual(0, code)
        self.assertEqual("", stdout)
        self.assertIn("prior report is invalid", stderr.lower())
        self.assertNotIn("Traceback", stderr)

    def test_cli_sanitizes_finite_number_overflow_in_server_metadata(self) -> None:
        code, stdout, stderr = self.run_main(self.argv("finite_number_overflow"))
        self.assertNotEqual(0, code)
        self.assertEqual("", stdout)
        self.assertNotIn("Traceback", stderr)
        self.assertIn("malformed JSON", stderr)

    def test_cli_sanitizes_provider_tool_errors(self) -> None:
        code, stdout, stderr = self.run_main(self.argv("tool_error"))
        self.assertNotEqual(0, code)
        self.assertEqual("", stdout)
        self.assertNotIn("do-not-leak", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_cli_rejects_non_finite_timeout_without_traceback(self) -> None:
        for value in ("0", "nan", "inf", "-inf"):
            argv = self.argv()
            argv[argv.index("2")] = value
            code, stdout, stderr = self.run_main(argv)
            with self.subTest(value=value):
                self.assertNotEqual(0, code)
                self.assertEqual("", stdout)
                self.assertNotIn("Traceback", stderr)

    def test_cli_refuses_existing_output_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            output.write_text("sentinel", encoding="utf-8")
            code, stdout, stderr = self.run_main(self.argv("success", "--output", str(output)))
            self.assertEqual("sentinel", output.read_text(encoding="utf-8"))
        self.assertNotEqual(0, code)
        self.assertEqual("", stdout)
        self.assertIn("exists", stderr.lower())

    def test_cli_creates_new_output_exclusively(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            code, stdout, stderr = self.run_main(self.argv("success", "--output", str(output)))
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(0, code)
        self.assertEqual("", stdout)
        self.assertEqual("", stderr)
        self.assertEqual(1, report["schema_version"])


if __name__ == "__main__":
    unittest.main()
