"""Read-only USB identity selection shared by cart and arm connections."""

import os


def identify_port(port, usb_serial):
    """Read host enumeration only; validate identity before opening a serial handle."""
    if not isinstance(usb_serial, str) or not usb_serial.strip():
        raise ValueError("A nonempty device USB serial is required")
    from serial.tools import list_ports

    if not isinstance(port, str) or not port.strip():
        raise ValueError("An explicit device port is required")
    requested = os.path.realpath(port).casefold()
    matches = [p for p in list_ports.comports() if os.path.realpath(p.device).casefold() == requested]
    if len(matches) != 1 or matches[0].serial_number != usb_serial:
        raise ValueError("Port/USB serial identity does not match; no connection attempted")
    return dict(
        port=matches[0].device, usb_serial=matches[0].serial_number, vid=matches[0].vid, pid=matches[0].pid
    )
