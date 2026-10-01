"""Analyses 6 and 7, plus the C6 torque re-screen, the C9 camera-height band and the B3 track-width effect.

All numbers are derived from repository files that are quoted by path. Every ceiling used is
labelled with the provenance the repository gives it (policy / ASSUMED_placeholder), never as a
measured capability.
"""
import json, math
from pathlib import Path

ROOT = Path(r"C:\TakeOne")
EV = ROOT / "docs/audit/2026-09-13/evidence"
PLAN = Path(r"C:\TakeOne-audit-20260913\out\plan-run1.json")

lines = []
P = lines.append

# ------------------------------------------------------------------ inputs
rig = json.loads((ROOT / "configs/rig.json").read_text("utf-8"))
armx = json.loads((ROOT / "configs/arm-execution.json").read_text("utf-8"))
cartrt = json.loads((ROOT / "configs/cart-runtime.json").read_text("utf-8"))
cartresp = json.loads((ROOT / "configs/cart-response.json").read_text("utf-8"))
plan = json.loads(PLAN.read_text("utf-8"))
limits_b = plan["limits"]

P("# Analyses 6 and 7 - tracking envelope, cart speed, torque re-screen, height band, track width")
P("")
P("## Inputs (quoted)")
P("")
P(f"- TakeOne-main/takeone/timing.py::MotionLimits (via plan['limits']): arm v={limits_b['arm_velocity_radps']} rad/s, a={limits_b['arm_acceleration_radps2']} rad/s^2, j={limits_b['arm_jerk_radps3']} rad/s^3; yaw v={limits_b['yaw_velocity_radps']} rad/s; cart v={limits_b['cart_velocity_mps']} m/s; source={limits_b['source']}")
cl = armx["commissioning_limits"]
P(f"- configs/arm-execution.json::commissioning_limits: velocity_rad_s={cl['velocity_rad_s']}, acceleration_rad_s2={cl['acceleration_rad_s2']}, jerk_rad_s3={cl['jerk_rad_s3']} (policy for supervised trials, not measured capability)")
cart = rig["cart"]
P(f"- configs/rig.json::cart: minimum_speed_m_s={cart.get('minimum_speed_m_s')}, minimum_command={cart.get('minimum_command')}, command_cap={cart.get('command_cap')}, track_width_m={cart.get('track_width_m')}, wheel_diameter_m={cart.get('wheel_diameter_m')}")
P(f"- configs/cart-runtime.json: commissioning_max_command={cartrt.get('commissioning_max_command')}, commissioning_max_duration_s={cartrt.get('commissioning_max_duration_s')}, commissioning_equal_commands_only={cartrt.get('commissioning_equal_commands_only')}, watchdog_s={cartrt.get('watchdog_s')}, period_s={cartrt.get('period_s')}")
P(f"- configs/cart-response.json: mode={cartresp.get('mode')}, wheel tables empty={all(not v for v in (cartresp.get('wheels') or {}).values()) if isinstance(cartresp.get('wheels'), dict) else cartresp.get('wheels')}")
P("")

