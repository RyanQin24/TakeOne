"""Project media folders: safe names, no path escape, and a placeable clip."""

import tempfile
import unittest
from pathlib import Path

from takeone.editor import reducer, state
from takeone.editor.errors import ValidationError
from takeone.editor.library import (
    ensure_project_library,
    find_media_by_digest,
    place_clip_operation,
    safe_filename,
    store_file,
    unique_destination,
    video_track,
)
from takeone.editor.operations import OperationType, Target

from tests.editor.support import ROOT, media_op, op, project_with_clips  # noqa: F401


class Naming(unittest.TestCase):
    def test_paths_and_spaces_are_stripped(self):
        self.assertEqual(safe_filename(r"..\\other\\Hero Take.mp4"), "Hero-Take.mp4")

    def test_an_unknown_suffix_is_refused(self):
        with self.assertRaises(ValidationError):
            safe_filename("notes.txt")


class Storage(unittest.TestCase):
    def test_a_project_folder_is_created_once(self):
        with tempfile.TemporaryDirectory() as folder:
            first = ensure_project_library(folder, "film-1")
            second = ensure_project_library(folder, "film-1")
            self.assertEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertEqual(first.name, "media")

    def test_a_name_collision_gets_a_suffix(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "clip.mp4").write_bytes(b"a")
            self.assertEqual(unique_destination(path, "clip.mp4").name, "clip-2.mp4")

    def test_store_copies_into_the_project_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.mp4"
            source.write_bytes(b"take")
            dest = store_file(Path(folder) / "library", "Night Scene.mp4", source)
            self.assertEqual(dest.name, "Night-Scene.mp4")
            self.assertEqual(dest.read_bytes(), b"take")
            self.assertTrue(dest.is_relative_to((Path(folder) / "library").resolve()))


class Placement(unittest.TestCase):
    def test_a_clip_is_appended_after_the_last_shot(self):
        current = project_with_clips(((0.0, 0.0, 2.0),))
        operation = place_clip_operation(current, "m1", "Second")
        self.assertEqual(operation.type, OperationType.ADD_CLIP)
        self.assertEqual(operation.parameters["timeline_start_s"], 2.0)
        current, _ = reducer.apply(current, operation)
        self.assertEqual(len(video_track(current).clips), 2)

    def test_mixed_frame_rates_do_not_overlap(self):
        current = state.empty("p-mix")
        current, _ = reducer.apply(current, media_op("m24", duration_s=49 / 24, fps_num=24, fps_den=1))
        current, _ = reducer.apply(current, media_op("m60", duration_s=3.017, fps_num=60, fps_den=1))
        current, _ = reducer.apply(
            current, op(OperationType.ADD_TRACK, Target.project(), track_id="V1", kind="video")
        )
        current, _ = reducer.apply(current, place_clip_operation(current, "m24"))
        current, _ = reducer.apply(current, place_clip_operation(current, "m60"))
        track = video_track(current)
        self.assertEqual(len(track.clips), 2)
        self.assertEqual(track.overlaps(), [])
        self.assertGreaterEqual(track.clips[1].timeline_start_s, track.clips[0].timeline_end_s)

    def test_the_same_bytes_are_the_same_media(self):
        current, _ = reducer.apply(state.empty("p"), media_op("m1"))
        digest = current.media["m1"].sha256
        self.assertEqual(find_media_by_digest(current, digest).media_id, "m1")
        self.assertIsNone(find_media_by_digest(current, "0" * 64))


if __name__ == "__main__":
    unittest.main()
