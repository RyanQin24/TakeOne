"""Offline API/quantization check in the existing LeRobot environment; opening is forbidden."""

import inspect
import json
import math
from unittest.mock import patch

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

from takeone.calibration import ArmMapping
from takeone.contracts import JOINTS


with patch("scservo_sdk.PortHandler.openPort", side_effect=AssertionError("No hardware in API check")) as opened:
    with patch("scservo_sdk.PortHandler.writePort", side_effect=AssertionError("No hardware in API check")) as written:
        results = {}
        for role, wrist in (("phone", 6), ("light", 5)):
            ids = dict(zip(JOINTS, (1, 2, 3, 4, wrist)))
            raw = {n: dict(id=i, drive_mode=0, homing_offset=0, range_min=0, range_max=4095) for n, i in ids.items()}
            mapping = ArmMapping((1, -1, 1, 1, 1), (10, 0, 0, 0, 0), ((-1, 1),) * 5, raw)
            bus = FeetechMotorsBus("OFFLINE_NO_PORT", {n: Motor(i, "sts3215", MotorNormMode.DEGREES) for n, i in ids.items()}, {n: MotorCalibration(**r) for n, r in raw.items()})
            q = (0.1, 0.2, -0.3, 0.4, -0.5)
            action = mapping.to_degrees(q)
            targets = bus._unnormalize({ids[n]: action[n + ".pos"] for n in JOINTS})
            observed = bus._normalize(targets)
            restored = mapping.from_degrees({n + ".pos": observed[ids[n]] for n in JOINTS})
            error = max(abs(a - b) for a, b in zip(q, restored))
            assert error < 2 * math.pi / 4095
            assert not bus.is_connected
            for method in (bus.sync_read, bus.sync_write):
                assert "num_retry" in inspect.signature(method).parameters
            results[role] = dict(motor_ids=ids, encoder_quantization_error_rad=error)
        print(json.dumps(dict(passed=True, port_open_attempts=opened.call_count, packet_write_attempts=written.call_count,
                              calibration="synthetic API test only", physical_motion_verified=False,
                              driver_source=inspect.getsourcefile(FeetechMotorsBus), roles=results), indent=2))
