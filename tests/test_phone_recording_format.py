"""Format selection uses the phone's advertised mode, without retrying writes."""

import unittest
from unittest.mock import Mock

from takeone.phone.client import BlackmagicCamera, CameraError


class RecordingFormatTests(unittest.TestCase):
    def setUp(self):
        self.client = BlackmagicCamera("http://127.0.0.1:4444")
        self.current = dict(codec="HEVC", frameRate="60", resolutionDescriptor=dict(group="4K"))
        self.size = dict(width=1920, height=1080)
        self.mode = dict(
            codecs=["HEVC"],
            frameRates=["60"],
            recordResolution=self.size,
            sensorResolution=self.size,
            resolutionDescriptor=dict(group="HD", aspectRatio="16:9"),
            minOffSpeedFrameRate=4,
            maxOffSpeedFrameRate=120,
        )
        self.after = dict(
            codec="HEVC",
            frameRate="60",
            offSpeedEnabled=False,
            recordResolution=self.size,
            sensorResolution=self.size,
        )

    def test_hd_uses_advertised_descriptor_instead_of_old_4k(self):
        self.client.request = Mock(
            side_effect=[self.current, dict(supportedFormats=[self.mode]), None, self.after]
        )
        self.assertEqual(self.client.set_recording_format(60, "1080p"), self.after)
        method, path, payload = self.client.request.call_args_list[2].args
        self.assertEqual((method, path), ("PUT", "/system/format"))
        self.assertEqual(payload["resolutionDescriptor"], self.mode["resolutionDescriptor"])
        self.assertEqual(payload["codec"], "HEVC")
        self.assertEqual(payload["recordResolution"], self.size)

    def test_unsupported_mode_does_not_send_a_write(self):
        self.client.request = Mock(side_effect=[self.current, dict(supportedFormats=[])])
        with self.assertRaisesRegex(CameraError, "supported"):
            self.client.set_recording_format(60, "1080p")
        self.assertTrue(all(call.args[0] == "GET" for call in self.client.request.call_args_list))

    def test_uncertain_format_write_is_not_retried(self):
        self.client.request = Mock(
            side_effect=[
                self.current,
                dict(supportedFormats=[self.mode]),
                CameraError("connection timed out"),
            ]
        )
        with self.assertRaises(CameraError):
            self.client.set_recording_format(60, "1080p")
        self.assertEqual(sum(call.args[0] == "PUT" for call in self.client.request.call_args_list), 1)


if __name__ == "__main__":
    unittest.main()
