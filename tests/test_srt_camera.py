"""Wireless iPhone capture lifecycle with fake FFmpeg and phone REST only."""

import io
import threading
import unittest
from types import SimpleNamespace

import numpy
from takeone.motion.srt_camera import SrtCamera


class FakePhone:
    def __init__(self):
        self.requests = []

    def request(self, method, path, body=None, **kwargs):
        self.requests.append((method, path, body, kwargs))
        return True if path.endswith("/start") else None


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


class SrtCameraTests(unittest.TestCase):
    def test_newest_frame_interface_and_phone_stream_lifecycle(self):
        config = {
            "ffmpeg": "ffmpeg.exe",
            "listen_url": "srt://0.0.0.0:9000?mode=listener",
            "push_url": "srt://10.0.0.2:9000",
            "width": 4,
            "height": 2,
            "connect_timeout_s": 1.0,
            "frame_timeout_s": 0.5,
            "platform_file": "TakeOneLocalSRT.xml",
            "service_name": "TakeOne Local SRT",
            "platform": "TakeOne Local SRT SRT",
            "server": "TakeOne Laptop",
            "quality": "Tracking 1080p",
        }
        raw = bytes(range(24))
        process = FakeProcess(raw)
        commands = []

        def popen(command, **kwargs):
            commands.append((command, kwargs))
            return process

        phone = FakePhone()
        camera = SrtCamera(
            config,
            cv2=SimpleNamespace(CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4),
            numpy=numpy,
            phone=phone,
            stop=threading.Event(),
            popen=popen,
        )
        ok, frame = camera.read()
        self.assertTrue(ok)
        self.assertEqual(frame.shape, (2, 4, 3))
        self.assertEqual(camera.get(3), 4)
        self.assertIn(config["listen_url"], commands[0][0])
        self.assertEqual(phone.requests[0][1], "/livestreams/customPlatforms/TakeOneLocalSRT.xml")
        self.assertEqual(phone.requests[0][3], {"media_type": "application/xml"})
        self.assertIn("srt://10.0.0.2:9000", phone.requests[0][2])
        self.assertEqual(phone.requests[1][1], "/livestreams/0/activePlatform")
        self.assertEqual(phone.requests[2][:3], ("PUT", "/livestreams/0/start", None))
        camera.release()
        self.assertTrue(process.terminated)
        self.assertEqual(phone.requests[-1][:3], ("PUT", "/livestreams/0/stop", None))


if __name__ == "__main__":
    unittest.main()
