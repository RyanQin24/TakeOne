"""Real UART transport, disconnected until connect(). No speed feedback exists."""

import threading

from takeone.config import finite
from takeone.protocol import COMMAND_CAP, uart_pair


class MotorUART:
    simulated = False

    def __init__(
        self, port, baudrate=115200, timeout=0.1, serial_factory=None, write_timeout=None, polarity=1
    ):
        if not isinstance(port, str) or not port.strip():
            raise ValueError("An explicit port is required")
        if polarity not in (1, -1):
            raise ValueError("Wire polarity must be exactly 1 or -1")
        # Wiring fact, not a planning choice: the plan stays in logical forward
        # units and this adapter emits the sign the controller actually needs.
        self.polarity = polarity
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
        if any(abs(finite(v, "Wheel command")) > COMMAND_CAP for v in (left, right)):
            raise ValueError("Refusing a command that the UART formatter would clip")
        # Check the reviewed logical values, then transmit with the wiring's sign.
        if tuple(map(float, uart_pair(left, right).split(","))) != (left, right):
            raise ValueError("Physical commands must already match the reviewed two-decimal wire values")
        # `or 0.0` collapses negative zero: an inverted stop must still format as
        # 0.00,0.00, not -0.00,-0.00, which the controller would not recognise.
        packet = uart_pair(self.polarity * left or 0.0, self.polarity * right or 0.0)
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
