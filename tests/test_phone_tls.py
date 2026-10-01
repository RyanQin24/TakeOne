"""The iPhone's self-signed HTTPS certificate is pinned before commands."""

import hashlib
import http.client
import unittest
from unittest.mock import patch

from takeone.phone.client import BlackmagicCamera, CameraError


class FakeSocket:
    def getpeercert(self, *, binary_form):
        assert binary_form
        return b"phone-certificate"


class FakeResponse:
    status = 204


class FakeConnection:
    def __init__(self):
        self.sock = FakeSocket()
        self.requests = []
        self.closed = False
        self.connected = False

    def connect(self):
        self.connected = True

    def request(self, *args):
        self.requests.append(args)

    def getresponse(self):
        return FakeResponse()

    def close(self):
        self.closed = True


class PhoneTLSTests(unittest.TestCase):
    def test_zoom_prefetch_authenticates_and_closes_every_socket(self):
        connections = []

        def factory(*args, **kwargs):
            transport = FakeConnection()
            connections.append(transport)
            return transport

        pin = hashlib.sha256(b"phone-certificate").hexdigest()
        with patch("takeone.phone.client.http.client.HTTPSConnection", side_effect=factory):
            camera = BlackmagicCamera("https://10.1.2.3:4444", cert_sha256=pin)
            with camera.zoom_stream():
                camera.set_zoom(0.01)
                camera.set_zoom(0.02)
        self.assertEqual(sum(len(c.requests) for c in connections), 2)
        self.assertTrue(all(c.connected and c.closed for c in connections))
        requested = [r[2] for c in connections for r in c.requests]
        self.assertEqual(sorted(requested), [b'{"normalised": 0.01}', b'{"normalised": 0.02}'])

    def test_prefetched_certificate_mismatch_cannot_send_zoom(self):
        connections = []

        def factory(*args, **kwargs):
            transport = FakeConnection()
            connections.append(transport)
            return transport

        with patch("takeone.phone.client.http.client.HTTPSConnection", side_effect=factory):
            camera = BlackmagicCamera("https://10.1.2.3:4444", cert_sha256="0" * 64)
            with self.assertRaisesRegex(CameraError, "certificate changed"):
                with camera.zoom_stream():
                    camera.set_zoom(0.01)
        self.assertTrue(all(not c.requests and c.closed for c in connections))

    def test_uncertain_prefetched_put_is_never_retried(self):
        connections = []

        def factory(*args, **kwargs):
            transport = FakeConnection()
            transport.getresponse = lambda: (_ for _ in ()).throw(http.client.RemoteDisconnected())
            connections.append(transport)
            return transport

        pin = hashlib.sha256(b"phone-certificate").hexdigest()
        with patch("takeone.phone.client.http.client.HTTPSConnection", side_effect=factory):
            camera = BlackmagicCamera("https://10.1.2.3:4444", cert_sha256=pin)
            with self.assertRaisesRegex(CameraError, "connection failed"):
                with camera.zoom_stream():
                    camera.set_zoom(0.01)
        self.assertEqual(sum(len(c.requests) for c in connections), 1)
        self.assertTrue(all(c.closed for c in connections))

    def test_matching_certificate_allows_record_command(self):
        transport = FakeConnection()
        pin = hashlib.sha256(b"phone-certificate").hexdigest()
        with patch("takeone.phone.client.http.client.HTTPSConnection", return_value=transport):
            camera = BlackmagicCamera("https://10.1.2.3:4444", cert_sha256=pin)
            self.assertIsNone(camera.request("POST", "/transports/0/record", {}))
        self.assertEqual(len(transport.requests), 1)

    def test_changed_certificate_blocks_record_before_request(self):
        transport = FakeConnection()
        with patch("takeone.phone.client.http.client.HTTPSConnection", return_value=transport):
            camera = BlackmagicCamera("https://10.1.2.3:4444", cert_sha256="0" * 64)
            with self.assertRaisesRegex(CameraError, "certificate changed"):
                camera.request("POST", "/transports/0/record", {})
        self.assertEqual(transport.requests, [])

    def test_custom_streaming_xml_uses_xml_content_type(self):
        transport = FakeConnection()
        pin = hashlib.sha256(b"phone-certificate").hexdigest()
        with patch("takeone.phone.client.http.client.HTTPSConnection", return_value=transport):
            camera = BlackmagicCamera("https://10.1.2.3:4444", cert_sha256=pin)
            camera.request(
                "PUT",
                "/livestreams/customPlatforms/TakeOne.xml",
                "<streaming />",
                media_type="application/xml",
            )
        self.assertEqual(transport.requests[0][2], b"<streaming />")
        self.assertEqual(transport.requests[0][3], {"Content-Type": "application/xml"})


if __name__ == "__main__":
    unittest.main()
