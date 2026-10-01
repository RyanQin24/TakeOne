"""Documented Blackmagic REST subset; never assumes mobile zoom units."""

import hashlib
import hmac
import http.client
import ipaddress
import json
import math
import ssl
import time
from urllib.parse import urlsplit


class CameraError(RuntimeError):
    pass


FRAME_RATES = (24, 25, 30, 50, 60)
RECORDING_RESOLUTIONS = {"1080p": (1920, 1080), "4k": (3840, 2160)}


def number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be a finite number between {low:g} and {high:g}.")
    return float(value)


def endpoint(value):
    """Literal local-network addresses only: no DNS rebinding, proxies or redirects."""
    if not isinstance(value, str):
        raise ValueError("Enter the Blackmagic REST address shown on your iPhone.")
    parts = urlsplit(value)
    try:
        address = ipaddress.ip_address(parts.hostname or "")
        port = parts.port
    except ValueError:
        raise ValueError("Use the phone's numeric private-network IP address and port.") from None
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7")
    if not any(address in ipaddress.ip_network(net) for net in networks):
        raise ValueError("The camera must be on a private network, not a public or link-local address.")
    if (
        parts.scheme not in ("http", "https")
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path.rstrip("/") not in ("", "/control/api/v1")
    ):
        raise ValueError("Use http(s)://IP:PORT, optionally /control/api/v1, without credentials or query.")
    host = f"[{address}]" if address.version == 6 else str(address)
    return f"{parts.scheme}://{host}" + (f":{port}" if port else "")


