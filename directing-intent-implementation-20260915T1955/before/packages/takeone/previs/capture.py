"""Editorial windows from one continuous compiled take; never a second motor plan."""

import copy
import math


def window(preview, start_s, duration_s, include_setup):
    setup = preview["orbit_start_s"]
    end = start_s + duration_s
    if start_s < 0 or duration_s <= 0 or end > preview["orbit_duration_s"] + 1e-8:
        raise ValueError("A shared take window must fit its compiled filming duration.")
    begin = 0.0 if include_setup else setup + start_s
    stop = setup + end
    source = preview["frames"]

    def boundary(stamp):
        # Retain a real FK sample at an editorial boundary, with no new solve
        # or invented joint pose. Both sides of a shared cut use the same sample.
        frame = next((f for f in reversed(source) if f["time_s"] <= stamp + 1e-8), source[0])
        return dict(copy.deepcopy(frame), time_s=stamp - begin)

    frames = (
        [boundary(begin)]
        + [
            dict(copy.deepcopy(f), time_s=f["time_s"] - begin)
            for f in source
            if begin + 1e-8 < f["time_s"] < stop - 1e-8
        ]
        + [boundary(stop)]
    )
    result = copy.deepcopy(preview)
    result.update(
        frames=frames,
        duration_s=stop - begin,
        orbit_start_s=setup if include_setup else 0.0,
        orbit_duration_s=duration_s,
        source_in_s=start_s,
        source_duration_s=preview["orbit_duration_s"],
    )
    distance = sum(math.dist(a["axle_m"], b["axle_m"]) for a, b in zip(frames, frames[1:]))
    result["summary"].update(
        duration_s=stop - begin,
        setup_duration_s=result["orbit_start_s"],
        orbit_duration_s=duration_s,
        distance_m=distance,
        average_speed_m_s=distance / duration_s,
    )
    return result
