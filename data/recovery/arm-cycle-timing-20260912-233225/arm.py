"""One arm owner, bounded trajectory dispatch and encoder tracking checks."""

import math
import time
from collections import deque
from dataclasses import asdict

from takeone.clock import monotonic
from takeone.config import finite


class ArmRunner:
    def __init__(
        self,
        adapter,
        role,
        plan,
        limits,
        timing,
        *,
        clock=monotonic,
        sleep=time.sleep,
        guard=lambda: None,
        heartbeat=lambda: None,
    ):
        self.adapter, self.role, self.plan = adapter, role, plan
        self.limits, self.timing = limits, timing
        self.clock, self.sleep, self.guard, self.heartbeat = clock, sleep, guard, heartbeat
        self.events = []
        self.last_observation = None
        self.last_clock = None
        self.last_goal = None
        self.used = False
        self.fault = None
        self.settled = False
        self.activated = False
        self.terminal_samples = deque(maxlen=250)
        self.terminal_count = 0
        self.terminal_max_error = [0.0] * 5

    def now(self):
        stamp = finite(self.clock(), "Monotonic clock")
        if self.last_clock is not None and stamp < self.last_clock:
            raise RuntimeError("Monotonic clock regressed")
        self.last_clock = stamp
        return stamp

    def wait(self, deadline):
        while True:
            self.guard()
            remaining = deadline - self.now()
            if remaining <= 1e-9:
                return
            self.sleep(min(remaining, self.timing.period_s / 4))

    def observe(self):
        self.guard()
        started = self.now()
        observation = self.adapter.read()
        completed = self.now()
        if completed - started > self.timing.io_limit_s:
            raise RuntimeError(f"{self.role}: encoder read exceeded IO budget")
        if not 0 <= completed - observation.captured_monotonic_s <= self.timing.feedback_age_s:
            raise ValueError(f"{self.role}: stale or future encoder feedback")
        if (
            self.last_observation
            and observation.captured_monotonic_s <= self.last_observation.captured_monotonic_s
        ):
            raise ValueError(f"{self.role}: repeated or reversed encoder timestamp")
        expected_source = "simulated" if self.adapter.simulated else "measured"
        if observation.source != expected_source:
            raise ValueError(f"{self.role}: feedback source mismatch")
        if not self.adapter.simulated and (
            observation.acquisition_start_s is None or observation.raw_positions is None
        ):
            raise ValueError(f"{self.role}: actual raw feedback and acquisition interval required")
        self.adapter.validate(observation.q_rad)
        self.last_observation = observation
        return observation

    def compare(self, observation, target, tolerance, phase):
        errors = tuple(abs(a - b) for a, b in zip(observation.q_rad, target))
        self.events.append(
            dict(
                phase=phase,
                captured_monotonic_s=observation.captured_monotonic_s,
                expected_rad=target,
                observed_rad=observation.q_rad,
                error_rad=errors,
                source=observation.source,
                acquisition_start_s=observation.acquisition_start_s,
                acquisition_end_s=observation.acquisition_end_s,
                raw_positions=observation.raw_positions,
                health_raw=observation.health_raw,
            )
        )
        return all(error <= limit for error, limit in zip(errors, tolerance))

    def ready(self):
        observation = self.observe()
        if not self.compare(
            observation, self.plan.arm_at(self.role, 0), self.limits.initial_tolerance_rad, "ready"
        ):
            raise ValueError(f"{self.role}: starting pose mismatch; no automatic positioning")
        if not self.activated:
            if not self.adapter.simulated:
                self.adapter.activate(observation, self.limits.initial_tolerance_rad)
            self.activated = True
            self.last_goal = observation.q_rad
        self.heartbeat()

    def send(self, target, deadline):
        self.guard()
        started = self.now()
        if started - deadline > self.timing.lateness_limit_s:
            raise RuntimeError(f"{self.role}: dispatch deadline missed; no catch-up")
        previous = self.last_goal if self.last_goal is not None else self.last_observation.q_rad
        if any(abs(a - b) > cap for a, b, cap in zip(previous, target, self.limits.step_rad)):
            raise ValueError(f"{self.role}: command step exceeded")
        self.adapter.validate(target)
        receipt = self.adapter.command(target)
        completed = self.now()
        self.events.append(
            dict(
                phase="command",
                deadline_s=deadline,
                write_start_s=started,
                write_end_s=completed,
                q_rad=target,
                source="simulated" if self.adapter.simulated else "transmitted_not_measured",
                receipt=receipt,
            )
        )
        self.last_goal = target
        if completed - started > self.timing.io_limit_s:
            raise RuntimeError(f"{self.role}: command exceeded IO budget")
        self.guard()
        self.heartbeat()

    def run(self, epoch):
        if self.used:
            raise RuntimeError("Arm runner is single-use")
        self.used = True
        try:
            for elapsed in self.plan.dispatch_times(self.timing.period_s):
                deadline = epoch + elapsed
                self.wait(deadline)
                cycle_started = self.now()
                observation = self.observe()
                expected = self.plan.arm_at(self.role, observation.captured_monotonic_s - epoch)
                if not self.compare(observation, expected, self.limits.tracking_tolerance_rad, "tracking"):
                    raise RuntimeError(f"{self.role}: measured tracking error exceeded tolerance")
                self.send(self.plan.arm_at(self.role, elapsed), deadline)
                cycle_completed = self.now()
                self.events.append(
                    dict(
                        phase="cycle",
                        start_s=cycle_started,
                        end_s=cycle_completed,
                        duration_s=cycle_completed - cycle_started,
                    )
                )
                if cycle_completed - cycle_started > self.timing.io_limit_s:
                    raise RuntimeError(f"{self.role}: complete read/write cycle exceeded IO budget")
            end = epoch + self.plan.duration_s
            stable_since = None
            tick = 1
            while self.now() < end + self.timing.settle_timeout_s:
                self.wait(end + tick * self.timing.period_s)
                tick += 1
                observation = self.observe()
                target = self.plan.arm_at(self.role, self.plan.duration_s)
                if not self.compare(observation, target, self.limits.tracking_tolerance_rad, "settling"):
                    raise RuntimeError(f"{self.role}: terminal tracking error exceeded tolerance")
                inside = all(
                    abs(a - b) <= cap
                    for a, b, cap in zip(
                        observation.q_rad,
                        target,
                        self.limits.final_tolerance_rad,
                    )
                )
                if inside:
                    if stable_since is None:
                        stable_since = observation.captured_monotonic_s
                    if observation.captured_monotonic_s - stable_since >= self.timing.settle_duration_s:
                        self.settled = True
                        self.heartbeat()
                        return
                else:
                    stable_since = None
                self.heartbeat()
            raise RuntimeError(f"{self.role}: final pose did not settle within the deadline")
        except BaseException as error:
            self.fault = type(error).__name__ + ": " + str(error)
            raise

    def hold_on_fault(self):
        """Best effort at a fresh measured pose; never disable a loaded arm's torque."""
        observation = self.last_observation
        if observation and 0 <= self.clock() - observation.captured_monotonic_s <= self.timing.feedback_age_s:
            try:
                if self.last_goal is not None and any(
                    abs(a - b) > cap
                    for a, b, cap in zip(observation.q_rad, self.last_goal, self.limits.step_rad)
                ):
                    raise ValueError("Fresh-pose stop would exceed the measured command-step envelope")
                self.adapter.hold(observation)
                self.last_goal = observation.q_rad
                self.events.append(dict(phase="fault_hold", source="hold_requested_not_confirmed"))
                return
            except Exception as error:
                self.events.append(dict(phase="fault_hold", error=str(error)))
        self.events.append(dict(phase="fault_hold", source="last_goal_retained_stop_unconfirmed"))

    def monitor_hold(self):
        """Read only; never adopt a new position as the hold target."""
        observation = self.observe()
        target = self.last_goal
        if target is None:
            raise RuntimeError("No established target to monitor")
        errors = [abs(a - b) for a, b in zip(observation.q_rad, target)]
        self.terminal_count += 1
        self.terminal_max_error = [max(a, b) for a, b in zip(self.terminal_max_error, errors)]
        self.terminal_samples.append(
            dict(
                captured_monotonic_s=observation.captured_monotonic_s,
                raw_positions=observation.raw_positions,
                error_rad=errors,
                health_raw=observation.health_raw,
            )
        )
        if any(e > cap for e, cap in zip(errors, self.limits.tracking_tolerance_rad)):
            raise RuntimeError(f"{self.role}: retained hold drift exceeded measured tolerance")
        self.heartbeat()

    def report(self):
        tracking = [e for e in self.events if e["phase"] in ("tracking", "settling")]
        return dict(
            role=self.role,
            measured_limits=asdict(self.limits)
            if not self.adapter.simulated and self.limits.basis == "measured"
            else None,
            command_policy=asdict(self.limits),
            fault=self.fault,
            settled=self.settled,
            max_error_rad=[max((e["error_rad"][j] for e in tracking), default=None) for j in range(5)],
            rms_error_rad=[
                math.sqrt(sum(e["error_rad"][j] ** 2 for e in tracking) / len(tracking)) if tracking else None
                for j in range(5)
            ],
            maximum_sample_gap_s=max(
                (
                    b["captured_monotonic_s"] - a["captured_monotonic_s"]
                    for a, b in zip(tracking, tracking[1:])
                ),
                default=None,
            ),
            maximum_cycle_s=max(
                (e["duration_s"] for e in self.events if e["phase"] == "cycle"), default=None
            ),
            command_count=sum(e["phase"] == "command" for e in self.events),
            feedback_source="simulated" if self.adapter.simulated else "measured",
            physical_tracking_verified=not self.adapter.simulated and self.settled and self.fault is None,
            tracking_scope="sampled joint encoders; not camera pose, cart odometry or physical stopping",
            activation=getattr(self.adapter, "lifecycle", {}),
            last_command_attempt=getattr(self.adapter, "last_command_attempt", None),
            terminal_hold=dict(
                samples=list(self.terminal_samples),
                sample_count=self.terminal_count,
                max_error_rad=self.terminal_max_error if self.terminal_count else None,
                samples_retained_limit=250,
            ),
            events=self.events,
        )