class BlackmagicCamera:
    def __init__(self, address, timeout_s=0.75, *, cert_sha256=""):
        self.address = endpoint(address)
        self.timeout_s = number(timeout_s, "Camera timeout", 0.1, 3.0)
        if not isinstance(cert_sha256, str) or (
            cert_sha256 and (len(cert_sha256) != 64 or any(c not in "0123456789abcdef" for c in cert_sha256))
        ):
            raise ValueError("The phone certificate pin must be a lowercase SHA-256 hex digest.")
        self.cert_sha256 = cert_sha256

    def request(self, method, path, body=None, *, media_type="application/json"):
        parts = urlsplit(self.address)
        kind = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        options = {"timeout": self.timeout_s}
        if parts.scheme == "https" and self.cert_sha256:
            # The phone serves a self-signed certificate. Pin its exact DER
            # fingerprint before sending any command, including record/stop.
            options["context"] = ssl._create_unverified_context()
        connection = kind(parts.hostname, parts.port, **options)
        started = time.perf_counter()
        try:
            if parts.scheme == "https" and self.cert_sha256:
                connection.connect()
                certificate = connection.sock.getpeercert(binary_form=True)
                actual = hashlib.sha256(certificate).hexdigest()
                if not hmac.compare_digest(actual, self.cert_sha256):
                    raise CameraError(
                        "Phone HTTPS certificate changed; verify its identity before reconnecting."
                    )
            if media_type == "application/json":
                raw = None if body is None else json.dumps(body, allow_nan=False).encode()
            elif media_type == "application/xml":
                if not isinstance(body, str) or not body:
                    raise ValueError("Camera XML body must be non-empty text.")
                raw = body.encode("utf-8")
            else:
                raise ValueError("Unsupported camera request media type.")
            connection.request(
                method,
                "/control/api/v1" + path,
                raw,
                {"Content-Type": media_type},
            )
            response = connection.getresponse()
            if response.status not in (200, 204):
                raise CameraError(
                    f"Camera {method} {path}: HTTP {response.status}. Check REST support/settings."
                )
            if response.status == 204:
                return None
            chunks, size = [], 0
            while True:
                remaining = self.timeout_s - (time.perf_counter() - started)
                if remaining <= 0:
                    raise TimeoutError()
                if connection.sock:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(8192)
                if not chunk:
                    break
                size += len(chunk)
                if size > 131072:
                    raise CameraError("Camera response exceeds 128 KiB.")
                chunks.append(chunk)
            return json.loads(b"".join(chunks))
        except (OSError, http.client.HTTPException) as error:
            raise CameraError(
                f"Camera connection failed ({type(error).__name__}). Check phone and network."
            ) from None
        except (ValueError, UnicodeError):
            raise CameraError(
                "Camera returned invalid JSON; check its REST address and app version."
            ) from None
        finally:
            connection.close()

    def recording(self):
        value = self.request("GET", "/transports/0/record")
        if not isinstance(value, dict) or type(value.get("recording")) is not bool:
            raise CameraError("Camera does not expose the documented recording readback.")
        return value["recording"]

    def zoom(self, normalised=None):
        if normalised is not None:
            self.request("PUT", "/lens/zoom", {"normalised": number(normalised, "Normalised zoom", 0, 1)})
        value = self.request("GET", "/lens/zoom")
        if not isinstance(value, dict):
            raise CameraError("Camera zoom readback is unavailable.")
        try:
            return number(value.get("normalised"), "Device zoom readback", 0, 1)
        except ValueError as error:
            raise CameraError(str(error)) from None

    def set_recording_format(self, frame_rate, resolution):
        """Apply and verify one explicit Blackmagic resolution/frame-rate pair."""
        if type(frame_rate) is not int or frame_rate not in FRAME_RATES:
            raise ValueError("Frame rate must be one of 24, 25, 30, 50 or 60 fps.")
        if resolution not in RECORDING_RESOLUTIONS:
            raise ValueError("Recording resolution must be 1080p or 4k.")
        current = self.request("GET", "/system/format")
        if not isinstance(current, dict):
            raise CameraError("Camera recording format could not be read.")
        width, height = RECORDING_RESOLUTIONS[resolution]
        documented = (
            "codec",
            "frameRate",
            "maxOffSpeedFrameRate",
            "minOffSpeedFrameRate",
            "offSpeedEnabled",
            "offSpeedFrameRate",
            "recordResolution",
            "sensorResolution",
        )
        requested = {key: current[key] for key in documented if key in current}
        requested.update(
            frameRate=str(frame_rate),
            offSpeedEnabled=False,
            recordResolution={"width": width, "height": height},
            sensorResolution={"width": width, "height": height},
        )
        self.request("PUT", "/system/format", requested)
        observed = self.request("GET", "/system/format")
        if not isinstance(observed, dict) or observed.get("frameRate") != str(frame_rate):
            raise CameraError(f"Phone did not confirm {frame_rate} fps. Inspect its recording format.")
        if observed.get("recordResolution") != {"width": width, "height": height}:
            raise CameraError(f"Phone did not confirm {resolution} recording. Inspect its recording format.")
        if observed.get("sensorResolution") != {"width": width, "height": height}:
            raise CameraError(f"Phone did not confirm the {resolution} sensor mode. Inspect its recording format.")
        if observed.get("offSpeedEnabled") is not False:
            raise CameraError("Phone enabled off-speed recording instead of the requested project frame rate.")
        return observed

    def probe(self):
        product = self.request("GET", "/system/product")
        format_value = self.request("GET", "/system/format")
        description = self.request("GET", "/lens/zoom/description")
        if (
            not isinstance(product, dict)
            or not product.get("productName")
            or not isinstance(format_value, dict)
        ):
            raise CameraError("Camera identity/recording format could not be verified.")
        if not isinstance(description, dict) or description.get("controllable") is not True:
            raise CameraError("The selected phone lens does not expose controllable zoom.")
        identity = dict(product=product, format=format_value, zoom_description=description)
        fingerprint = hashlib.sha256(
            json.dumps(identity, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        return dict(
            identity,
            fingerprint=fingerprint,
            recording=self.recording(),
            normalised=self.zoom(),
            source="device_reported",
            optical_framing_verified=False,
        )

    def wait_recording(self, expected, timeout_s=2.0):
        deadline = time.perf_counter() + timeout_s
        while self.recording() is not expected:
            if time.perf_counter() >= deadline:
                raise CameraError(f"Phone did not confirm recording={expected}; inspect it before retrying.")
            time.sleep(0.05)


def calibration_points(points):
    if not isinstance(points, list) or not 2 <= len(points) <= 32:
        raise ValueError("Measure at least two lens calibration points before linking.")
    previous, result = (0.0, -1.0), []
    for point in points:
        if not isinstance(point, dict) or set(point) != {"focal_mm", "normalised"}:
            raise ValueError("Each lens calibration point needs focal_mm and normalised.")
        pair = (
            number(point["focal_mm"], "Equivalent focal length", 13, 360),
            number(point["normalised"], "Normalised zoom", 0, 1),
        )
        if pair[0] <= previous[0] or pair[1] <= previous[1]:
            raise ValueError("Calibration must increase in both equivalent focal length and zoom.")
        previous = pair
        result.append(pair)
    return result


def mapped_zoom(points, focal_mm):
    focal = number(focal_mm, "Equivalent focal length", 13, 360)
    if not points[0][0] <= focal <= points[-1][0]:
        raise ValueError(
            f"Requested {focal:g} mm is outside measured phone range "
            f"{points[0][0]:g}-{points[-1][0]:g} mm. No silent clamp or lens switch."
        )
    for (fa, za), (fb, zb) in zip(points, points[1:]):
        if focal <= fb:
            return za + (zb - za) * (focal - fa) / (fb - fa)
    return points[-1][1]
