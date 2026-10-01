"""Deadline-based finite cart playback. No background keepalive and no hardware imports."""

import math
import statistics
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass

from takeone.clock import clock_info, monotonic
from takeone.config import finite, read_json, rig_config
from takeone.paths import CONFIGS
from takeone.protocol import MIN_COMMAND, uart_pair


@contextmanager
def host_timing_priority(enabled=True):
    """Temporarily favor the dedicated runner without using real-time priority."""
    status = {
        "requested": bool(enabled),
        "applied": False,
        "platform": sys.platform,
        "process_class": None,
        "thread_level": None,
    }
    if not enabled or sys.platform != "win32":
        yield status
        return

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentThread.argtypes = []
    kernel32.GetCurrentThread.restype = wintypes.HANDLE
    kernel32.GetPriorityClass.argtypes = [wintypes.HANDLE]
    kernel32.GetPriorityClass.restype = wintypes.DWORD
    kernel32.GetThreadPriority.argtypes = [wintypes.HANDLE]
    kernel32.GetThreadPriority.restype = ctypes.c_int
    kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.SetPriorityClass.restype = wintypes.BOOL
    kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
    kernel32.SetThreadPriority.restype = wintypes.BOOL
    process = kernel32.GetCurrentProcess()
    thread = kernel32.GetCurrentThread()
    original_process = kernel32.GetPriorityClass(process)
    original_thread = kernel32.GetThreadPriority(thread)
    if not original_process or original_thread == 0x7FFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())

    above_normal_priority_class = 0x00008000
    thread_priority_highest = 2
    process_changed = False
    thread_changed = False
    try:
        if not kernel32.SetPriorityClass(process, above_normal_priority_class):
            raise ctypes.WinError(ctypes.get_last_error())
        process_changed = True
        if not kernel32.SetThreadPriority(thread, thread_priority_highest):
            raise ctypes.WinError(ctypes.get_last_error())
        thread_changed = True
        status.update(applied=True, process_class="above_normal", thread_level="highest")
        yield status
    finally:
        errors = []
        if thread_changed and not kernel32.SetThreadPriority(thread, original_thread):
            errors.append("thread: " + str(ctypes.WinError(ctypes.get_last_error())))
        if process_changed and not kernel32.SetPriorityClass(process, original_process):
            errors.append("process: " + str(ctypes.WinError(ctypes.get_last_error())))
        status["restored"] = not errors
        if errors:
            raise OSError("Unable to restore host priority: " + "; ".join(errors))


@dataclass(frozen=True)
class Timing:
    period_s: float
    wake_guard_s: float
    lateness_limit_s: float
    host_gap_limit_s: float
    write_timeout_s: float
    watchdog_s: float
    zero_duration_s: float

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            if finite(getattr(self, name), name) <= 0:
                raise ValueError("Timing values must be positive")
        if (
            not self.period_s + self.lateness_limit_s + self.write_timeout_s
            < self.host_gap_limit_s
            < self.watchdog_s
        ):
            raise ValueError(
                "No watchdog margin: period + lateness + write must be below host gap < watchdog"
            )
        if self.wake_guard_s > self.lateness_limit_s or self.wake_guard_s >= self.period_s:
            raise ValueError("Wake guard must not exceed lateness and must be shorter than the period")
        if self.zero_duration_s < self.watchdog_s:
            raise ValueError("Zero-command window must cover at least one firmware watchdog interval")

    @classmethod
    def load(cls):
        config = read_json(CONFIGS / "cart-runtime.json")
        return cls(**{key: config[key] for key in cls.__dataclass_fields__})