# ------------------------------------------------------------ F2 algebra check
P("## Analysis 6 - tracking envelope (pan axis), closed form checked numerically")
P("")
P("theta(t) = atan(v t / d); omega = v d / (d^2 + v^2 t^2); peak omega = v/d at t=0.")
P("omega_dot = -2 v^3 d t / (d^2+v^2 t^2)^2; extremum at v t = d/sqrt(3): |omega_dot|max = (3 sqrt(3)/8) v^2/d^2 = 0.6495 v^2/d^2.")
P("omega_ddot(0) = -2 v^3/d^3 (peak magnitude at closest approach).")
# numeric check
v, d = 1.0, 1.0
import numpy as np
t = np.linspace(-5, 5, 2000001)
om = v * d / (d * d + v * v * t * t)
dt = t[1] - t[0]
omd = np.gradient(om, dt); omdd = np.gradient(omd, dt)
P(f"numeric check (v=d=1): peak omega={om.max():.6f} (expect 1.0); peak |omega_dot|={np.abs(omd).max():.6f} (expect 0.649519); peak |omega_ddot|={np.abs(omdd).max():.6f} (expect 2.0)")
P("")
P("Standoff constraints: d >= v/omega_max; d >= v*sqrt(0.6495/alpha_max); d >= v*(2/J_max)^(1/3).")
P("")
speeds = [1.0, 2.0, 3.0, 5.0]
CLAMP = 6.0
for jerk_label, J in (("Tree B MotionLimits jerk 12.0 rad/s^3 (ASSUMED_placeholder)", 12.0),
                      ("configs/arm-execution.json jerk 20.0 rad/s^3 (commissioning policy)", 20.0)):
    P(f"### ceilings: omega_max=0.80 rad/s, alpha_max=1.80 rad/s^2, {jerk_label}")
    P("")
    P("| subject speed v (m/s) | d_vel = v/0.80 | d_acc = v*sqrt(0.6495/1.80) | d_jerk = v*(2/J)^(1/3) | binding | required standoff (m) | vs 6.0 m clamp (intent.camera_track / planner.sample_goals) |")
    P("|---|---|---|---|---|---|---|")
    for v in speeds:
        dv, da, dj = v / 0.80, v * math.sqrt(0.6495 / 1.80), v * (2.0 / J) ** (1.0 / 3.0)
        req = max(dv, da, dj)
        binding = ["velocity", "acceleration", "jerk"][[dv, da, dj].index(req)]
        P(f"| {v:.1f} | {dv:.3f} | {da:.3f} | {dj:.3f} | {binding} | {req:.2f} | {'EXCEEDS clamp' if req > CLAMP else 'inside clamp'} |")
    P("")
P("Coefficients: d_vel = 1.250 v; d_acc = 0.601 v; d_jerk = 0.550 v (J=12) / 0.464 v (J=20). Velocity binds at every speed.")
P("")
# vertical axis
P("### Vertical axis (tilt)")
P("")
P("Head bob: z = A sin(2 pi f t), A=0.05 m, stride frequency f=2.7 Hz for a 3 m/s jog (assumed gait figure, not measured). At standoff d the tilt angle is ~z/d.")
for d in (1.8, 3.75, 6.0):
    A, f = 0.05, 2.7
    w = 2 * math.pi * f
    om = A * w / d; al = A * w * w / d; je = A * w ** 3 / d
    P(f"- d={d} m: peak tilt rate {om:.3f} rad/s (ceiling 0.80), accel {al:.3f} rad/s^2 (ceiling 1.80), jerk {je:.2f} rad/s^3 (ceiling 12) -> {'jerk binds' if je > 12 else ('accel binds' if al > 1.8 else ('velocity binds' if om > 0.8 else 'inside all ceilings'))}")
P("Descending steps: rise 0.17 m per step at 2 steps/s = 0.34 m/s sustained vertical rate; at d=3.0 m the tilt rate is 0.113 rad/s, at d=1.8 m 0.189 rad/s; both inside the 0.80 rad/s ceiling. Vertical is not the binding axis; horizontal pan is.")
P("")

