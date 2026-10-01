import serial
import threading

# motor caps
flt_reverseCap = -0.15
flt_fwdCap = 0.15

class MotorUART:
    def __init__(self, port="COM5", baudrate=115200, timeout=0.1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self._serial = None
        self._lock = threading.Lock()

    def connect(self):
        """Open the serial connection to the ESP32."""
        if self._serial is None or not self._serial.is_open:
            self._serial = serial.Serial()

            self._serial.port = self.port
            self._serial.baudrate = self.baudrate
            self._serial.timeout = self.timeout
            self._serial.write_timeout = self.timeout

            # must run to avoid ESP32 reset on initial connection
            self._serial.rtscts = False
            self._serial.dsrdtr = False
            self._serial.xonxoff = False
            self._serial.dtr = False
            self._serial.rts = False

            self._serial.open()

    def set_speed(self, left_speed: float, right_speed: float):
        """
        Send left and right motor speed commands.

        Expected range:
            full reverse
             0.0 = stopped
            full forward
        """

        # Prevent invalid commands
        left_speed = max(flt_reverseCap, min(flt_fwdCap, left_speed))
        right_speed = max(flt_reverseCap, min(flt_fwdCap, right_speed))

        message = f"{left_speed:.2f},{right_speed:.2f}\n"

        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise RuntimeError("Motor UART is not connected.")

            self._serial.write(bytes(message, "ascii"))

    def stop(self):
        """Stop both motors."""
        self.set_speed(0.0, 0.0)

    def close(self):
        """Close the serial port."""
        if self._serial is not None and self._serial.is_open:
            self._serial.close()

    @property
    def connected(self):
        return self._serial is not None and self._serial.is_open