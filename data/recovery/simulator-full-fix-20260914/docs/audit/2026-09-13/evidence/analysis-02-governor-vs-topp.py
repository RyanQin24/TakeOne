"""Analysis 2: duration of every reference take and reposition phase under
(a) the governor bound Tree B actually uses (the plan's rehearsal_duration_s),
(b) a per-sample velocity-only bound  T_v  = integral ds / min_axis(v_lim / |q_s(s)|),
(c) a numerical time-optimal path parameterisation (TOPP) with the SAME per-axis velocity
    and acceleration limits (MotionLimits), integrated forward/backward in (s, sdot^2),
(d) (c) plus one jerk ramp (a_lim / j_lim) per acceleration reversal as a conservative
    jerk-inclusive estimate; the exact jerk-limited optimum lies between (c) and (a).

Input: C:\\TakeOne-audit-20260913\\out\\plan-run1.json (Tree B recompile of the reference timeline,
see analysis-tb-compile.py). Paths are rebuilt with Tree B's own PathSpline and
arclength_parameter so the geometry is identical to what the governor was derived from.
"""
import sys, json, math
from pathlib import Path
import numpy as np

COPY = Path(r"C:\TakeOne-audit-20260913\TakeOne-main-copy")
sys.path.insert(0, str(COPY))
from takeone.timing import PathSpline, MotionLimits
from takeone.planner import arclength_parameter

EV = Path(r"C:\TakeOne\docs\audit\2026-09-13\evidence")
PLAN = Path(r"C:\TakeOne-audit-20260913\out\plan-run1.json")

L = MotionLimits()
ARM = list(range(3, 13)); XY = [0, 1]; YAW = [2]


def groups(q_s, q_ss):
    """Return list of (|q_s| effective, |q_ss| effective, v_lim, a_lim) per constraint group."""
    out = []
    # arm: each joint separately
    for j in ARM:
        out.append((abs(q_s[j]), q_ss[j], L.arm_velocity_radps, L.arm_acceleration_radps2, "arm%d" % j))
    out.append((float(np.linalg.norm(q_s[XY])), float(np.linalg.norm(q_ss[XY])), L.cart_velocity_mps, L.cart_acceleration_mps2, "cart_xy"))
    out.append((abs(q_s[2]), q_ss[2], L.yaw_velocity_radps, L.yaw_acceleration_radps2, "yaw"))
    return out


def topp(path, n=2000):
    s = np.linspace(0.0, 1.0, n + 1)
    ds = s[1] - s[0]
    Q1 = path.derivative(s, 1)
    Q2 = path.derivative(s, 2)
    # velocity MVC: sdot <= v/|q_s|
    mvc = np.full(n + 1, np.inf)
    for k in range(n + 1):
        for a, b, vl, al, _ in groups(Q1[k], Q2[k]):
            if a > 1e-9:
                mvc[k] = min(mvc[k], vl / a)
    x_max = mvc ** 2  # sdot^2 ceiling from velocity
    # acceleration bounds for a given x = sdot^2:  for each axis |q_ss x + q_s sddot| <= a
    def acc_bounds(k, x):
        lo, hi = -np.inf, np.inf
        for a, b, vl, al, _ in groups(Q1[k], Q2[k]):
            # careful: for the cart xy group use the vector form conservatively: |q_ss|x + |q_s||sddot| <= a
            if a > 1e-9:
                hi = min(hi, (al - b * x) / a)
                lo = max(lo, (-al + b * x) / a)   # symmetric for scalar; conservative for the norm group
        return lo, hi
    # forward pass
    x = np.zeros(n + 1)
    for k in range(n):
        lo, hi = acc_bounds(k, x[k])
        if hi < lo:
            hi = lo  # infeasible point: take the MVC-limited value
        x[k + 1] = min(x_max[k + 1], x[k] + 2.0 * hi * ds)
        x[k + 1] = max(x[k + 1], 0.0)
    # backward pass (end at rest)
    x[n] = 0.0
    for k in range(n, 0, -1):
        lo, hi = acc_bounds(k, x[k])
        if hi < lo:
            lo = hi
        x[k - 1] = min(x[k - 1], x[k] - 2.0 * lo * ds)
        x[k - 1] = max(x[k - 1], 0.0)
    v = np.sqrt(np.maximum(x, 0.0))
    vm = 0.5 * (v[1:] + v[:-1])
    vm = np.maximum(vm, 1e-6)
    T = float(np.sum(ds / vm))
    # count acceleration reversals (sign changes of dx/ds) for the jerk ramp estimate
    dxd = np.diff(x)
    sign = np.sign(dxd[np.abs(dxd) > 1e-12])
    reversals = int(np.sum(sign[1:] != sign[:-1])) + 2  # plus start and stop
    return T, reversals


