"""Shared wire contract for simulation and cart UART. Commands are not watts."""

from .config import finite, rig_config

_cart = rig_config()["cart"]
COMMAND_CAP = _cart["command_cap"]
MIN_COMMAND = _cart["minimum_command"]


def uart_pair(left, right):
    values = [max(-COMMAND_CAP, min(COMMAND_CAP, finite(v, "Motor command"))) for v in (left, right)]
    return f"{values[0]:.2f},{values[1]:.2f}\n"
