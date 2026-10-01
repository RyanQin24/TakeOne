"""Real STS3215 owner: read, fixed-goal activation, motion, retained hold, supported release.

Uses the installed LeRobot bus and its scservo packet handler. No follower setup,
mode/PID/limit/homing/calibration changes, reconnects or automatic re-enabling.
"""

import math
from dataclasses import asdict

from takeone.adapters.fixed_pose import activate_fixed_pose
from takeone.clock import monotonic
from takeone.contracts import JOINTS, ArmObservation

# Installed STS3215 table: one acknowledged 31-byte RAM block per motor.
RAM_FIELDS = {
    "Torque_Enable": (40, 1),
    "Goal_Position": (42, 2),
    "Torque_Limit": (48, 2),
    "Present_Position": (56, 2),
    "Present_Load": (60, 2),
    "Present_Voltage": (62, 1),
    "Present_Temperature": (63, 1),
    "Status": (65, 1),
    "Present_Current": (69, 2),
}


class LeRobotArm:
    simulated = False

    def __init__(self, bus, mapping, motor_ids, clock=monotonic):
        self.bus, self.mapping = bus, mapping
        self.motor_ids, self.clock = dict(motor_ids), clock
        self.connected = self.active = False
        self.last_raw_goal = None
        self.lifecycle = {}
        self.firmware_limits = {}
        self.last_command_attempt = None

    def _read_all(self, register):
        values = {}
        for name in JOINTS:
            try:
                values[name] = self.bus.read(register, name, normalize=False, num_retry=0)
            except ConnectionError as error:
                # A read is idempotent. Discard a corrupt/late reply and request
                # one fresh reply; never retry torque or motion writes here.
                self.lifecycle.setdefault("read_retries", []).append(
                    dict(register=register, joint=name, error=str(error), time_s=self.clock())
                )
                self.bus.port_handler.ser.reset_input_buffer()
                values[name] = self.bus.read(register, name, normalize=False, num_retry=0)
        return values

    def connect(self):
        actual = {name: motor.id for name, motor in self.bus.motors.items()}
        expected = {name: self.mapping.raw_calibration[name]["id"] for name in JOINTS}
        if actual != self.motor_ids or actual != expected or set(actual) != set(JOINTS):
            raise ValueError("Arm motor identity mismatch")
        if any(m.norm_mode.value != "degrees" for m in self.bus.motors.values()):
            raise ValueError("The installed calibrated degree convention is required")
        if {n: asdict(c) for n, c in self.bus.calibration.items()} != self.mapping.raw_calibration:
            raise ValueError("Bus calibration differs from the verified original")
        if self.bus.is_connected:
            raise ValueError("Arm bus must have one owner; it is already connected")
        try:
            self.bus.connect()
            if {n: asdict(c) for n, c in self.bus.read_calibration().items()} != self.mapping.raw_calibration:
                raise ValueError("Attached motors do not match the original calibration")
            for register in ("Operating_Mode", "Torque_Enable"):
                if any(v != 0 for v in self._read_all(register).values()):
                    raise ValueError(
                        f"{register}: initial position-mode, supported torque-off setup required"
                    )
            if any(v & 16 for v in self._read_all("Phase").values()):
                raise ValueError("Unsupported extended-angle mode")
            self.firmware_limits = {
                key: self._read_all(key)
                for key in (
                    "Min_Voltage_Limit",
                    "Max_Voltage_Limit",
                    "Max_Temperature_Limit",
                    "Max_Torque_Limit",
                    "P_Coefficient",
                )
            }
            for name in JOINTS:
                if (
                    not 0
                    < self.firmware_limits["Min_Voltage_Limit"][name]
                    < self.firmware_limits["Max_Voltage_Limit"][name]
                ):
                    raise ValueError(f"{name}: invalid firmware voltage limits")
                if any(
                    self.firmware_limits[k][name] <= 0
                    for k in ("Max_Temperature_Limit", "Max_Torque_Limit", "P_Coefficient")
                ):
                    raise ValueError(f"{name}: zero firmware temperature/torque/position gain")
            self.connected = True
            self.lifecycle.update(
                driver=type(self.bus).__module__,
                port=self.bus.port,
                motor_ids=self.motor_ids,
                firmware_limits_raw=self.firmware_limits,
            )
        except BaseException:
            self.disconnect()
            raise

    def read(self):
        if not self.connected:
            raise RuntimeError("Arm adapter disconnected")
        started = self.clock()
        health = {k: {} for k in RAM_FIELDS}
        intervals = {}
        for name in JOINTS:
            begin = self.clock()
            block, result, error = self.bus.packet_handler.readTxRx(
                self.bus.port_handler, self.motor_ids[name], 40, 31
            )
            end = self.clock()
            if result != 0 or error != 0 or len(block) != 31:
                raise ConnectionError(
                    f"{name}/ID {self.motor_ids[name]}: RAM read failed comm={result}, error={error}, bytes={len(block)}"
                )
            intervals[name] = [begin, end]
            for field, (address, length) in RAM_FIELDS.items():
                health[field][name] = int.from_bytes(
                    bytes(block[address - 40 : address - 40 + length]), "little"
                )
            limits = self.firmware_limits
            if (
                not limits["Min_Voltage_Limit"][name]
                <= health["Present_Voltage"][name]
                <= limits["Max_Voltage_Limit"][name]
            ):
                raise RuntimeError(f"{name}: voltage outside firmware limits")
            if health["Present_Temperature"][name] >= limits["Max_Temperature_Limit"][name]:
                raise RuntimeError(f"{name}: temperature reached firmware limit")
            if (
                not 0 < health["Torque_Limit"][name] <= limits["Max_Torque_Limit"][name]
                or health["Status"][name]
            ):
                raise RuntimeError(f"{name}: torque limit or servo status fault")
            if self.active and health["Torque_Enable"][name] != 1:
                raise RuntimeError(f"{name}: torque lost; no automatic re-enable")
            if (
                self.active
                and self.last_raw_goal
                and health["Goal_Position"][name] != self.last_raw_goal[name]
            ):
                raise RuntimeError(f"{name}: stored goal differs from the last acknowledged target")
        completed = self.clock()
        raw = health["Present_Position"]
        values = self.mapping.from_raw(raw)
        self.validate(values)
        health["acquisition_intervals_s"] = intervals
        return ArmObservation(values, (started + completed) / 2, "measured", started, completed, raw, health)

    def activate(self, observation, tolerance_rad):
        if self.active or self.lifecycle.get("torque_enable_attempted"):
            raise RuntimeError("Activation is single-use; no automatic re-enable")
        if observation.source != "measured" or observation.raw_positions is None:
            raise ValueError("Fixed activation requires actual raw positions")
        if not 0 <= self.clock() - observation.captured_monotonic_s <= 0.05:
            raise ValueError("Captured activation pose is stale")
        targets = dict(observation.raw_positions)
        self.lifecycle["targets_raw"] = targets
        activate_fixed_pose(
            self.bus,
            targets,
            self._read_all,
            lambda: self._read_all("Present_Position"),
            math.degrees(min(tolerance_rad)),
            self.lifecycle,
            clock=self.clock,
        )
        self.last_raw_goal = targets
        self.active = True

    def validate(self, q_rad):
        self.mapping.to_degrees(q_rad)

    def command(self, q_rad):
        if not self.connected or not self.active:
            raise RuntimeError("Arm is not in the owned active state")
        action = self.mapping.to_degrees(q_rad)
        raw = self.mapping.to_raw(q_rad)
        writes = []
        self.last_command_attempt = dict(requested_rad=q_rad, encoded_raw=raw, writes=writes)
        for name in JOINTS:
            start = self.clock()
            # Deliberate raw write: conversion occurred once above, matching the
            # installed degree mode's int() arithmetic. Every write is acknowledged.
            entry = dict(
                motor_id=self.motor_ids[name], raw_goal=raw[name], write_start_s=start, acknowledged=False
            )
            writes.append(entry)
            try:
                self.bus.write("Goal_Position", name, raw[name], normalize=False, num_retry=0)
                entry.update(write_end_s=self.clock(), acknowledged=True)
            except BaseException as error:
                entry.update(write_end_s=self.clock(), error=str(error))
                raise
            if self.last_raw_goal is not None:
                self.last_raw_goal[name] = raw[name]
        return dict(
            requested_servo_degrees=action,
            encoded_raw=raw,
            writes=writes,
            source="acknowledged_target_not_measured_position",
        )

    def hold(self, observation):
        if not self.active:
            raise RuntimeError("Cannot command hold when activation is incomplete")
        self.command(observation.q_rad)

    def release_supported(self):
        errors = []
        for name in JOINTS:
            try:
                self.bus.write("Torque_Enable", name, 0, normalize=False, num_retry=0)
            except Exception as error:
                errors.append(f"{name}: {error}")
        self.lifecycle["release_errors"] = errors
        self.lifecycle["torque_disabled_confirmed"] = not any(self._read_all("Torque_Enable").values())
        self.active = False
        if errors or not self.lifecycle["torque_disabled_confirmed"]:
            raise RuntimeError("Supported release not fully confirmed: " + "; ".join(errors))

    def disconnect(self):
        if self.bus.is_connected:
            self.bus.disconnect(disable_torque=False)
        self.connected = False


