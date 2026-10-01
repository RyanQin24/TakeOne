#!/usr/bin/env python

# Copyright 2026 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import MagicMock, patch

import pytest

from lerobot.teleoperators.so_leader import SO100Leader, SO100LeaderConfig

BODY_MOTORS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]


@pytest.mark.parametrize(
    ("has_gripper", "motor_ids", "expected_motor_ids"),
    [
        (True, None, [1, 2, 3, 4, 5, 6]),
        (False, None, [1, 2, 3, 4, 5]),
        (
            False,
            {
                "shoulder_pan": 1,
                "shoulder_lift": 2,
                "elbow_flex": 3,
                "wrist_flex": 4,
                "wrist_roll": 6,
            },
            [1, 2, 3, 4, 6],
        ),
    ],
)
def test_motor_layout_respects_config(tmp_path, has_gripper, motor_ids, expected_motor_ids):
    bus_mock = MagicMock(name="FeetechBusMock")

    def _bus_side_effect(*_args, **kwargs):
        bus_mock.motors = kwargs["motors"]
        return bus_mock

    with patch(
        "lerobot.teleoperators.so_leader.so_leader.FeetechMotorsBus",
        side_effect=_bus_side_effect,
    ):
        config_kwargs = {
            "port": "/dev/null",
            "calibration_dir": tmp_path,
            "has_gripper": has_gripper,
        }
        if motor_ids is not None:
            config_kwargs["motor_ids"] = motor_ids
        leader = SO100Leader(SO100LeaderConfig(**config_kwargs))

    expected_motor_names = [*BODY_MOTORS, *(("gripper",) if has_gripper else ())]
    assert list(leader.bus.motors) == expected_motor_names
    assert [motor.id for motor in leader.bus.motors.values()] == expected_motor_ids
    assert set(leader.action_features) == {f"{motor}.pos" for motor in expected_motor_names}