def check_commissioning(plan):
    """First live-test envelope, deliberately narrower than the general planner."""
    config = read_json(CONFIGS / "cart-runtime.json")
    if config["commissioning_equal_commands_only"] is not True:
        raise ValueError("Broader hardware motion requires a reviewed measured-response workflow")
    reversed_motion = rig_config()["cart"]["reverse_enabled"]
    direction = "reverse" if reversed_motion else "forward"
    direction_sign = -1 if reversed_motion else 1
    cap = finite(config["commissioning_max_command"], "Commissioning command cap")
    duration = finite(config["commissioning_max_duration_s"], "Commissioning duration")
    if not MIN_COMMAND <= cap <= 0.05 or not 0 < duration <= 4:
        raise ValueError("Commissioning envelope exceeds the authorized 0.05 command or four-second limit")
    if plan.duration_s > duration:
        raise ValueError(f"Commissioning allows at most {duration:g} seconds; prepare a shorter shot")
    for left, right in plan.commands:
        if left != right or (left != 0.0 and not MIN_COMMAND <= direction_sign * left <= cap):
            raise ValueError(f"Commissioning permits only zero or equal {direction} commands up to {cap:g}")
        if float(uart_pair(left, right).split(",")[0]) != left:
            raise ValueError("Commissioning requires exact two-decimal wire commands")
        if abs(left) > MIN_COMMAND and plan.duration_s > 2.0:
            raise ValueError("The increased-command commissioning test is limited to two seconds")
    return {
        "direction": direction,
        "max_command_magnitude": cap,
        "max_duration_s": duration,
        "max_duration_above_minimum_command_s": 2.0,
        "equal_commands_only": True,
        "physical_straightness_verified": False,
    }


