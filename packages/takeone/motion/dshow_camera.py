"""Named Windows DirectShow camera behind the OpenCV capture interface."""

import queue
import subprocess
import threading
import time


class DirectShowCamera:
    def __init__(self, config, *, cv2, numpy, stop, popen=subprocess.Popen):
        self.config = config
        self.cv2 = cv2
        self.numpy = numpy
        self.stop = stop
        self.width = config["width"]
        self.height = config["height"]
        self.frame_bytes = self.width * self.height * 3
        self.frames = queue.Queue(maxsize=1)
        self.closed = False
        self.received = False
        command = [
            config["ffmpeg"],
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-f",
            "dshow",
            "-i",
            "video=" + config["device_label"],
            "-an",
            "-vf",
            f"scale={self.width}:{self.height}",
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
            creationflags=(subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0),
        )
        self.reader = threading.Thread(target=self._read_frames, name="cart-camera-frames", daemon=True)
        self.reader.start()

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
        while not self.stop.is_set() and self.process.poll() is None:
            raw = self._read_exact()
            if raw is None:
                break
            frame = self.numpy.frombuffer(raw, dtype=self.numpy.uint8).reshape((self.height, self.width, 3))
            try:
                self.frames.get_nowait()
            except queue.Empty:
                pass
            self.frames.put_nowait((time.monotonic(), frame.copy()))
            self.received = True

    def isOpened(self):
        return not self.closed and self.process.poll() is None

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
