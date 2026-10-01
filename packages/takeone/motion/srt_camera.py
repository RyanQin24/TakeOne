"""Low-latency Blackmagic SRT frames behind the small OpenCV capture interface."""

import queue
import subprocess
import threading
import time
from xml.etree import ElementTree


def platform_xml(config):
    """Build Blackmagic's documented custom streaming service file."""
    root = ElementTree.Element("streaming")
    service = ElementTree.SubElement(root, "service")
    ElementTree.SubElement(service, "name").text = config["service_name"]
    servers = ElementTree.SubElement(service, "servers")
    server = ElementTree.SubElement(servers, "server")
    ElementTree.SubElement(server, "name").text = config["server"]
    ElementTree.SubElement(server, "url").text = config["push_url"]
    profiles = ElementTree.SubElement(service, "profiles", default=config["quality"])
    profile = ElementTree.SubElement(profiles, "profile")
    ElementTree.SubElement(profile, "name").text = config["quality"]
    stream = ElementTree.SubElement(
        profile,
        "config",
        resolution="1080p",
        fps="30",
        codec="H264",
    )
    ElementTree.SubElement(stream, "bitrate").text = "4000000"
    ElementTree.SubElement(stream, "audio-bitrate").text = "128000"
    ElementTree.SubElement(stream, "keyframe-interval").text = "1"
    return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)


class SrtCamera:
    """Receive the iPhone stream with FFmpeg and expose newest-frame-only reads."""

    def __init__(self, config, *, cv2, numpy, phone, stop, popen=subprocess.Popen):
        self.config = config
        self.cv2 = cv2
        self.numpy = numpy
        self.phone = phone
        self.stop = stop
        self.width = config["width"]
        self.height = config["height"]
        self.frame_bytes = self.width * self.height * 3
        self.frames = queue.Queue(maxsize=1)
        self.closed = False
        self.streaming = False
        self.start_attempted = False
        self.received = False
        self.error = None
        command = [
            config["ffmpeg"],
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-i",
            config["listen_url"],
            "-an",
            "-vf",
            f"scale={self.width}:{self.height},fps=15",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        self.process = popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        self.reader = threading.Thread(target=self._read_frames, name="iphone-srt-frames", daemon=True)
        self.reader.start()
        try:
            self.phone.request(
                "PUT",
                "/livestreams/customPlatforms/" + config["platform_file"],
                platform_xml(config),
                media_type="application/xml",
            )
            self.phone.request(
                "PUT",
                "/livestreams/0/activePlatform",
                {
                    "platform": config["platform"],
                    "server": config["server"],
                    "quality": config["quality"],
                    "url": config["push_url"],
                    "key": "",
                    "passphrase": "",
                },
            )
            self.start_attempted = True
            started = self.phone.request("PUT", "/livestreams/0/start")
            if started is not True:
                raise RuntimeError("Blackmagic Camera did not start its local SRT feed")
            self.streaming = True
        except BaseException:
            self.release()
            raise

    def _read_exact(self):
        chunks = []
        remaining = self.frame_bytes
        while remaining and not self.stop.is_set():
            chunk = self.process.stdout.read(remaining)
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks) if not remaining else None

    def _read_frames(self):
        try:
            while not self.stop.is_set() and self.process.poll() is None:
                raw = self._read_exact()
                if raw is None:
                    break
                frame = self.numpy.frombuffer(raw, dtype=self.numpy.uint8).reshape(
                    (self.height, self.width, 3)
                )
                try:
                    self.frames.get_nowait()
                except queue.Empty:
                    pass
                self.frames.put_nowait((time.monotonic(), frame.copy()))
                self.received = True
        except BaseException as error:
            self.error = error

    def isOpened(self):
        return not self.closed and self.streaming and self.process.poll() is None

    def get(self, prop):
        if prop == self.cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.width)
        if prop == getattr(self.cv2, "CAP_PROP_FRAME_HEIGHT", -1):
            return float(self.height)
        return 0.0

    def read(self):
        timeout = self.config["frame_timeout_s"] if self.received else self.config["connect_timeout_s"]
        deadline = time.monotonic() + timeout
        while not self.stop.is_set() and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                captured_at, frame = self.frames.get(timeout=min(0.05, remaining))
            except queue.Empty:
                if self.process.poll() is not None:
                    break
                continue
            if time.monotonic() - captured_at <= self.config["frame_timeout_s"]:
                return True, frame
        return False, None

    def release(self):
        if self.closed:
            return
        self.closed = True
        if self.start_attempted:
            try:
                self.phone.request("PUT", "/livestreams/0/stop")
            except Exception:
                pass
            self.start_attempted = False
            self.streaming = False
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        if self.process.stdout:
            self.process.stdout.close()
        if self.reader is not threading.current_thread():
            self.reader.join(timeout=1)