class CartRunner:
    """One owner; absolute deadlines; never replay overdue nonzero commands after a stall.

    The transport must bound its write duration. Python and host timestamps do not
    guarantee firmware reception. The user's firmware watchdog is the independent
    no-packet brake mechanism, not a reason to silently resume after a deadline miss.
    """

    def __init__(
        self,
        transport,
        timing,
        clock=monotonic,
        sleep=time.sleep,
        cancelled=lambda: False,
        guard=lambda: None,
        heartbeat=lambda: None,
    ):
        self.transport, self.timing = transport, timing
        self.clock, self.sleep, self.cancelled = clock, sleep, cancelled
        self.guard, self.heartbeat = guard, heartbeat
        self.events = []
        self.last_clock = None
        self.last_write = None
        self.last_command = None
        self.used = False
        self.fault = None
        self.wall_duration_s = None
        self.cpu_duration_s = None

    def now(self):
        stamp = finite(self.clock(), "Monotonic time")
        if self.last_clock is not None and stamp < self.last_clock:
            raise RuntimeError("Monotonic clock moved backwards")
        self.last_clock = stamp
        return stamp

    def wait_until(self, deadline, interruptible=True):
        while True:
            if interruptible and self.cancelled():
                raise InterruptedError("Operator cancelled cart run")
            remaining = deadline - self.now()
            if remaining <= 1e-9:
                return
            # Wake early so a normal Windows timer overshoot does not consume the
            # dispatch budget. Absolute deadlines still expose a real host stall.
            if remaining > self.timing.wake_guard_s + 1e-9:
                self.sleep(remaining - self.timing.wake_guard_s)
            else:
                # Yield during the guard too. A 10 ms spin at 50 Hz consumed
                # almost half a core and competed with vision and arm workers.
                self.sleep(min(remaining, 0.001))

    def send(self, command, deadline, phase, enforce=True):
        if enforce:
            self.guard()
        started = self.now()
        lateness = max(0.0, started - deadline)
        gap = None if self.last_write is None else started - self.last_write
        # Repeating an already-established zero does not replay stale motion.
        # Keep the host gap bound, and enforce the tighter phase deadline for
        # every moving command and every transition from motion to zero.
        stationary_zero = tuple(command) == (0.0, 0.0) and self.last_command == (0.0, 0.0)
        if enforce and (
            (lateness > self.timing.lateness_limit_s and not stationary_zero)
            or (gap is not None and gap > self.timing.host_gap_limit_s)
        ):
            self.events.append(
                dict(
                    phase=phase,
                    deadline_s=deadline,
                    observed_s=started,
                    lateness_s=lateness,
                    host_gap_s=gap,
                    dispatch_rejected=True,
                    error="Cart dispatch deadline missed",
                )
            )
            raise RuntimeError("Cart dispatch deadline missed; aborting without catch-up commands")
        event = dict(
            phase=phase,
            deadline_s=deadline,
            write_start_s=started,
            lateness_s=lateness,
            host_gap_s=gap,
            requested_wire=uart_pair(*command),
            expected_wire=uart_pair(*(v * getattr(self.transport, "polarity", 1) or 0.0 for v in command)),
            source="host transport attempt",
            firmware_receipt_verified=False,
            physical_motion_verified=False,
            stationary_zero=stationary_zero,
        )
        self.events.append(event)
        try:
            packet = self.transport.set_speed(*command)
        except BaseException as error:
            event["error"] = type(error).__name__ + ": " + str(error)
            raise
        completed = self.now()
        self.last_write = started
        self.last_command = tuple(command)
        event.update(write_end_s=completed, write_duration_s=completed - started, wire=packet)
        if packet != event["expected_wire"]:
            raise RuntimeError("Transport returned a different motor packet")
        if enforce and completed - started > self.timing.write_timeout_s + 1e-9:
            raise RuntimeError("Cart write exceeded its deadline; delivery timing unknown")
        self.heartbeat()

    def zero_window(self, phase, strict):
        epoch = self.now()
        end = epoch + self.timing.zero_duration_s
        index = 0
        while True:
            deadline = min(end, epoch + index * self.timing.period_s)
            self.wait_until(deadline, interruptible=strict)
            self.send((0.0, 0.0), deadline, phase, enforce=strict)
            if self.now() >= end - 1e-9:
                break
            # Even during shutdown do not burst queued writes after a host stall.
            index = max(index + 1, math.floor((self.now() - epoch) / self.timing.period_s) + 1)

    def run(self, plan, start_epoch=None):
        if self.used:
            raise RuntimeError("Runner is single-use; no automatic replay or fault restart")
        self.used = True
        if not self.transport.connected:
            raise RuntimeError("Cart transport must be explicitly connected")
        wall_start, cpu_start = monotonic(), time.process_time()
        try:
            self.zero_window("startup_zero", strict=True)
            epoch = self.now() if start_epoch is None else start_epoch(self)
            while self.now() < epoch - 1e-9:
                due = min(epoch, self.now() + self.timing.period_s)
                self.wait_until(due)
                if due < epoch:
                    self.send((0.0, 0.0), due, "armed_zero")
            for index, start in enumerate(plan.times_s):
                end = plan.times_s[index + 1] if index + 1 < len(plan.times_s) else plan.duration_s
                tick = 0
                while True:
                    due = start + tick * self.timing.period_s
                    self.wait_until(epoch + due)
                    # Preserve each compiled command boundary. The simulator may use
                    # a slightly shorter step than 20 ms to end exactly on duration.
                    # Avoid choosing the previous sample due to float cancellation.
                    elapsed = max(due, self.now() - epoch)
                    self.send(plan.command_at(elapsed), epoch + due, "motion")
                    tick += 1
                    if start + tick * self.timing.period_s >= end - 1e-9:
                        break
        except BaseException as error:
            self.fault = type(error).__name__ + ": " + str(error)
            raise
        finally:
            try:
                self.zero_window("shutdown_zero", strict=False)
            except BaseException as error:
                self.events.append(
                    {"phase": "shutdown_zero", "error": type(error).__name__ + ": " + str(error)}
                )
                if self.fault is None:
                    self.fault = "Shutdown zero delivery failed"
                    raise
            finally:
                self.wall_duration_s = monotonic() - wall_start
                self.cpu_duration_s = time.process_time() - cpu_start

    def report(self):
        writes = [e for e in self.events if "write_end_s" in e]
        dispatches = [e for e in self.events if "lateness_s" in e]
        gaps = [e["host_gap_s"] for e in dispatches if e["host_gap_s"] is not None]
        lateness = [e["lateness_s"] for e in dispatches]
        percentiles = statistics.quantiles(lateness, n=100, method="inclusive") if len(lateness) > 1 else None
        return dict(
            fault=self.fault,
            writes_completed=len(writes),
            max_host_gap_s=max(gaps, default=0),
            max_lateness_s=max((e["lateness_s"] for e in dispatches), default=0),
            max_write_duration_s=max((e["write_duration_s"] for e in writes), default=0),
            p99_lateness_s=percentiles[98] if percentiles else None,
            wall_duration_s=self.wall_duration_s,
            cpu_duration_s=self.cpu_duration_s,
            cpu_percent_one_core=(
                100 * self.cpu_duration_s / self.wall_duration_s if self.wall_duration_s else None
            ),
            rejected_dispatches=sum(e.get("dispatch_rejected", False) for e in self.events),
            dispatch_clock=clock_info() if self.clock is monotonic else {"function": "injected_clock"},
            timing_scope="host write timing only, not firmware reception or actual braking",
            physical_stop_confirmed=False,
            events=self.events,
        )