# --------------------------------------------------------------- cart speeds
P("## Analysis 7 - cart speed against a 3 m/s jog")
P("")
sample = float(cart.get("minimum_speed_m_s", 0.1375))
cmd_min = float(cart.get("minimum_command", 0.04)); cap = float(cart.get("command_cap", 0.15))
extrap = sample * cap / cmd_min
P("| figure | value (m/s) | provenance | 3 m/s jog / value | 1.4 m/s walk / value |")
P("|---|---|---|---|---|")
P(f"| configs/rig.json minimum_speed_m_s (55 cm / 4 s at command {cmd_min}, provisional) | {sample:.4f} | single operator observation, provisional | {3.0 / sample:.1f}x short | {1.4 / sample:.1f}x short |")
P(f"| linear extrapolation of that sample to command_cap {cap} | {extrap:.3f} | UNEVIDENCED extrapolation (response tables empty; drift reported) | {3.0 / extrap:.1f}x short | {1.4 / extrap:.1f}x short |")
P(f"| TakeOne-main drive.py DriveLimits.max_speed_mps | 0.25 | ASSUMED_placeholder | {3.0 / 0.25:.1f}x short | {1.4 / 0.25:.1f}x short |")
P("")
mc = float(cartrt.get("commissioning_max_command", 0.05)); md = float(cartrt.get("commissioning_max_duration_s", 2.0))
P(f"Supervised envelope (configs/cart-runtime.json): command <= {mc} for <= {md} s, equal commands only (straight line). At the provisional 0.1375 m/s-per-0.04 slope, 0.05 -> ~{sample * mc / cmd_min:.3f} m/s; net displacement in {md} s ~{sample * mc / cmd_min * md:.2f} m. That is the whole displacement budget of a qualified cart move today.")
P(f"Walking speed the qualified envelope supports: {sample * mc / cmd_min:.3f} m/s (provisional slope) for at most {md} s -- slower than a slow walk (~1.0 m/s) by {1.0 / (sample * mc / cmd_min):.1f}x. Following a walking subject is not inside the qualified envelope either; following a runner is not available.")
P("")

# ---------------------------------------------------------- key light angle
P("## Key-light angle from one cart")
P("")
for reach in (0.29, 0.3745):
    for dist in (2.0, 3.75):
        P(f"- lateral offset {reach:.3f} m at subject distance {dist} m: max key angle ~ atan({reach}/{dist}) = {math.degrees(math.atan2(reach, dist)):.1f} deg (planner uses asin(comfortable/dist) = {math.degrees(math.asin(min(1, reach / dist))):.1f} deg)")
P("A 35 deg key at 2 m needs a lateral offset of 2*tan(35deg) = %.2f m; no arm on this cart reaches it. Ring-light irradiance falls as 1/d^2: moving from 2.0 m to 3.75 m keeps %.0f%% of the light." % (2 * math.tan(math.radians(35)), 100 * (2.0 / 3.75) ** 2))
P("")

# ---------------------------------------------------------- C6 torque re-screen
P("## C6 - torque re-screen against STS3215 datasheet figures (spec, not measured)")
P("")
P("Datasheet figures (spec, not measured): STS3215 7.4 V variant (C001): stall 19.5 kg*cm at 7.4 V, 16.5 kg*cm at 6 V; rated 5 kg*cm at 7.4 V, 4 kg*cm at 6 V; gear 1:345")
P("(https://pages.switch-science.com/comparison/files/feetech/serial-sts/STS3215_datasheet.pdf). 12 V variant (C047/C018): stall 30 kg*cm, rated 10 kg*cm, gear 1:345")
P("(https://www.seeedstudio.com/STS3215-30KG-Serial-Servo-p-6340.html). 1 kg*cm = 0.0980665 N*m.")
P("Bus voltage on this rig (docs/robot-commissioning.md line 68): phone arm read 11.9-12.6 V; light arm read 5.8 V at rest and 4.9 V during approach on a 5 V supply. Motor variant of each arm is unconfirmed there.")
P("")
KGCM = 0.0980665
figs = {
    "cam (phone, ~12 V bus)": dict(rated=10 * KGCM, stall=30 * KGCM, note="12 V variant spec; variant unconfirmed"),
    "light (~5-5.8 V bus)": dict(rated=4 * KGCM, stall=16.5 * KGCM, note="6 V column of the 7.4 V variant; the rig runs BELOW 6 V, so real capability is lower and unknown"),
}
P("| take | status (0.800 N*m assumed) | worst joint | peak N*m | gravity N*m | cam arm peak | vs cam rated 0.981 | vs cam stall 2.942 | light arm peak | vs light rated 0.392 (6 V) | vs light stall 1.618 (6 V) |")
P("|---|---|---|---|---|---|---|---|---|---|---|")
changed_rated = changed_stall = 0
for t in plan["takes"]:
    tq = t["load"]["torque"]
    cam = max(j["max_nm"] for j in tq["per_joint"] if j["joint"].startswith("cam_"))
    lig = max(j["max_nm"] for j in tq["per_joint"] if j["joint"].startswith("light_"))
    v_cam_r = "fail" if cam > figs["cam (phone, ~12 V bus)"]["rated"] else "conditional"
    v_cam_s = "fail" if cam > figs["cam (phone, ~12 V bus)"]["stall"] else "conditional"
    v_l_r = "fail" if lig > figs["light (~5-5.8 V bus)"]["rated"] else "conditional"
    v_l_s = "fail" if lig > figs["light (~5-5.8 V bus)"]["stall"] else "conditional"
    new_rated = "fail" if (v_cam_r == "fail" or v_l_r == "fail") else "conditional"
    new_stall = "fail" if (v_cam_s == "fail" or v_l_s == "fail") else "conditional"
    if new_rated != tq["status"]: changed_rated += 1
    if new_stall != tq["status"]: changed_stall += 1
    P(f"| {t['label']} | {tq['status']} | {tq['worst_joint']} | {tq['value']:.3f} | {tq['gravity_component_nm']:.3f} | {cam:.3f} | {v_cam_r} | {v_cam_s} | {lig:.3f} | {v_l_r} | {v_l_s} |")
