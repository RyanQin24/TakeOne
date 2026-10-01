"""Analysis 1: convert every joint sample in TakeOne-main/runtime/reference-export.json
to STS3215 encoder counts under the mapping documented in packages/takeone/calibration.py
(nominal midpoint mapping: degrees = deg(q) * axis_sign + zero_offset_deg;
count = int(degrees * 4095 / 360 + (range_min + range_max) / 2)), and count how many
samples fall outside (a) the configured calibration range, (b) the 2.0 deg planning
margin recorded in calibration/derived/*.json.

Read-only. Reads the repository; writes only into docs/audit/2026-09-13/evidence/.
The mapping is reproduced here rather than imported so the arithmetic is visible.
Assumption carried over from calibration/derived/*.json: model joint zero == calibration
midpoint ("nominal midpoint mapping"); servo_to_urdf_transform_verified is false, so this
whole analysis is conditional on that assumption.
"""
import json, math, sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(r"C:\TakeOne")
EV = ROOT / "docs/audit/2026-09-13/evidence"
JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]

def load_arm(role):
    reg = json.loads((ROOT / "calibration/registry.json").read_text("utf-8"))["arms"][role]
    raw = json.loads((ROOT / "calibration" / reg["original_path"]).read_text("utf-8"))
    derived = json.loads((ROOT / "calibration" / reg["mapping_path"]).read_text("utf-8"))
    configured = json.loads(json.dumps(raw))
    for name, ch in derived.get("raw_range_overrides", {}).items():
        configured[name].update(ch)
    margin = float(derived.get("limit_margin_deg", 0.0))
    bounds = {}
    for name, sign, off in zip(JOINTS, derived["axis_signs"], derived["zero_offsets_deg"]):
        half_span_deg = (configured[name]["range_max"] - configured[name]["range_min"]) * 180 / 4095
        usable = max(half_span_deg - margin, half_span_deg / 2)
        lo, hi = sorted(math.radians((v - off) / sign) for v in (-usable, usable))
        bounds[name] = (lo, hi)
    return dict(raw=raw, configured=configured, derived=derived, margin_deg=margin, bounds_rad=bounds,
                calibration_id=reg["calibration_id"])

def to_count(q, name, arm):
    sign = arm["derived"]["axis_signs"][JOINTS.index(name)]
    off = arm["derived"]["zero_offsets_deg"][JOINTS.index(name)]
    deg = math.degrees(q) * sign + off
    c = arm["configured"][name]
    mid = (c["range_min"] + c["range_max"]) / 2
    return deg * 4095 / 360 + mid, deg  # float count (before int truncation), degrees

def xml_ranges(path):
    tree = ET.parse(path)
    out = {}
    for j in tree.iter("joint"):
        n = j.get("name")
        if n and j.get("range"):
            lo, hi = (float(x) for x in j.get("range").split())
            out[n] = (lo, hi)
    return out

