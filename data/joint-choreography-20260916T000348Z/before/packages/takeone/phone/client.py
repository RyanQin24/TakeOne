"""Documented Blackmagic REST subset; never assumes mobile zoom units."""

import hashlib
import http.client
import ipaddress
import json
import math
import time
from urllib.parse import urlsplit


class CameraError(RuntimeError):
    pass


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
    def __init__(self, address, timeout_s=0.75):
        self.address = endpoint(address)
        self.timeout_s = number(timeout_s, "Camera timeout", 0.1, 3.0)

    def request(self, method, path, body=None):
        parts = urlsplit(self.address)
        kind = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        connection = kind(parts.hostname, parts.port, timeout=self.timeout_s)
        started = time.perf_counter()
        try:
            raw = None if body is None else json.dumps(body, allow_nan=False).encode()
            connection.request(method, "/control/api/v1" + path, raw, {"Content-Type": "application/json"})
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
