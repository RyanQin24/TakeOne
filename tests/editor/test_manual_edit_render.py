"""Synthetic local import -> reorder -> MP4 -> undo regression; no cloud or hardware."""

import hashlib
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from takeone.editor.api import EditorAPI
from takeone.editor.repository import ProjectRepository
from takeone.editor.service import EditorService

from tests.editor.test_render_qualification import frame_count, rgb_frame


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools required")
class ManualEditRender(unittest.TestCase):
    def test_import_reorder_export_and_undo_preserve_originals(self):
        with TemporaryDirectory(prefix="takeone-manual-edit-") as directory:
            root = Path(directory)
            service = EditorService(ProjectRepository(root / "projects.sqlite3"))
            api = EditorAPI(service, root / "editor", [root])
            service.create("manual", "Manual edit")
            originals = []
            for color, seconds in (("red", 1), ("blue", 2)):
                source = root / f"{color}.mp4"
                subprocess.run(
                    [
                        shutil.which("ffmpeg"),
                        "-v",
                        "error",
                        "-nostdin",
                        "-n",
                        "-f",
                        "lavfi",
                        "-i",
                        f"color=c={color}:s=160x90:r=30:d={seconds}",
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        str(source),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                originals.append((source, hashlib.sha256(source.read_bytes()).hexdigest()))
                receipt = api.receive_upload("manual", source.name, source, place=True)
                self.assertTrue(receipt["imported"])
                self.assertTrue(receipt["placed"])
            before = service.state("manual")
            blue = before.timeline.track("V1").clips[1]
            api.post(
                "/api/editor/projects/manual/operations",
                {
                    "operation": {
                        "type": "REORDER_CLIP",
                        "target": {"kind": "clip", "clip_id": blue.clip_id},
                        "parameters": {"index": 0},
                    }
                },
            )
            result = api.render("manual", {"target": "master", "wait": True})
            artifact = Path(result["artifact"])
            self.assertEqual(frame_count(artifact), 90)
            first, last = rgb_frame(artifact, 0.5), rgb_frame(artifact, 2.5)
            self.assertGreater(first[2], first[0] + 100)
            self.assertGreater(last[0], last[2] + 100)
            service.undo("manual", 1)
            self.assertEqual(service.state("manual").wire(), before.wire())
            restored = api.render("manual", {"target": "master", "wait": True})
            self.assertNotEqual(restored["work"]["output_id"], result["work"]["output_id"])
            first = rgb_frame(Path(restored["artifact"]), 0.5)
            self.assertGreater(first[0], first[2] + 100)
            for path, digest in originals:
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
