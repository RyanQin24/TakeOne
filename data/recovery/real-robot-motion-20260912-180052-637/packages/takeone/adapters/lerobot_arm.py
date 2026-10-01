"""Read-verified motor bus ownership, without LeRobot follower bring-up side effects.

Only Goal_Position is written. Mode, torque, PID, calibration and homing are never
configured. Use the separate, supervised LeRobot setup before live execution.
"""

from dataclasses import asdict

from takeone.clock import monotonic
from takeone.contracts import JOINTS, ArmObservation


class LeRobotArm:
    simulated = False

    def __init__(self, bus, mapping, motor_ids, clock=monotonic):
        self.bus, self.mapping = bus, mapping
        self.motor_ids, self.clock = dict(motor_ids), clock
        self.connected = False

    def connect(self):
        actual = {name: motor.id for name, motor in self.bus.motors.items()}
        expected = {name: self.mapping.raw_calibration[name]["id"] for name in JOINTS}
        if actual != self.motor_ids or actual != expected or set(actual) != set(JOINTS):
            raise ValueError("Arm motor identity mismatch")
        if any(m.norm_mode.value != "degrees" for m in self.bus.motors.values()):
            raise ValueError("Calibrated servo degrees are required")
        if {name: asdict(c) for name, c in self.bus.calibration.items()} != self.mapping.raw_calibration:
            raise ValueError("Bus calibration differs from the verified original")
        if self.bus.is_connected:
            raise ValueError("Arm bus must have one owner; it is already connected")
        try:
            self.bus.connect()  # Bus handshake reads IDs/firmware; never follower.configure().
            calibration = {name: asdict(c) for name, c in self.bus.read_calibration().items()}
            if calibration != self.mapping.raw_calibration:
                raise ValueError("Attached motors do not match the original calibration")
            for register, expected_value in (("Operating_Mode", 0), ("Torque_Enable", 1)):
                values = self.bus.sync_read(register, normalize=False, num_retry=0)
                if set(values) != set(JOINTS) or any(v != expected_value for v in values.values()):
                    raise ValueError(f"Human-supervised setup required: {register} mismatch")
            phases = self.bus.sync_read("Phase", normalize=False, num_retry=0)
            if set(phases) != set(JOINTS) or any(int(v) & 16 for v in phases.values()):
                raise ValueError("Unsupported extended-angle mode; no implicit reconfiguration")
            self.connected = True
        except BaseException:
            self.disconnect()
            raise

    def read(self):
        if not self.connected:
            raise RuntimeError("Arm adapter disconnected")
        captured = self.clock()
        degrees = self.bus.sync_read("Present_Position", num_retry=0)
        if set(degrees) != set(JOINTS):
            raise ValueError("Incomplete encoder feedback")
        values = self.mapping.from_degrees({n + ".pos": v for n, v in degrees.items()})
        self.validate(values)
        return ArmObservation(values, captured, "measured")

    def validate(self, q_rad):
        self.mapping.to_degrees(q_rad)

    def command(self, q_rad):
        if not self.connected:
            raise RuntimeError("Arm adapter disconnected")
        action = self.mapping.to_degrees(q_rad)
        # Direct degree-mode sync_write has no relative-target clipping or camera
        # reads. The servo's finite encoder resolution still quantizes targets.
        self.bus.sync_write("Goal_Position", {n: action[n + ".pos"] for n in JOINTS}, num_retry=0)
        return dict(requested_servo_degrees=action, source="transmitted_not_measured")

    def hold(self, observation):
        self.command(observation.q_rad)

    def disconnect(self):
        if self.bus.is_connected:
            self.bus.disconnect(disable_torque=False)
        self.connected = False


def openable_arm(device, mapping, io_limit_s):
    """Open only inside the owning live worker, after offline qualification."""
    from lerobot.motors import Motor, MotorCalibration, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus

    motors = {name: Motor(id_, "sts3215", MotorNormMode.DEGREES) for name, id_ in device["motor_ids"].items()}
    calibration = {name: MotorCalibration(**raw) for name, raw in mapping.raw_calibration.items()}
    bus = FeetechMotorsBus(device["port"], motors, calibration=calibration)
    arm = LeRobotArm(bus, mapping, device["motor_ids"])
    try:
        arm.connect()
        bus.port_handler.ser.write_timeout = io_limit_s
    except BaseException:
        arm.disconnect()
        raise
    return arm
