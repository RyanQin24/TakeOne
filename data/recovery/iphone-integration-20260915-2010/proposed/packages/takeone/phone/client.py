"""Bounded Blackmagic REST subset; framing uses measured lens calibration."""

import hashlib
import http.client
import ipaddress
import json
import math
import time
from urllib.parse import urlsplit


class CameraError(RuntimeError):
    """A camera failure, never a simulated success."""


def number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and between {low:g} and {high:g}.")
    return float(value)


def endpoint(value):
    """Numeric private addresses only: no discovery, proxies or redirects."""
    if not isinstance(value, str):
        raise ValueError("Enter the Blackmagic REST address shown on the phone.")
    try:
        parts = urlsplit(value)
        address = ipaddress.ip_address(parts.hostname or "")
        port = parts.port
    except ValueError:
        raise ValueError("Use the phone's numeric private-network IP address and port.") from None
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7")
    if not any(address in ipaddress.ip_network(net) for net in networks):
        raise ValueError("Use a private or loopback camera address, not a public/link-local address.")
    if (
        parts.scheme not in ("http", "https") or parts.username or parts.password or parts.query
        or parts.fragment or parts.path.rstrip("/") not in ("", "/control/api/v1")
    ):
        raise ValueError("Use http(s)://IP:PORT, optionally /control/api/v1, without credentials or query.")
    host = f"[{address}]" if address.version == 6 else str(address)
    default_port = 443 if parts.scheme == "https" else 80
    return f"{parts.scheme}://{host}" + (f":{port}" if port and port != default_port else "")


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
                raise CameraError(f"Camera {method} {path}: HTTP {response.status}. Check REST support/settings.")
            if time.perf_counter() - started >= self.timeout_s:
                raise TimeoutError()
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
            raise CameraError(f"Camera connection failed ({type(error).__name__}). Check phone/network.") from None
        except (ValueError, UnicodeError):
            raise CameraError("Camera returned invalid JSON; check its REST address and app version.") from None
        finally:
            connection.close()

    def recording(self):
        value = self.request("GET", "/transports/0/record")
        if not isinstance(value, dict) or type(value.get("recording")) is not bool:
            raise CameraError("Phone does not expose the documented recording readback.")
        return value["recording"]

    def zoom(self, normalised=None):
        if normalised is not None:
            self.request("PUT", "/lens/zoom", {"normalised": number(normalised, "Normalised zoom", 0, 1)})
        value = self.request("GET", "/lens/zoom")
        if not isinstance(value, dict):
            raise CameraError("Phone zoom readback is unavailable.")
        try:
            return number(value.get("normalised"), "Device zoom readback", 0, 1)
        except ValueError as error:
            raise CameraError(str(error)) from None

    def probe(self):
        product = self.request("GET", "/system/product")
        format_value = self.request("GET", "/system/format")
        description = self.request("GET", "/lens/zoom/description")
        if not isinstance(product, dict) or not product.get("productName") or not isinstance(format_value, dict):
            raise CameraError("Phone identity/recording format could not be verified.")
        if not isinstance(description, dict) or description.get("controllable") is not True:
            raise CameraError("The selected phone lens does not expose controllable zoom.")
