"""Offline reviewed-derivative intake, using real media and the editor journal."""

import copy
import errno
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from takeone.editor.api import EditorAPI
from takeone.editor.cli import _editor_http
from takeone.editor.errors import EditorError
from takeone.editor.ids import file_digest
from takeone.editor.library import media_dir
from takeone.editor.operations import OperationType, Target
from takeone.editor.repository import ProjectRepository
from takeone.editor.service import EditorService

from tests.editor.support import op


class ReviewedDerivatives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls.fixtures.name)
        for name, duration, dimensions, color, fps in (
            ("source", 2, "160x90", "blue", 24),
            ("candidate", 1, "320x180", "red", 30),
            ("long", 1.2, "160x90", "red", 24),
            ("square", 1, "90x90", "red", 24),
        ):
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={color}:s={dimensions}:r={fps}:d={duration}",
                    "-c:v",
                    "mpeg4",
                    str(cls.fixture_root / f"{name}.mov"),
                ],
                check=True,
                timeout=20,
                capture_output=True,
            )
        for suffix, codec in (
            ("mp4", "copy"),
            ("mkv", "copy"),
            ("avi", "mpeg4"),
            ("webm", "libvpx-vp9"),
            ("mpg", "mpeg2video"),
        ):
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(cls.fixture_root / "candidate.mov"),
                    "-c:v",
                    codec,
                    str(cls.fixture_root / f"container.{suffix}"),
                ],
                check=True,
                timeout=20,
                capture_output=True,
            )

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.allowed = self.root / "allowed"
        self.allowed.mkdir()
        for source in self.fixture_root.iterdir():
            shutil.copyfile(source, self.allowed / source.name)
        self.original = self.allowed / "source.mov"
        self.candidate = self.allowed / "candidate.mov"
        self.workspace = self.root / "editor"
        self.reopen()
        self.api.create({"project_id": "demo", "title": "Offline augmentation"})
        imported = self.api.import_media("demo", {"path": str(self.original), "build_proxy": False})
        self.source_id = imported["media_id"]
        self.original_digest = file_digest(self.original)
        # These values describe an offline stand-in, not a successful cloud job.
        self.body = {
            "path": str(self.candidate),
            "name": "Reviewed offline stand-in",
            "source_media_id": self.source_id,
            "source_sha256": self.original_digest,
            "source_start_s": 0.5,
            "source_end_s": 1.5,
            "output_source_space": "rec709",
            "provider": "offline-test",
            "model": "no-generation-performed",
            "model_version": "provider-not-reported",
            "job_id": "offline-fixture-not-cloud",
            "prompt": "Add floating ingredients while preserving the source.",
            "settings": {"taskMode": "edit", "resolution": "720p", "outputFormat": "mov"},
            "cost": {"amount": None, "unit": "credits", "status": "unknown"},
            "rights_evidence": "Locally generated color fixture; no private footage",
            "review": {
                "reviewer": "test-operator",
                "decision": "approved",
                "notes": "Offline intake fixture only, not visual preservation evidence",
                "preserved": dict.fromkeys(
                    ("people", "action", "camera_motion", "geometry", "text_logos"), True
                ),
                "audio": "silent_source",
            },
        }

    def reopen(self):
        self.service = EditorService(ProjectRepository(self.workspace / "projects.sqlite3"))
        self.api = EditorAPI(self.service, self.workspace, [self.allowed])

    def post(self, body=None):
        try:
            return self.api.post("/api/editor/projects/demo/vfx/derivatives", body or self.body)
        except KeyError as error:
            self.fail(f"Reviewed derivative endpoint unavailable: {error}")

    def assert_rejected(self, body):
        before = self.service.state("demo").wire()
        files = {str(path): file_digest(path) for path in media_dir(self.workspace, "demo").iterdir()}
        history = self.service.history("demo")
        with self.assertRaises(EditorError):
            self.post(body)
        self.assertEqual(self.service.state("demo").wire(), before)
        self.assertEqual(self.service.history("demo"), history)
        self.assertEqual(
            {str(path): file_digest(path) for path in media_dir(self.workspace, "demo").iterdir()}, files
        )

    def test_import_persists_verified_copy_lineage_without_placing_or_proxy(self):
        # Missing copy, metadata or accidental placement each break this consumer contract.
        result = self.post()
        self.assertTrue(result["ok"])
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "reviewed_derivative")
        self.assertFalse(result["placed"])
        self.assertFalse(result["reused"])
        self.assertEqual(len(self.service.state("demo").timeline.tracks), 0)
        self.assertEqual(file_digest(self.original), self.original_digest)
        media = self.service.state("demo").media[result["media_id"]]
        self.assertTrue(Path(media.path).is_relative_to(media_dir(self.workspace, "demo")))
        self.assertNotEqual(Path(media.path), self.candidate)
        self.assertEqual(file_digest(media.path), file_digest(self.candidate))
        self.assertIsNone(media.proxy_path)
        lineage = result["lineage"]
        self.assertEqual(lineage["output_sha256"], file_digest(self.candidate))
        self.assertEqual(lineage["source_sha256"], self.original_digest)
        self.assertEqual(lineage["cost"], {"amount": None, "unit": "credits", "status": "unknown"})
        self.assertEqual(lineage["output_probe"]["width"], 320)
        self.assertEqual(lineage["output_probe"]["fps_num"], 30)
        self.assertEqual(self.service.history("demo")[-1]["operation"]["metadata"]["vfx_lineage"], lineage)
        self.candidate.unlink()
        self.assertEqual(file_digest(media.path), lineage["output_sha256"])

    def test_duplicate_survives_reload_without_second_operation(self):
        first = self.post()
        self.reopen()
        second = self.post()
        self.assertTrue(second["reused"])
        self.assertEqual(second["media_id"], first["media_id"])
        self.assertEqual(second["lineage"], first["lineage"])
        self.assertEqual(len(self.service.history("demo")), 2)
        self.assertEqual(len(list(media_dir(self.workspace, "demo").iterdir())), 1)

    def test_ordinary_duplicate_upload_removes_only_its_unregistered_copy(self):
        before = self.service.state("demo").wire()
        results = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: self.api.receive_upload(
                        "demo", "duplicate-source.mov", self.original, place=False
                    ),
                    range(2),
                )
            )
        self.assertTrue(all(result["reused"] for result in results))
        self.assertEqual(self.service.state("demo").wire(), before)
        self.assertEqual(list(media_dir(self.workspace, "demo").iterdir()), [])
        self.assertEqual(file_digest(self.original), self.original_digest)

    def test_ordinary_upload_retains_a_committed_copy_after_publish_failure(self):
        with patch.object(self.service, "_publish", side_effect=RuntimeError("publish failed")):
            with self.assertRaisesRegex(RuntimeError, "publish failed"):
                self.api.receive_upload("demo", "committed-candidate.mov", self.candidate, place=False)
        registered = next(
            item
            for item in self.service.state("demo").media.values()
            if item.sha256 == file_digest(self.candidate)
        )
        self.assertTrue(Path(registered.path).is_file())
        self.assertTrue(Path(registered.path).is_relative_to(media_dir(self.workspace, "demo")))

    def _audible_body(self):
        source = self.allowed / "audible-source.mp4"
        candidate = self.allowed / "audible-candidate.mp4"
        for path, duration, color in ((source, 2, "blue"), (candidate, 1, "red")):
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-n",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={color}:s=160x90:r=30:d={duration}",
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency=440:sample_rate=48000:duration={duration}",
                    "-c:v",
                    "mpeg4",
                    "-c:a",
                    "aac",
                    str(path),
                ],
                check=True,
                timeout=20,
                capture_output=True,
            )
        source_id = self.api.import_media("demo", {"path": str(source), "build_proxy": False})["media_id"]
        body = copy.deepcopy(self.body)
        body.update(path=str(candidate), source_media_id=source_id, source_sha256=file_digest(source))
        body["review"]["audio"] = "reviewed"
        return body

    def test_reviewed_derivative_can_supply_a_verified_audio_selection(self):
        body = self._audible_body()
        result = self.post(body)
        try:
            self.service.submit(
                "demo",
                op(
                    OperationType.ADD_MUSIC,
                    Target.project(),
                    event_id="derived-audio",
                    asset_id=result["media_id"],
                    timeline_start_s=0.0,
                    source_start_s=0.0,
                    duration_s=1.0,
                ),
            )
        except EditorError as error:
            self.fail(f"Verified derivative audio selection rejected: {error}")
        before = self.service.state("demo").wire()
        self.assertAlmostEqual(result["lineage"]["output_probe"]["audio_duration_s"], 1.0)
        self.reopen()
        self.assertEqual(self.service.state("demo").wire(), before)
        self.assertEqual(self.service.replay("demo")[0].wire(), before)

    def test_retry_preserves_a_legacy_derivative_receipt_without_audio_timing(self):
        with patch("takeone.editor.analysis.probe._audio_timing", return_value={}):
            with patch("takeone.editor.vfx._audio_timing", return_value={}):
                body = self._audible_body()
                first = self.post(body)
        self.assertNotIn("audio_duration_s", first["lineage"]["output_probe"])
        before = self.service.state("demo").wire()
        self.reopen()
        try:
            repeat = self.post(body)
        except EditorError as error:
            self.fail(f"Unchanged legacy derivative retry rejected: {error}")
        self.assertTrue(repeat["reused"])
        self.assertEqual(repeat["lineage"], first["lineage"])
        self.assertEqual(self.service.state("demo").wire(), before)
        self.assertEqual(len(self.service.history("demo")), 3)

    def test_simultaneous_duplicates_create_one_operation(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.post(), range(2)))
        self.assertEqual(sorted(result["reused"] for result in results), [False, True])
        self.assertEqual(len(self.service.history("demo")), 2)

    def test_long_journal_retry_reload_replay_undo_and_http_pages(self):
        # Truncating internal reads at the HTTP page cap loses provenance and replay state.
        for _ in range(10000):
            self.service.submit("demo", op(OperationType.SET_PHASE, Target.project(), phase="understand"))
        first = self.post()
        self.assertEqual(self.service.state("demo").version, 10002)
        first_page = self.api.get("/api/editor/projects/demo/operations")["operations"]
        self.assertEqual(len(first_page), 10000)
        self.assertEqual(first_page[-1]["sequence"], 10000)
        tail = self.api.get("/api/editor/projects/demo/operations", {"since": ["10000"]})["operations"]
        self.assertEqual([entry["sequence"] for entry in tail], [10001, 10002])
        with self.subTest(contract="retry after capped HTTP page"):
            self.assertTrue(self.post()["reused"])
            self.assertEqual(self.service.state("demo").version, 10002)
        with self.subTest(contract="reload complete log"):
            self.reopen()
            self.assertEqual(self.service.state("demo").version, 10002)
            retried = self.post()
            self.assertTrue(retried["reused"])
            self.assertEqual(retried["media_id"], first["media_id"])
        with self.subTest(contract="replay complete log"):
            replayed, operations, _ = self.service.replay("demo")
            self.assertEqual(replayed.version, 10002)
            self.assertEqual(len(operations), 10002)
        with self.subTest(contract="undo final operation only"):
            self.service.undo("demo")
            self.assertEqual(self.service.state("demo").version, 10001)
            self.assertNotIn(first["media_id"], self.service.state("demo").media)
            self.reopen()
            self.assertEqual(self.service.state("demo").version, 10001)

    def test_long_journal_sse_uses_current_sequence_and_bounded_resume(self):
        # A capped first-page read must not label a current snapshot with an old sequence.
        for _ in range(10000):
            self.service.submit("demo", op(OperationType.SET_PHASE, Target.project(), phase="understand"))
        self.post()
        initial = self.api.backlog("demo", 0)
        self.assertEqual(len(initial), 1)
        self.assertEqual(initial[0]["sequence"], 10002)
        self.assertEqual(initial[0]["patch"][0]["value"]["version"], 10002)
        recent = self.api.backlog("demo", 10000)
        self.assertEqual([event["sequence"] for event in recent], [10001, 10002])
        boundary = self.api.backlog("demo", 9802)
        self.assertEqual(len(boundary), 200)
        self.assertEqual(boundary[0]["sequence"], 9803)
        self.assertEqual(boundary[-1]["sequence"], 10002)
        missed = self.api.backlog("demo", 9801)
        self.assertEqual(len(missed), 1)
        self.assertEqual(missed[0]["sequence"], 10002)
        self.assertEqual(missed[0]["patch"][0]["path"], "")

    def test_long_journal_native_export_rebuilds_complete_consistent_state(self):
        # A full snapshot paired with a truncated export log cannot be loaded/recovered.
        for _ in range(10000):
            self.service.submit("demo", op(OperationType.SET_PHASE, Target.project(), phase="understand"))
        result = self.post()
        exported = self.api.post(
            "/api/editor/projects/demo/export",
            {"format": "takeone", "destination": str(self.workspace / "complete")},
        )
        document = json.loads(Path(exported["path"]).read_text())
        self.assertEqual(len(document["operations"]), 10002)
        self.assertEqual(document["operations"][-1]["metadata"]["vfx_lineage"], result["lineage"])
        from takeone.editor.project import rebuild

        rebuilt = rebuild("demo", document["operations"], document["state"])
        self.assertEqual(rebuilt.version, 10002)
        self.assertEqual(rebuilt.media[result["media_id"]].source_space, "rec709")

    def test_conflicting_provenance_is_rejected(self):
        self.post()
        altered = copy.deepcopy(self.body)
        altered["job_id"] = "different-job"
        self.assert_rejected(altered)

    def test_ordinary_import_cannot_acquire_vfx_provenance(self):
        self.api.import_media("demo", {"path": str(self.candidate), "build_proxy": False})
        self.assert_rejected(self.body)

    def test_strict_review_and_top_level_fields(self):
        changes = [
            ({"decision": "rejected"}, None),
            ({"audio": "not-reviewed"}, None),
            ({"reviewer": " "}, None),
            ({"unknown": True}, None),
        ]
        for change, _ in changes:
            with self.subTest(change=change):
                body = copy.deepcopy(self.body)
                body["review"].update(change)
                self.assert_rejected(body)
        for key in self.body:
            if key == "name":
                continue
            with self.subTest(missing=key):
                body = copy.deepcopy(self.body)
                del body[key]
                self.assert_rejected(body)
        body = {**self.body, "place": True}
        self.assert_rejected(body)

    def test_every_preservation_check_must_be_explicitly_true(self):
        for key in self.body["review"]["preserved"]:
            for value in (False, 1, None, "true"):
                with self.subTest(key=key, value=value):
                    body = copy.deepcopy(self.body)
                    body["review"]["preserved"][key] = value
                    self.assert_rejected(body)
            body = copy.deepcopy(self.body)
            del body["review"]["preserved"][key]
            self.assert_rejected(body)

    def test_ranges_hash_strings_and_settings_fail_closed(self):
        for key, value in (
            ("source_start_s", True),
            ("source_end_s", float("nan")),
            ("source_start_s", -0.1),
            ("source_end_s", 2.1),
            ("source_end_s", 0.5),
            ("source_sha256", "A" * 64),
            ("source_sha256", "a" * 64),
            ("provider", " "),
            ("prompt", "x" * 20001),
            ("settings", {"value": float("inf")}),
            ("settings", {"value": "x" * 20000}),
            ("settings", []),
            ("settings", {"deep": [[[[[[[[[[0]]]]]]]]]]}),
        ):
            with self.subTest(key=key, value=str(value)[:40]):
                self.assert_rejected({**self.body, key: value})

    def test_charge_is_explicit_and_strict(self):
        for charge in (
            {"amount": None, "unit": "credits", "status": "reported"},
            {"amount": True, "unit": "credits", "status": "reported"},
            {"amount": float("nan"), "unit": "credits", "status": "reported"},
            {"amount": -1, "unit": "credits", "status": "reported"},
            {"amount": 6, "unit": "credits", "status": "free"},
            {"amount": 6, "unit": "credits", "status": "reported", "extra": 1},
        ):
            with self.subTest(charge=charge):
                self.assert_rejected({**self.body, "cost": charge})
        body = {**self.body, "cost": {"amount": 6.0, "unit": "credits", "status": "reported"}}
        self.assertEqual(self.post(body)["lineage"]["cost"]["amount"], 6.0)

    def test_rec709_derivative_of_apple_log_preserves_explicit_output_encoding(self):
        # Inheriting capture encoding makes valid generated footage unrenderable or misgraded.
        self.service.undo("demo")
        self.api.import_media(
            "demo", {"path": str(self.original), "build_proxy": False, "source_space": "apple-log"}
        )
        result = self.post()
        current = self.service.state("demo")
        self.assertEqual(current.media[self.source_id].source_space, "apple-log")
        self.assertEqual(file_digest(self.original), self.original_digest)
        self.assertEqual(current.media[result["media_id"]].source_space, "rec709")
        self.assertEqual(result["lineage"]["output_source_space"], "rec709")
        self.reopen()
        self.assertEqual(self.service.state("demo").media[result["media_id"]].source_space, "rec709")
        self.api.place("demo", {"media_id": result["media_id"]})
        from takeone.editor.compile import preview_target, project_graph
        from takeone.editor.render.ffmpeg import compile_graph

        state = self.service.state("demo")
        compiled = compile_graph(project_graph(state, preview_target(state)), self.workspace / "preview.mp4")
        self.assertTrue(compiled.argv)

    def test_output_encoding_is_required_and_validated_before_mutation(self):
        missing = copy.deepcopy(self.body)
        del missing["output_source_space"]
        self.assert_rejected(missing)
        for value in ("unsupported", "", None, True):
            with self.subTest(value=value):
                self.assert_rejected({**self.body, "output_source_space": value})

    def test_modified_source_is_rejected(self):
        self.original.write_bytes(self.original.read_bytes() + b"changed")
        self.assert_rejected(self.body)

    def test_source_change_during_verification_is_rejected(self):
        from takeone.editor import vfx

        real_verify = vfx.verify_video

        def mutate_source(path):
            result = real_verify(path)
            self.original.write_bytes(self.original.read_bytes() + b"modified-during-decode")
            return result

        with patch.object(vfx, "verify_video", side_effect=mutate_source):
            self.assert_rejected(self.body)

    def test_path_escape_symlink_missing_and_identical_source_rejected(self):
        outside = self.root / "outside.mov"
        shutil.copyfile(self.candidate, outside)
        link = self.allowed / "escape.mov"
        link.symlink_to(outside)
        identical = self.allowed / "same.mov"
        shutil.copyfile(self.original, identical)
        for path in (outside, link, self.allowed / "missing.mov", self.original, identical):
            with self.subTest(path=path):
                self.assert_rejected({**self.body, "path": str(path)})

    def test_disguised_relative_manifest_and_outside_symlink_reference_rejected(self):
        # Hashing/copying a manifest cannot attest the video resources FFmpeg follows.
        manifest = self.allowed / "disguised.mov"
        manifest.write_text("ffconcat version 1.0\nfile payload.mov\nduration 1.0\n")
        payload = self.allowed / "payload.mov"
        shutil.copyfile(self.candidate, payload)
        with self.subTest(reference="relative local video"):
            self.assert_rejected({**self.body, "path": str(manifest)})
        outside = self.root / "outside-payload.mov"
        shutil.copyfile(self.candidate, outside)
        payload.unlink()
        payload.symlink_to(outside)
        with self.subTest(reference="symlink outside media roots"):
            self.assert_rejected({**self.body, "path": str(manifest)})

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO observes actual reference opening")
    def test_manifest_rejected_before_opening_outside_root_reference(self):
        # A nonblocking FIFO writer can pair only if FFmpeg has opened the referenced reader.
        external = self.root / "outside-payload.mov"
        os.mkfifo(external)
        (self.allowed / "payload.mov").symlink_to(external)
        self.candidate.write_text("ffconcat version 1.0\nfile payload.mov\nduration 1.0\n")
        opened = threading.Event()
        stopped = threading.Event()

        def observe_reader():
            while not stopped.is_set():
                try:
                    descriptor = os.open(external, os.O_WRONLY | os.O_NONBLOCK)
                except OSError as error:
                    if error.errno != errno.ENXIO:
                        raise
                    stopped.wait(0.005)
                    continue
                opened.set()
                try:
                    os.write(descriptor, b"invalid payload stops an unrestricted probe promptly")
                except BrokenPipeError:
                    pass
                finally:
                    os.close(descriptor)
                return

        observer = threading.Thread(target=observe_reader, daemon=True)
        observer.start()
        try:
            self.assert_rejected(self.body)
        finally:
            stopped.set()
            observer.join(timeout=5)
        self.assertFalse(observer.is_alive())
        self.assertFalse(opened.is_set(), "FFmpeg opened a reference outside allowed roots")

    def test_registered_source_manifest_is_rejected_at_lineage_boundary(self):
        # A previously registered source hash must not represent only a manifest.
        manifest = self.allowed / "source-manifest.mov"
        manifest.write_text("ffconcat version 1.0\nfile payload.mov\nduration 1.0\n")
        external = self.root / "outside-source-payload.mov"
        shutil.copyfile(self.candidate, external)
        (self.allowed / "payload.mov").symlink_to(external)
        imported = self.api.import_media("demo", {"path": str(manifest), "build_proxy": False})
        body = {
            **self.body,
            "source_media_id": imported["media_id"],
            "source_sha256": file_digest(manifest),
            "source_start_s": 0.0,
            "source_end_s": 1.0,
        }
        self.assert_rejected(body)

    def test_self_contained_common_video_containers_remain_importable(self):
        # Whitelist syntax or aliases that break normal installed demuxers fail this test.
        for suffix in ("mp4", "mkv", "avi", "webm", "mpg"):
            with self.subTest(container=suffix):
                result = self.post({**self.body, "path": str(self.allowed / f"container.{suffix}")})
                self.assertEqual(result["status"], "reviewed_derivative")
                media = self.service.state("demo").media[result["media_id"]]
                self.assertEqual(file_digest(media.path), result["lineage"]["output_sha256"])

    def test_source_path_escape_is_checked_before_hashing(self):
        outside = self.root / "outside-source.mov"
        shutil.copyfile(self.original, outside)
        self.service.undo("demo")
        from takeone.editor.analysis.probe import probe

        self.service.submit(
            "demo",
            op(
                OperationType.IMPORT_MEDIA,
                Target.project(),
                media_id=self.source_id,
                name="Source",
                path=str(outside),
                sha256=self.original_digest,
                probe=probe(outside).wire(),
            ),
        )
        self.assert_rejected(self.body)

    def test_wrong_duration_aspect_and_corrupt_media_rejected(self):
        corrupt = self.allowed / "corrupt.mov"
        corrupt.write_bytes(b"not-video")
        truncated = self.allowed / "truncated.mov"
        content = self.candidate.read_bytes()
        # Keep intact metadata and the first packet, but corrupt subsequent frames.
        mdat = content.index(b"mdat")
        mdat_size = int.from_bytes(content[mdat - 4 : mdat], "big")
        packet_end = mdat - 4 + mdat_size
        packets = json.loads(
            subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_packets",
                    "-select_streams",
                    "v",
                    "-of",
                    "json",
                    str(self.candidate),
                ],
                check=True,
                capture_output=True,
                timeout=20,
            ).stdout
        )["packets"]
        first_end = int(packets[0]["pos"]) + int(packets[0]["size"])
        truncated.write_bytes(content[:first_end] + b"\x00" * (packet_end - first_end) + content[packet_end:])
        from takeone.editor.analysis.probe import probe

        self.assertEqual(probe(truncated).duration_s, 1.0)
        for path in (self.allowed / "long.mov", self.allowed / "square.mov", corrupt, truncated):
            with self.subTest(path=path):
                self.assert_rejected({**self.body, "path": str(path)})

    def test_library_symlink_escape_is_rejected_without_writing_outside(self):
        outside = self.root / "outside-library"
        outside.mkdir()
        folder = media_dir(self.workspace, "demo")
        folder.rmdir()
        folder.symlink_to(outside, target_is_directory=True)
        self.assert_rejected(self.body)
        self.assertEqual(list(outside.iterdir()), [])

    def test_decode_timeout_rejects_without_import(self):
        from takeone.editor import vfx

        actual_run = subprocess.run

        def timeout_decoder(argv, **kwargs):
            if Path(argv[0]).name == "ffmpeg":
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return actual_run(argv, **kwargs)

        with patch.object(vfx.subprocess, "run", side_effect=timeout_decoder):
            self.assert_rejected(self.body)

    def test_missing_name_uses_filename_and_renamed_candidate_reuses(self):
        body = copy.deepcopy(self.body)
        del body["name"]
        first = self.post(body)
        self.assertEqual(self.service.state("demo").media[first["media_id"]].name, "candidate.mov")
        renamed = self.allowed / "renamed.mov"
        shutil.copyfile(self.candidate, renamed)
        body["path"] = str(renamed)
        body["name"] = "Updated display name does not change lineage"
        self.assertTrue(self.post(body)["reused"])

    def test_corrupted_stored_copy_is_not_reported_as_reused(self):
        result = self.post()
        stored = Path(self.service.state("demo").media[result["media_id"]].path)
        stored.write_bytes(stored.read_bytes() + b"corruption")
        self.assert_rejected(self.body)

    def test_finalized_project_has_no_partial_import(self):
        self.api.place("demo", {"media_id": self.source_id})
        self.service.submit("demo", op(OperationType.FINALIZE_TIMELINE, Target.project()))
        self.assert_rejected(self.body)

    def test_commit_failure_removes_only_new_copy(self):
        sentinel = media_dir(self.workspace, "demo") / "keep.mov"
        shutil.copyfile(self.candidate, sentinel)
        with patch.object(self.service, "submit", side_effect=EditorError("injected journal failure")):
            self.assert_rejected(self.body)
        self.assertTrue(sentinel.is_file())

    def test_post_commit_publish_failure_does_not_delete_registered_media(self):
        # A notification failure after SQLite commit must never destroy committed bytes.
        with patch.object(self.service, "_publish", side_effect=EditorError("injected notification failure")):
            with self.assertRaises(EditorError):
                self.post()
        media = next(
            item for item in self.service.state("demo").media.values() if item.media_id != self.source_id
        )
        self.assertTrue(Path(media.path).is_file())
        self.reopen()
        self.assertTrue(self.post()["reused"])

    def test_loopback_http_persists_lineage_and_replays(self):
        server = _editor_http().serve(self.api, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/editor/projects/demo/vfx/derivatives",
                json.dumps(self.body).encode(),
                {"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.reopen()
        self.assertEqual(
            self.service.history("demo")[-1]["operation"]["metadata"]["vfx_lineage"], result["lineage"]
        )
        self.assertTrue(self.post()["reused"])

    def upload(self, metadata, duplicate=False):
        boundary = "takeone-reviewed-upload"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'
            f"{json.dumps(metadata)}\r\n"
        ).encode()
        part = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="candidate.mov"\r\n'
                "Content-Type: video/quicktime\r\n\r\n"
            ).encode()
            + self.candidate.read_bytes()
            + b"\r\n"
        )
        body += part * (2 if duplicate else 1) + f"--{boundary}--\r\n".encode()
        server = _editor_http().serve(self.api, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/editor/projects/demo/vfx/derivatives/upload",
                body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=30) as response:
                    return response.status, json.load(response)
            except HTTPError as error:
                with error:
                    return error.code, json.load(error)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def upload_metadata(self):
        return {key: value for key, value in copy.deepcopy(self.body).items() if key != "path"}

    def assert_upload_clean(self):
        self.assertEqual(list((self.workspace / "tmp").iterdir()), [])
        self.assertEqual(list(media_dir(self.workspace, "demo").glob("vfx-upload-*")), [])
        self.assertEqual(file_digest(self.original), self.original_digest)

    def test_reviewed_upload_imports_without_placement_and_reuses_after_reload(self):
        before = self.service.state("demo").timeline.wire()
        status, result = self.upload(self.upload_metadata())
        self.assertEqual(status, 200, result)
        self.assertFalse(result["placed"])
        self.assertEqual(result["lineage"]["source_sha256"], self.original_digest)
        self.assertEqual(self.service.state("demo").timeline.wire(), before)
        self.assert_upload_clean()
        self.reopen()
        status, retry = self.upload(self.upload_metadata())
        self.assertEqual(status, 200, retry)
        self.assertTrue(retry["reused"])
        self.assertEqual(retry["lineage"], result["lineage"])
        self.assert_upload_clean()

    def test_reviewed_upload_rejection_does_not_register_media(self):
        for mutate in ("review", "hash", "path"):
            with self.subTest(mutate=mutate):
                metadata = self.upload_metadata()
                if mutate == "review":
                    metadata["review"]["preserved"]["people"] = False
                elif mutate == "hash":
                    metadata["source_sha256"] = "0" * 64
                else:
                    metadata["path"] = str(self.original)
                before = self.service.state("demo").wire()
                status, result = self.upload(metadata)
                self.assertEqual(status, 400, result)
                self.assertEqual(self.service.state("demo").wire(), before)
                self.assert_upload_clean()

    def test_reviewed_upload_rejects_duplicate_files_and_cleans_staging(self):
        status, result = self.upload(self.upload_metadata(), duplicate=True)
        self.assertEqual(status, 400, result)
        self.assertEqual(len(self.service.state("demo").media), 1)
        self.assert_upload_clean()


if __name__ == "__main__":
    unittest.main()
