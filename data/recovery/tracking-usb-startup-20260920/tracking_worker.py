"""Execute byte-preserved scripts with UI lifetime and optional arm IO adapters."""

import argparse
import builtins
import importlib
import importlib.util
import json
import os
import sys
import threading
import time
from types import SimpleNamespace

from takeone.motion.dshow_camera import DirectShowCamera
from takeone.motion.srt_camera import SrtCamera
from takeone.motion.studio_worker import BrowserControl, device_ownership
from takeone.motion.tracking import STOP_GRACE_S, camera_settings, source_path


class TrackingStopped(BaseException):
    """Unwind script initialization or its loop without changing tracking maths."""


class Proxy:
    def __init__(self, wrapped, **overrides):
        self.wrapped, self.overrides = wrapped, overrides

    def __getattr__(self, name):
        return self.overrides[name] if name in self.overrides else getattr(self.wrapped, name)


class TrackingIO:
    def __init__(
        self,
        stop,
        *,
        arms_enabled,
        sdk,
        cv2,
        motor_class,
        camera_config=None,
        numpy=None,
        phone=None,
        srt_factory=SrtCamera,
        dshow_factory=DirectShowCamera,
        emit=lambda event: None,
        identity_check=lambda port: None,
    ):
        self.stop = stop
        self.arms_enabled = arms_enabled
        self.sdk, self.cv2, self.motor_class = sdk, cv2, motor_class
        self.camera_config = camera_config
        self.numpy, self.phone, self.srt_factory = numpy, phone, srt_factory
        self.dshow_factory = dshow_factory
        self.emit, self.identity_check = emit, identity_check
        self.ports, self.cameras, self.carts = [], [], []
        self.cart_lock = threading.RLock()
        self.running = False
        self.scope = None
        self.arm_goal_notices = {}

    def check(self):
        if self.stop.is_set():
            raise TrackingStopped()

    def port(self, name):
        self.check()
        owner = self

        class Port:
            def __init__(self):
                self.name = name
                self.raw = owner.sdk.PortHandler(name) if owner.arms_enabled else None
                self.checked = False
                owner.ports.append(self)

            def openPort(self):
                owner.check()
                if self.raw is None:
                    return True
                if not self.checked:
                    owner.identity_check(name)
                    self.checked = True
                try:
                    return self.raw.openPort()
                except Exception as error:
                    raise RuntimeError(f"Could not open tracking arm port {name}: {error}") from error

            def setBaudRate(self, baudrate):
                owner.check()
                if self.raw is None:
                    return True
                # scservo_sdk.openPort() already applies its default 1 Mbps rate.
                # Calling setBaudRate(1 Mbps) again closes and immediately reopens
                # the USB port, which can fail on Windows even though the first
                # open succeeded.
                if self.raw.is_open and self.raw.getBaudRate() == baudrate:
                    return True
                try:
                    return self.raw.setBaudRate(baudrate)
                except Exception as error:
                    raise RuntimeError(
                        f"Could not set tracking arm port {name} to {baudrate} baud: {error}"
                    ) from error

            def closePort(self):
                if self.raw is not None and getattr(self.raw, "is_open", False):
                    self.raw.closePort()

            def __getattr__(self, key):
                return getattr(self.raw, key)

        return Port()

    def servo(self, port):
        owner = self
        raw = self.sdk.sms_sts(port) if self.arms_enabled else None

        class Servo:
            def write1ByteTxRx(self, *args):
                owner.check()
                return raw.write1ByteTxRx(*args) if raw is not None else (0, 0)

            def write2ByteTxRx(self, *args):
                owner.check()
                result = raw.write2ByteTxRx(*args) if raw is not None else (0, 0)
                if raw is not None and len(args) >= 3 and args[1] == 42 and args[0] == 1:
                    now = time.monotonic()
                    if now - owner.arm_goal_notices.get(port.name, 0.0) >= 0.5:
                        owner.emit(
                            dict(
                                event="arm_goal",
                                port=port.name,
                                motor_id=args[0],
                                goal_position=args[2],
                                result=list(result),
                            )
                        )
                        owner.arm_goal_notices[port.name] = now
                return result

        return Servo()

    def camera(self, *args, **kwargs):
        self.check()
        kind = self.camera_config.get("kind") if self.camera_config else None
        persistent = kind in ("blackmagic_srt", "directshow")

        def open_camera():
            if kind == "blackmagic_srt":
                return self.srt_factory(
                    self.camera_config,
                    cv2=self.cv2,
                    numpy=self.numpy,
                    phone=self.phone,
                    stop=self.stop,
                )
            if kind == "directshow":
                return self.dshow_factory(
                    self.camera_config,
                    cv2=self.cv2,
                    numpy=self.numpy,
                    stop=self.stop,
                )
            return self.cv2.VideoCapture(*args, **kwargs)

        last_notice = 0.0
        while True:
            self.check()
            try:
                raw = open_camera()
                if raw.isOpened():
                    break
                raw.release()
                error = RuntimeError("receiver did not stay open")
            except Exception as caught:
                error = caught
            if not persistent:
                label = self.camera_config["device_label"] if self.camera_config else args[0]
                raise RuntimeError(
                    f"Could not open the configured tracking camera: {label}: {error}"
                ) from error
            now = time.monotonic()
            if now - last_notice >= 2.0:
                self.emit(dict(phase="camera_waiting", detail=str(error)))
                last_notice = now
            if self.stop.wait(0.5):
                self.check()
        self.cameras.append(raw)
        if kind == "directshow" and self.scope is not None and "shoulder_target_px" in self.scope:
            target = self.camera_config["body_target"]
            width, height = self.camera_config["width"], self.camera_config["height"]
            self.scope["shoulder_target_px"] = (
                int(target["center_x_fraction"] * width + 0.5),
                int(target["center_y_fraction"] * height + 0.5),
            )
            self.scope["shoulder_size_px_target"] = int(target["shoulder_width_fraction"] * width + 0.5)
            self.scope["int_abs_error_start"] = max(1, int(target["start_deadband_fraction"] * width + 0.5))
            self.scope["int_abs_error_stop"] = max(1, int(target["stop_deadband_fraction"] * width + 0.5))
            self.scope["float_KPP"] = target["pan_gain_counts_per_normalized_error"] / width
            self.emit(
                dict(
                    event="body_target",
                    center_px=list(self.scope["shoulder_target_px"]),
                    shoulder_width_px=self.scope["shoulder_size_px_target"],
                    calibrated=target["calibrated"],
                )
            )
        waiting = False

        def read():
            nonlocal raw, waiting, last_notice
            while True:
                self.check()
                frame = raw.read()
                if frame[0]:
                    if not self.running or waiting:
                        self.running = True
                        waiting = False
                        self.emit(dict(phase="running"))
                    return frame
                if not persistent:
                    return frame

                # Never let a temporary camera gap terminate the preserved
                # tracking script. Stop the cart while vision is unavailable;
                # the arms simply retain their last goals.
                self.stop_cart()
                waiting = True
                now = time.monotonic()
                if now - last_notice >= 2.0:
                    self.emit(dict(phase="camera_waiting"))
                    last_notice = now
                if raw.isOpened():
                    if self.stop.wait(0.05):
                        self.check()
                    continue

                raw.release()
                while not self.stop.wait(0.5):
                    try:
                        replacement = open_camera()
                        if not replacement.isOpened():
                            replacement.release()
                            continue
                        raw = replacement
                        self.cameras.append(raw)
                        break
                    except Exception as error:
                        now = time.monotonic()
                        if now - last_notice >= 2.0:
                            self.emit(dict(phase="camera_waiting", detail=str(error)))
                            last_notice = now
                else:
                    self.check()

        return Proxy(raw, read=read)

    def wait_key(self, delay):
        return ord("q") if self.stop.is_set() else self.cv2.waitKey(delay)

    def cart(self, *args, **kwargs):
        self.check()
        owner = self
        raw = self.motor_class(*args, **kwargs)

        class Cart:
            def connect(self):
                with owner.cart_lock:
                    owner.check()
                    owner.identity_check(raw.port)
                    return raw.connect()

            def set_speed(self, left, right):
                with owner.cart_lock:
                    owner.check()
                    return raw.set_speed(left, right)

            def stop(self):
                with owner.cart_lock:
                    if raw.connected:
                        return raw.stop()

            def close(self):
                with owner.cart_lock:
                    if raw.connected:
                        raw.stop()
                        raw.close()

        cart = Cart()
        self.carts.append(cart)
        return cart

    def imports(self, original=builtins.__import__):
        modules = {
            "cv2": Proxy(self.cv2, VideoCapture=self.camera, waitKey=self.wait_key),
            "scservo_sdk": SimpleNamespace(PortHandler=self.port, sms_sts=self.servo, COMM_SUCCESS=0),
            "motor_UART": SimpleNamespace(MotorUART=self.cart),
        }

        def load(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and name in modules:
                return modules[name]
            return original(name, globals, locals, fromlist, level)

        return load

    def stop_cart(self):
        errors = []
        for cart in self.carts:
            try:
                cart.stop()
            except Exception as error:
                errors.append(str(error))
        return errors

    def cleanup(self):
        self.stop.set()
        errors = self.stop_cart()
        actions = [cart.close for cart in self.carts] + [port.closePort for port in self.ports]
        actions += [camera.release for camera in self.cameras] + [self.cv2.destroyAllWindows]
        for action in actions:
            try:
                action()
            except Exception as error:
                errors.append(str(error))
        return errors


def dependencies():
    """Import libraries only; never import a tracking script or construct IO."""
    return {
        name: importlib.import_module(name) for name in ("cv2", "mediapipe", "numpy", "serial", "scservo_sdk")
    }


def execute(mode, io):
    path = source_path(mode)
    scope = dict(
        __name__="__main__", __file__=str(path), __builtins__=dict(vars(builtins), __import__=io.imports())
    )
    completed = False
    try:
        io.scope = scope
        io.check()
        exec(compile(path.read_bytes(), str(path), "exec"), scope)
        completed = True
        if not io.running and not io.stop.is_set():
            raise RuntimeError("Tracking ended before the camera produced a frame")
    finally:
        # Original cleanup can be skipped by a startup failure, or the arm-only
        # script's lack of try/finally. The wrapper owns those resource lifetimes.
        if not completed and scope.get("detector") is not None:
            try:
                scope["detector"].close()
            except Exception:
                pass  # Some script paths already closed their detector.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("cart", "arms"), default="arms")
    parser.add_argument("--arms", action="store_true")
    parser.add_argument("--check", action="store_true", help="Import dependencies only; no camera or motors")
    args = parser.parse_args(argv)
    if args.check:
        modules = dependencies()
        for mode in ("cart", "arms"):
            source_path(mode)
        print(
            json.dumps(
                dict(
                    imports={
                        key: getattr(value, "__version__", "available") for key, value in modules.items()
                    },
                    hardware_opened=False,
                )
            )
        )
        return 0

    stop, finished = threading.Event(), threading.Event()
    control = BrowserControl(stop)
    io = None

    def emit(event):
        print(json.dumps(dict(event, source="tracking_worker")), flush=True)

    def read():
        try:
            for line in sys.stdin:
                control.receive(line)
        finally:
            control.receive("")

    def watch():
        stopped_at = None
        while not finished.wait(0.05):
            if control.expired():
                if stopped_at is None:
                    stopped_at = time.monotonic()
                    if io is not None:
                        threading.Thread(target=io.stop_cart, daemon=True).start()
                elif time.monotonic() - stopped_at > STOP_GRACE_S:
                    emit(
                        dict(
                            terminal=True,
                            phase="terminated",
                            cleanup_completed=False,
                            error="Tracking did not exit after Stop; hardware stop is unconfirmed.",
                        )
                    )
                    os._exit(2)

    threading.Thread(target=read, daemon=True).start()
    threading.Thread(target=watch, daemon=True).start()
    error = None
    phase = "stopped"
    cleanup_errors = []
    try:
        source_path(args.mode)
        modules = dependencies()
        from takeone.adapters.identity import identify_port
        from takeone.config import read_json
        from takeone.paths import CONFIGS
        from takeone.phone.client import BlackmagicCamera

        config = read_json(CONFIGS / "devices/windows.json")
        devices = [config["cart"], *config["arms"].values()]
        identities = {device["port"]: device["usb_serial"] for device in devices}

        def identity(port):
            if port not in identities:
                raise ValueError(f"Script port {port} does not match the configured devices")
            identify_port(port, identities[port])

        uart_path = source_path(args.mode).with_name("motor_UART.py")
        spec = importlib.util.spec_from_file_location("takeone_tracking_uart", uart_path)
        uart = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(uart)
        camera_config = camera_settings()
        phone = None
        if camera_config["kind"] == "blackmagic_srt":
            phone_config = read_json(CONFIGS / "iphone-camera.json")
            phone = BlackmagicCamera(
                phone_config["endpoint"],
                phone_config["timeout_s"],
                cert_sha256=phone_config.get("tls_cert_sha256", ""),
            )
        io = TrackingIO(
            stop,
            arms_enabled=args.arms or args.mode == "arms",
            sdk=modules["scservo_sdk"],
            cv2=modules["cv2"],
            motor_class=uart.MotorUART,
            camera_config=camera_config,
            numpy=modules["numpy"],
            phone=phone,
            emit=emit,
            identity_check=identity,
        )
        # Shares ownership with ordinary robot playback, even in another server.
        with device_ownership():
            try:
                emit(dict(phase="initializing"))
                execute(args.mode, io)
            finally:
                cleanup_errors = io.cleanup()
    except TrackingStopped:
        pass
    except BaseException as exc:
        phase, error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        finished.set()
        stop.set()
    if cleanup_errors:
        phase, error = "failed", "; ".join(cleanup_errors)
    emit(
        dict(terminal=True, phase=phase, error=error, cleanup_completed=io is not None and not cleanup_errors)
    )
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
