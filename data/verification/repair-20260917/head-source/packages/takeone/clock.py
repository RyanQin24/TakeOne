"""One high-resolution, system-wide monotonic clock for robot execution.

Windows Python 3.12 can implement time.monotonic with 15.625 ms GetTickCount64
ticks. perf_counter uses QueryPerformanceCounter there and is system-wide on
supported Python versions. All motion timestamps, leases and deadlines must use
this same clock domain. Virtual replay continues to inject its own clock.
"""

import time


def monotonic():
    return time.perf_counter()


def clock_info():
    info = time.get_clock_info("perf_counter")
    return dict(
        function="time.perf_counter",
        implementation=info.implementation,
        resolution_s=info.resolution,
        monotonic=info.monotonic,
        adjustable=info.adjustable,
    )