def openable_arm(device, mapping, io_limit_s):
    """Only the owning worker opens the real port, after complete preflight."""
    from lerobot.motors import Motor, MotorCalibration, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus
    from lerobot.motors.feetech.tables import STS_SMS_SERIES_CONTROL_TABLE

    if any(STS_SMS_SERIES_CONTROL_TABLE.get(name) != value for name, value in RAM_FIELDS.items()):
        raise ValueError("Installed STS register map differs from the reviewed RAM decoder")

    motors = {n: Motor(id_, "sts3215", MotorNormMode.DEGREES) for n, id_ in device["motor_ids"].items()}
    calibration = {n: MotorCalibration(**raw) for n, raw in mapping.raw_calibration.items()}
    bus = FeetechMotorsBus(device["port"], motors, calibration=calibration)
    if bus.model_resolution_table["sts3215"] != 4096 or bus.protocol_version != 0:
        raise ValueError("Installed STS3215 resolution or protocol differs from the reviewed conversion")
    # Keep SDK packet expiry in the same monotonic clock domain. Bound failed
    # transactions; LeRobot's default per-packet allowance exceeds a full cycle.
    port = bus.port_handler
    original_timeout = port.setPacketTimeout
    port.getCurrentTime = lambda: monotonic() * 1000

    def bounded_timeout(length):
        original_timeout(length)
        port.packet_timeout = min(port.packet_timeout, io_limit_s * 1000)

    port.setPacketTimeout = bounded_timeout
    arm = LeRobotArm(bus, mapping, device["motor_ids"])
    try:
        arm.connect()
        # The SDK defaults to timeout=0 and busy-polls until every reply arrives.
        # A bounded wait returns as soon as the requested bytes arrive, while
        # allowing Windows to schedule the other arm and cart workers.
        bus.port_handler.ser.timeout = min(0.001, io_limit_s)
        bus.port_handler.ser.write_timeout = io_limit_s
        arm.lifecycle["serial_read_timeout_s"] = bus.port_handler.ser.timeout
    except BaseException:
        arm.disconnect()
        raise
    return arm