def main():
    export = json.loads((ROOT / "TakeOne-main/runtime/reference-export.json").read_text("utf-8"))
    arms = {"cam": load_arm("phone"), "light": load_arm("light")}
    xml = xml_ranges(ROOT / "TakeOne-main/rig_tall.xml")
    lines = []
    P = lines.append
    P("# Analysis 1 - reference export joint samples converted to encoder counts")
    P("")
    P(f"export: TakeOne-main/runtime/reference-export.json  schema={export['schema']}  generated_at_utc={export['generated_at_utc']}")
    P(f"robot_model hash in export: {export['hashes']['robot_model']}")
    P("mapping: packages/takeone/calibration.py ArmMapping (nominal midpoint; degrees = deg(q)*sign + zero_offset; count = degrees*4095/360 + mid)")
    P("cam arm -> phone calibration (%s); light arm -> light calibration (%s)" % (arms['cam']['calibration_id'], arms['light']['calibration_id']))
    P("CONDITIONAL on servo_to_urdf_transform_verified == false (configs/reference/previs_rig.json) and derived/*.json verified == false.")
    P("")
    # --- Table A: XML range vs calibrated range in degrees
    P("## A. rig_tall.xml joint range vs calibration-derived operating range (degrees, model frame)")
    P("")
    P("| arm | joint | XML lo | XML hi | calib lo | calib hi | margin lo | margin hi | XML exceeds calib (deg lo/hi) | XML exceeds margin (deg lo/hi) |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for prefix, arm in arms.items():
        for name in JOINTS:
            xlo, xhi = (math.degrees(v) for v in xml[f"{prefix}_{name}"])
            c = arm["configured"][name]
            sign = arm["derived"]["axis_signs"][JOINTS.index(name)]
            off = arm["derived"]["zero_offsets_deg"][JOINTS.index(name)]
            half = (c["range_max"] - c["range_min"]) * 180 / 4095
            clo, chi = sorted(((v - off) / sign) for v in (-half, half))
            mlo, mhi = (math.degrees(v) for v in arm["bounds_rad"][name])
            ex_c = (max(0.0, clo - xlo), max(0.0, xhi - chi))
            ex_m = (max(0.0, mlo - xlo), max(0.0, xhi - mhi))
            P(f"| {prefix} | {name} | {xlo:.2f} | {xhi:.2f} | {clo:.2f} | {chi:.2f} | {mlo:.2f} | {mhi:.2f} | {ex_c[0]:.2f} / {ex_c[1]:.2f} | {ex_m[0]:.2f} / {ex_m[1]:.2f} |")
    P("")
    P("Positive 'exceeds' values are degrees of XML-permitted travel the calibrated (or margin-reduced) range does not contain.")
    P("Zero means the XML range is inside the calibrated range on that side.")
    P("")
    # --- Samples
    P("## B. Every joint sample in the export, converted to counts")
    P("")
    names = export["joint_names"]
    def joint_cols():
        cols = []
        for i, n in enumerate(names):
            if n.startswith("cam_") or n.startswith("light_"):
                prefix, jn = n.split("_", 1)
                cols.append((i, prefix, jn))
        return cols
    cols = joint_cols()
    P(f"joint_names: {names}")
    P("")
    overall = {}
    def acc(key, i, prefix, jn, q):
        arm = arms[prefix]
        cnt, deg = to_count(q, jn, arm)
        c = arm["configured"][jn]
        lo, hi = arm["bounds_rad"][jn]
        d = overall.setdefault(key, {}).setdefault(f"{prefix}_{jn}", dict(n=0, min=1e9, max=-1e9, out_calib=0, out_margin=0, qmin=1e9, qmax=-1e9))
        d["n"] += 1
        d["min"] = min(d["min"], cnt); d["max"] = max(d["max"], cnt)
        d["qmin"] = min(d["qmin"], q); d["qmax"] = max(d["qmax"], q)
        if not (c["range_min"] <= int(cnt) <= c["range_max"]):
            d["out_calib"] += 1
        if not (lo <= q <= hi):
            d["out_margin"] += 1
    total_samples = 0
    for take in export["takes"]:
        for s in take["samples"]:
            total_samples += 1
            for i, prefix, jn in cols:
                acc(("take", take["segment"], take["label"]), i, prefix, jn, s["q"][i])
                acc(("ALL", "", ""), i, prefix, jn, s["q"][i])
    trans_samples = 0
    for tr in export["transitions"]:
        for ph in tr["phases"]:
            for q in ph["q_samples"]:
                trans_samples += 1
                for i, prefix, jn in cols:
                    acc(("transition", f"{tr['from_segment']}->{tr['to_segment']}", ph["kind"]), i, prefix, jn, q[i])
                    acc(("ALL", "", ""), i, prefix, jn, q[i])
    P(f"take samples: {total_samples} (uniform 5 Hz grid in export); transition samples: {trans_samples} (decimated q_samples)")
    P("")
    for key, table in overall.items():
        kind, seg, label = key
        P(f"### {kind} {seg} {label}".rstrip())
        P("")
        P("| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |")
        P("|---|---|---|---|---|---|---|---|---|")
        for jn, d in table.items():
            prefix, name = jn.split("_", 1)
            c = arms[prefix]["configured"][name]
            P(f"| {jn} | {d['n']} | {math.degrees(d['qmin']):.2f} | {math.degrees(d['qmax']):.2f} | {d['min']:.1f} | {d['max']:.1f} | [{c['range_min']}, {c['range_max']}] | {d['out_calib']} | {d['out_margin']} |")
        P("")
    # per-take status for cross-reference
    P("## C. Take status recorded in the export (for cross-reference)")
    P("")
    P("| segment | label | status | checks fail | checks unknown | checks conditional |")
    P("|---|---|---|---|---|---|")
    for take in export["takes"]:
        st = [c["status"] for c in take["checks"]]
        P(f"| {take['segment']} | {take['label']} | {take['status']} | {st.count('fail')} | {st.count('unknown')} | {st.count('conditional')} |")
    P("")
    P("## D. Export joint_limits_rad (what the planner solved inside) vs calibration bounds")
    P("")
    P("| joint | export lo (deg) | export hi (deg) | calib margin lo | calib margin hi |")
    P("|---|---|---|---|---|")
    for (i, prefix, jn), lim in zip(cols, export["joint_limits_rad"]):
        lo, hi = arms[prefix]["bounds_rad"][jn]
        P(f"| {prefix}_{jn} | {math.degrees(lim[0]):.2f} | {math.degrees(lim[1]):.2f} | {math.degrees(lo):.2f} | {math.degrees(hi):.2f} |")
    out = EV / "analysis-01-encoder-counts.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
