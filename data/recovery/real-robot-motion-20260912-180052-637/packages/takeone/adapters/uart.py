"""Real UART transport, disconnected until connect(). No speed feedback exists."""

import threading

from takeone.config import finite
from takeone.protocol import uart_pair


class MotorUART:
    simulated = False

    def __init__(self, port, baudrate=115200, timeout=0.1, serial_factory=None, write_timeout=None):
        if not isinstance(port, str) or not port.strip():
            raise ValueError("An explicit port is required")
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = timeout if write_timeout is None else write_timeout
        if finite(self.timeout, "Serial timeout") <= 0 or finite(self.write_timeout, "Write timeout") <= 0:
            raise ValueError("Serial timeouts must be positive")
        self._factory = serial_factory
        self._serial = None
        self._lock = threading.Lock()

    @property
    def connected(self):
        return self._serial is not None and self._serial.is_open

    def connect(self):
        with self._lock:
            if self.connected:
                return
            factory = self._factory
            if factory is None:
                import serial  # Optional dependency; never imported by simulation.

                factory = serial.Serial
            connection = factory()
            connection.port = self.port
            connection.baudrate = self.baudrate
            connection.timeout = self.timeout
            connection.write_timeout = self.write_timeout
            connection.rtscts = False
            connection.dsrdtr = False
            connection.xonxoff = False
            connection.dtr = False
            connection.rts = False
            try:
                connection.open()
            except Exception:
                connection.close()
                raise
            self._serial = connection

    def set_speed(self, left, right):
        packet = uart_pair(left, right)
        with self._lock:
            if not self.connected:
                raise RuntimeError("Motor UART is not connected")
            data = packet.encode("ascii")
            if self._serial.write(data) != len(data):
                raise IOError("Incomplete motor packet; delivery unknown")
        return packet

    def stop(self):
        return self.set_speed(0.0, 0.0)

    def disconnect(self):
        if self.connected:
            try:
                self.stop()
            finally:
                self.close()

    def close(self):
        """Close after the owning runner's logged zero window; no implicit write."""
        with self._lock:
            if self.connected:
                self._serial.close()
