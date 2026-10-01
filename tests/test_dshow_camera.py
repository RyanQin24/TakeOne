"""Named cart-camera capture lifecycle with fake FFmpeg only."""

import io
import threading
import unittest
from types import SimpleNamespace

import numpy
from takeone.motion.dshow_camera import DirectShowCamera


class FakeProcess:
    def __init__(self, raw):
        self.stdout = io.BytesIO(raw)
        self.code = None
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = 0

    def kill(self):
        self.code = -9

    def wait(self, timeout=None):
        return self.code


class DirectShowCameraTests(unittest.TestCase):
    def test_newest_frame_interface_uses_exact_device_name(self):
        config = {
            "ffmpeg": "ffmpeg.exe",
            "device_label": "Live Streamer CAM 313",
            "width": 4,
            "height": 2,
            "connect_timeout_s": 1.0,
            "frame_timeout_s": 0.5,
        }
        process = FakeProcess(bytes(range(24)))
        commands = []

        def popen(command, **kwargs):
            commands.append((command, kwargs))
            return process

        cv2 = SimpleNamespace(CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4)
        camera = DirectShowCamera(
            config,
            cv2=cv2,
            numpy=numpy,
            stop=threading.Event(),
            popen=popen,
        )
        ok, frame = camera.read()
        self.assertTrue(ok)
        self.assertEqual(frame.shape, (2, 4, 3))
        self.assertEqual(camera.get(cv2.CAP_PROP_FRAME_WIDTH), 4)
        self.assertIn("video=Live Streamer CAM 313", commands[0][0])
        camera.release()
        self.assertTrue(process.terminated)


if __name__ == "__main__":
    unittest.main()