P("")
P(f"Verdict changes vs the 0.800 N*m assumption: {changed_rated} of {len(plan['takes'])} takes change against RATED figures; {changed_stall} of {len(plan['takes'])} change against STALL figures.")
P("Gravity-only demand on the light arm (0.73-0.77 N*m per the plan) already exceeds the light arm's 6 V RATED torque (0.392 N*m) on every take: at its measured 4.9-5.8 V supply the light arm is holding more than its continuous rating on gravity alone. That is a build/supply finding, not a planning finding.")
P("")

# ------------------------------------------------------------ C9 height band
P("## C9 - camera-height band arithmetic")
P("")
for mount, reach in ((1.20, 0.5350), (1.23, 0.5350)):
    for frac in (0.70, 0.85, 1.0):
        comfortable = frac * reach
        max_dz = math.sqrt(max(comfortable ** 2 - 0.09 ** 2, 1e-6))
        P(f"- mount {mount:.2f} m, reach bound {reach} m, reach_fraction {frac:.2f}: comfortable={comfortable:.4f} m, max_dz={max_dz:.4f} m, band [{mount - max_dz:.2f}, {mount + max_dz:.2f}] m")
P("The UI slider (dist/app.js renderAnchors nominal_camera_height_m) offers 0.5-2.0 m; camera keys accept up to 2.2 m (sample_goals clamp); the measured rig reaches 1.80 m (configs/rig.json max_extended_height_m). At reach_fraction 0.70 from a 1.20 m mount the band top is 1.56 m: 0.24 m of the measured 1.80 m envelope is removed by the choice of 0.70 plus the 0.03 m mount error.")
P("")

# ------------------------------------------------------------ B3 track width
P("## B3 - track width effect on differential kinematics")
P("")
for track in (0.34, 0.58):
    P(f"- track {track} m: yaw rate for a 0.10 m/s wheel-speed difference = dv/track = {0.10 / track:.3f} rad/s; wheel speed difference needed for the 0.6 rad/s yaw ceiling = {0.6 * track:.3f} m/s")
P(f"Ratio 0.58/0.34 = {0.58 / 0.34:.2f}: for the same wheel-speed difference the real cart yaws 1.71x SLOWER than the simulated one; equivalently the in-place rotation phases (which the governor already times at the yaw ceiling, not at a wheel-speed limit) are unaffected in duration, but the WHEEL speeds the drive screen infers per phase are 1.71x too low for a rotation and the no-slip/turning-radius checks are evaluated on the wrong wheel geometry. The tipping screen uses cart_footprint (0.46 x 0.38 m assumed) not the track; with the real 0.58 m track the support polygon is wider, so the assumed screen is conservative in roll and unmeasured in pitch (axle -0.27 m, casters +0.32 m per configs/rig.json).")
P("")
(EV / "analysis-06-07-envelopes.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
