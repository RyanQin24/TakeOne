"""Explicit simulated or physical device composition, constructed in child processes."""

from dataclasses import dataclass

from takeone.adapters.simulated import SimulatedArm, SimulatedCart


@dataclass(frozen=True)
class DeviceFactory:
    simulated: bool
    devices: dict | None = None
    mappings: dict | None = None

    def open(self, role, plan, arm_timing, cart_timing):
        if self.simulated:
            return SimulatedCart() if role == "cart" else SimulatedArm(plan.arm_at(role, 0))
        from takeone.adapters.identity import identify_port

        device = self.devices["cart"] if role == "cart" else self.devices["arms"][role]
        identify_port(device["port"], device["usb_serial"])
        if role == "cart":
            from takeone.adapters.uart import MotorUART

            cart = MotorUART(
                device["port"],
                baudrate=device["baudrate"],
                timeout=cart_timing.write_timeout_s,
                write_timeout=cart_timing.write_timeout_s,
            )
            cart.connect()
            return cart
        from takeone.adapters.lerobot_arm import openable_arm

        return openable_arm(device, self.mappings[role], arm_timing.io_limit_s)
