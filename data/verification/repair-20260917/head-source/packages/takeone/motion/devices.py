"""Physical device composition. Each child process owns one real serial bus."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceFactory:
    devices: dict
    mappings: dict
    execution_mode: str = "qualified"
    simulated = False

    def open(self, role, plan, arm_timing, cart_timing):
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
