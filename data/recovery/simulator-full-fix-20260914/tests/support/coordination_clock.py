"""Cooperative virtual time for real spawned coordination workers, not host qualification."""

import json
import math
import multiprocessing
import os
from contextlib import ExitStack
from dataclasses import dataclass, replace
from functools import partial
from types import SimpleNamespace
from unittest.mock import patch

from takeone import execution
from takeone.cart.runtime import CartRunner
from takeone.motion.arm import ArmRunner

from tests.support.devices import SimulatedArm, SimulatedCart

ACTORS = ("supervisor", "cart", "phone", "light")


class Scheduler:
    def __init__(self, context):
        self.condition = context.Condition()
        self.stamp = context.Value("d", 100.0, lock=False)
        self.turn = context.Value("i", 0, lock=False)
        self.due = context.Array("d", [math.inf, 100.0, 100.0, 100.0], lock=False)
        self.finished = context.Array("b", [False] * 4, lock=False)
        self.aborted = context.Value("b", False, lock=False)

    def await_turn(self, actor):
        if not self.condition.wait_for(lambda: self.turn.value == actor or self.aborted.value, timeout=10):
            self.aborted.value = True
            self.condition.notify_all()
        if self.aborted.value:
            raise AssertionError("Coordination fixture stalled in real time")

    def advance(self):
        candidates = [i for i in range(4) if not self.finished[i]]
        if candidates:
            actor = min(candidates, key=lambda i: (self.due[i], i))
            if not math.isfinite(self.due[actor]):
                raise AssertionError("Coordination fixture has no scheduled wakeup")
            self.stamp.value = max(self.stamp.value, self.due[actor])
            self.due[actor] = math.inf
            self.turn.value = actor
        self.condition.notify_all()


class Clock:
    def __init__(self, scheduler, actor, scenario="healthy", shared=None):
        self.scheduler, self.actor = scheduler, actor
        self.scenario, self.shared = scenario, shared
        self.events = []
        self.delayed = False

    def enter(self):
        with self.scheduler.condition:
            self.scheduler.await_turn(self.actor)

    def now(self):
        return self.scheduler.stamp.value

    def sleep(self, seconds):
        if (
            self.scenario == "late_cart"
            and self.actor == ACTORS.index("cart")
            and not self.delayed
            and self.shared.epoch.value >= 0
            and self.now() >= self.shared.epoch.value
        ):
            self.delayed = True
            self.events.append(dict(event="dispatch_stall", at=self.now(), duration_s=0.025))
            seconds += 0.025
        with self.scheduler.condition:
            if self.scheduler.turn.value != self.actor:
                raise AssertionError("Clock advanced outside the actor's scheduled turn")
            self.scheduler.due[self.actor] = self.now() + seconds
            self.scheduler.advance()
            self.scheduler.await_turn(self.actor)

    def finish(self):
        with self.scheduler.condition:
            self.scheduler.finished[self.actor] = True
            self.scheduler.advance()


class BlockingArm(SimulatedArm):
    def __init__(self, initial, clock):
        super().__init__(initial, clock.now)
        self.test_clock = clock
        self.blocked = False

    def read(self):
        if any(self.goal) and not self.blocked:
            self.blocked = True
            self.test_clock.events.append(dict(event="read_blocked", at=self.test_clock.now()))
            self.test_clock.sleep(0.4)
            self.test_clock.events.append(dict(event="read_released", at=self.test_clock.now()))
        return super().read()


class SlowCart(SimulatedCart):
    def __init__(self, clock):
        self.clock = clock
        self.delayed = False

    def set_speed(self, left, right):
        if not self.delayed:
            self.delayed = True
            self.clock.events.append(dict(event="write_stall", at=self.clock.now(), duration_s=0.006))
            self.clock.sleep(0.006)
        return super().set_speed(left, right)


@dataclass(frozen=True)
class ClockedFactory:
    scenario: str = "healthy"
    clock: object = None
    simulated: bool = True

    def open(self, role, plan, arm_timing, cart_timing):
        if role == "cart":
            return SlowCart(self.clock) if self.scenario == "slow_write" else SimulatedCart()
        if role == "phone" and self.scenario == "blocked_phone":
            return BlockingArm(plan.arm_at(role, 0), self.clock)
        return SimulatedArm(plan.arm_at(role, 0), self.clock.now)


def scheduled_worker(target, arguments, scheduler, actor):
    shared, folder = arguments[-2:]
    clock = Clock(scheduler, actor, arguments[2].scenario, shared)
    clock.enter()
    try:
        with ExitStack() as patches:
            patches.enter_context(
                patch.object(
                    execution,
                    "time",
                    SimpleNamespace(
                        monotonic=clock.now,
                        sleep=clock.sleep,
                    ),
                )
            )
            patches.enter_context(
                patch.object(
                    execution,
                    "ArmRunner",
                    partial(
                        ArmRunner,
                        clock=clock.now,
                        sleep=clock.sleep,
                    ),
                )
            )
            patches.enter_context(
                patch.object(
                    execution,
                    "CartRunner",
                    partial(
                        CartRunner,
                        clock=clock.now,
                        sleep=clock.sleep,
                    ),
                )
            )
            arguments = (*arguments[:2], replace(arguments[2], clock=clock), *arguments[3:])
            target(*arguments)
    finally:
        (folder / f"clock-{ACTORS[actor]}.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "epoch": shared.epoch.value,
                    "events": clock.events,
                    "cancelled": shared.cancel.is_set(),
                }
            )
        )
        clock.finish()


class ScheduledProcess:
    def __init__(self, process, scheduler, actor):
        self.process, self.scheduler, self.actor = process, scheduler, actor

    def __getattr__(self, name):
        return getattr(self.process, name)

    def is_alive(self):
        if self.scheduler.finished[self.actor]:
            self.process.join(timeout=5)
        return self.process.is_alive()


class ScheduledContext:
    def __init__(self, context, scheduler):
        self.context, self.scheduler = context, scheduler
        self.processes = []

    def __getattr__(self, name):
        return getattr(self.context, name)

    def Process(self, *, name, target, args):
        actor = ACTORS.index(args[0])
        process = self.context.Process(
            name=name, target=scheduled_worker, args=(target, args, self.scheduler, actor)
        )
        self.processes.append(process)
        return ScheduledProcess(process, self.scheduler, actor)

    def get_context(self, method):
        if method != "spawn":
            raise AssertionError("Coordination must retain independent spawned workers")
        return self


def run_coordinated(plan, limits, folder, scenario="healthy"):
    context = multiprocessing.get_context("spawn")
    scheduler = Scheduler(context)
    wrapped = ScheduledContext(context, scheduler)
    clock = Clock(scheduler, 0)
    try:
        with (
            patch.object(execution, "multiprocessing", wrapped),
            patch.object(execution, "time", SimpleNamespace(monotonic=clock.now, sleep=clock.sleep)),
        ):
            result = execution.RobotRunner(plan, ClockedFactory(scenario), limits).run(folder)
    finally:
        for process in wrapped.processes:
            try:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                process.close()
            except ValueError:
                pass
    evidence = {role: json.loads((folder / f"clock-{role}.json").read_text()) for role in ACTORS[1:]}
    return result, evidence