def vel_only(path, n=2000):
    s = np.linspace(0.0, 1.0, n + 1)
    Q1 = path.derivative(s, 1)
    Q2 = path.derivative(s, 2)
    r = np.full(n + 1, np.inf)
    for k in range(n + 1):
        for a, b, vl, al, _ in groups(Q1[k], Q2[k]):
            if a > 1e-9:
                r[k] = min(r[k], vl / a)
    r = np.minimum(r, 1.0 / 0.25)  # MIN_TRAVERSE_S cap as in derive_governor
    rm = 0.5 * (r[1:] + r[:-1])
    return float(np.sum((s[1] - s[0]) / rm))


def main():
    plan = json.loads(PLAN.read_text("utf-8"))
    ramp = max(L.arm_acceleration_radps2 / L.arm_jerk_radps3, L.cart_acceleration_mps2 / L.cart_jerk_mps3,
               L.yaw_acceleration_radps2 / L.yaw_jerk_radps3)
    rows = []
    tot_cur = tot_v = tot_topp = tot_toppj = 0.0
    for t in plan["takes"]:
        q = np.array(t["q"]); s = np.array(t["s_knots"])
        path = PathSpline(s, q)
        cur = t["rehearsal_duration_s"]; nominal = t["nominal_duration_s"]
        Tv = vel_only(path); Tt, rev = topp(path); Tj = Tt + rev * ramp
        rows.append(("take", t["label"], nominal, cur, Tv, Tt, Tj, rev))
        tot_cur += cur; tot_v += max(Tv, nominal); tot_topp += max(Tt, nominal); tot_toppj += max(Tj, nominal)
    for tr in plan["transitions"]:
        for p in tr["phases"]:
            q = np.array(p["q"])
            if len(q) < 6:
                continue
            path = PathSpline(arclength_parameter(q), q)
            cur = p["rehearsal_duration_s"]
            Tv = vel_only(path); Tt, rev = topp(path); Tj = Tt + rev * ramp
            rows.append(("reposition/" + p["kind"], f"{tr['from_segment']}->{tr['to_segment']}", 0.0, cur, Tv, Tt, Tj, rev))
            tot_cur += cur; tot_v += Tv; tot_topp += Tt; tot_toppj += Tj
    lines = ["# Analysis 2 - governor bound vs per-axis time-optimal parameterisation", "",
             f"limits: {L.describe()}", f"jerk ramp per reversal used for (d): {ramp:.3f} s (max over groups of a_lim/j_lim)", "",
             "| kind | segment | nominal source s | governor duration s (a) | velocity-only s (b) | TOPP v+a s (c) | TOPP + jerk ramps s (d) | reversals | ratio a/c | ratio a/d |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for kind, label, nominal, cur, Tv, Tt, Tj, rev in rows:
        rc = "n/a (locked-off, no motion)" if Tt < 1e-3 else f"{cur / Tt:.1f}"
        rd = "n/a" if Tt < 1e-3 else f"{cur / Tj:.1f}"
        lines.append(f"| {kind} | {label} | {nominal:.2f} | {cur:.2f} | {Tv:.2f} | {Tt:.2f} | {Tj:.2f} | {rev} | {rc} | {rd} |")
    lines += ["",
              f"TOTAL physical rehearsal (takes floored at nominal source duration): governor {tot_cur:.1f} s; velocity-only {tot_v:.1f} s; TOPP v+a {tot_topp:.1f} s; TOPP+jerk ramps {tot_toppj:.1f} s",
              f"ratio governor / TOPP(v+a) = {tot_cur / tot_topp:.2f};  governor / TOPP+jerk = {tot_cur / tot_toppj:.2f}",
              f"source filmed duration {plan['schedule']['filmed_source_s']:.2f} s; governor total is {tot_cur / plan['schedule']['filmed_source_s']:.1f}x the filmed source; TOPP+jerk total would be {tot_toppj / plan['schedule']['filmed_source_s']:.1f}x",
              "",
              "Caveats: (c) enforces velocity and acceleration per sample but not jerk; (d) adds one full jerk ramp per acceleration reversal, which over-counts",
              "because ramps overlap with cruise. The true jerk-limited time-optimal duration lies between (c) and (a). The paths are identical to the",
              "governor's (same PathSpline, same knots, same arclength parameterisation); only the time law differs. All limits are ASSUMED_placeholder."]
    (EV / "analysis-02-governor-vs-topp.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
