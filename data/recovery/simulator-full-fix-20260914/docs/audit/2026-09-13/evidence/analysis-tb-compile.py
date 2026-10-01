"""Compile the reference timeline through Tree B's planner (TakeOne-main/takeone/planner.py).

Rebuilds the project from TakeOne-main/runtime/reference-export.json (timeline, scene, drive,
anchors are all carried in the export) and compiles it with the same constructor the server uses
(server.py::job_compile): Planner(load_robot(), SceneModel(spec), drive, MotionLimits(),
GovernorLimits(), PlanOptions()).

Runs against an EXTERNAL copy of Tree B (C:\\TakeOne-audit-20260913\\TakeOne-main-copy) because
takeone/scene.py writes ROOT/.scene_compiled.xml on every SceneModel build; nothing is written
into C:\\TakeOne by this script.

usage: python analysis-tb-compile.py <run-label> [--reach-fraction F] [--limits-json path]
writes: C:\\TakeOne-audit-20260913\\out\\plan-<label>.json   (full plan, deterministic dumps)
        C:\\TakeOne-audit-20260913\\out\\export-<label>.json (build_export artifact)
        C:\\TakeOne-audit-20260913\\out\\meta-<label>.json   (timing, hashes)
"""
import sys, json, time, hashlib, platform
from pathlib import Path

COPY = Path(r"C:\TakeOne-audit-20260913\TakeOne-main-copy")
OUT = Path(r"C:\TakeOne-audit-20260913\out")
sys.path.insert(0, str(COPY))

from takeone.robot import load as load_robot
from takeone.scene import SceneSpec, SceneModel
from takeone.drive import DriveModel
from takeone.timeline import Timeline
from takeone.timing import MotionLimits, GovernorLimits
from takeone.planner import Planner, PlanOptions
from takeone.project import Project, build_export, dumps
from takeone.estimate import ScaleAnchors


def main():
    label = sys.argv[1]
    reach = 0.70
    limits = MotionLimits()
    if "--reach-fraction" in sys.argv:
        reach = float(sys.argv[sys.argv.index("--reach-fraction") + 1])
    OUT.mkdir(parents=True, exist_ok=True)
    export = json.loads((Path(r"C:\TakeOne") / "TakeOne-main/runtime/reference-export.json").read_text("utf-8"))
    project = Project("audit reference recompile", COPY)
    project.timeline = Timeline.from_json(export["timeline"])
    scene_raw = dict(export["scene"])
    # The export carries the absolute path of the machine that made it
    # ('/home/claude/work/rehearsal-mvp/rig_tall.xml'); SceneSpec.from_json restores it verbatim,
    # so the export does not recompile on another machine without this override (finding A3).
    exported_model_path = scene_raw.get("robot_model_path")
    scene_raw["robot_model_path"] = str(COPY / "rig_tall.xml")
    project.scene = SceneSpec.from_json(scene_raw)
    d = export["drive"]
    project.drive = DriveModel.for_topology(d["topology"], float(d["wheelbase_m"]), float(d["track_m"]))
    project.anchors = ScaleAnchors.from_json(export["anchors"])
    project.intent_script = ""
    t0 = time.perf_counter()
    robot = load_robot()
    scene = SceneModel(project.scene)
    t_load = time.perf_counter() - t0
    options = PlanOptions(reach_fraction=reach, rehearsal_camera_hfov_deg=export["intrinsics"]["hfov_deg"])
    planner = Planner(robot, scene, project.drive, limits, GovernorLimits(), options)
    t1 = time.perf_counter()
    plan = planner.compile(project.timeline)
    t_compile = time.perf_counter() - t1
    project.plan = plan
    plan_text = dumps(plan)
    (OUT / f"plan-{label}.json").write_text(plan_text, encoding="utf-8")
    exp = build_export(project, robot, scene, plan)
    exp_text = dumps(exp)
    (OUT / f"export-{label}.json").write_text(exp_text, encoding="utf-8")
    meta = dict(
        label=label, python=sys.version, platform=platform.platform(),
        exported_robot_model_path=exported_model_path,
        reach_fraction=reach, limits=limits.describe(),
        robot_model_hash=robot.model_hash, scene_hash=scene.scene_hash,
        settings_hash=project.settings_hash(),
        load_s=t_load, compile_s=t_compile,
        plan_sha256=hashlib.sha256(plan_text.encode()).hexdigest(),
        export_sha256=hashlib.sha256(exp_text.encode()).hexdigest(),
        plan_bytes=len(plan_text), export_bytes=len(exp_text),
        schedule=dict(rehearsal_duration_s=plan["schedule"]["rehearsal_duration_s"],
                      source_duration_s=plan["schedule"]["source_duration_s"],
                      filmed_source_s=plan["schedule"]["filmed_source_s"]),
        takes=[dict(segment=t["segment"], label=t["label"], status=t["status"],
                    rehearsal_duration_s=t["rehearsal_duration_s"],
                    nominal_duration_s=t["nominal_duration_s"], samples=t["samples"],
                    cart_notes=t["cart"]["notes"],
                    torque_status=t["load"]["torque"]["status"],
                    torque_value=t["load"]["torque"].get("value"),
                    torque_limit=t["load"]["torque"].get("limit"),
                    collision_status=t["collision"]["status"],
                    timing_status=t["timing"]["status"], drive_status=t["drive"]["status"],
                    checks=[(c["name"], c["status"], c.get("value")) for c in t["checks"]])
               for t in plan["takes"]],
        transitions=[dict(from_segment=t["from_segment"], to_segment=t["to_segment"], status=t["status"],
                          length_m=t.get("length_m"), rehearsal_duration_s=t["rehearsal_duration_s"],
                          path_kind=t.get("path_kind"),
                          phases=[dict(kind=p["kind"], rehearsal_duration_s=p["rehearsal_duration_s"],
                                       samples=len(p["q"])) for p in t["phases"]])
                     for t in plan["transitions"]],
    )
    (OUT / f"meta-{label}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("label", "load_s", "compile_s", "plan_sha256", "export_sha256", "schedule")}, indent=1))
    for t in meta["takes"]:
        print(t["segment"], t["label"], t["status"], f"{t['rehearsal_duration_s']:.2f}s", "torque:", t["torque_status"], t["torque_value"], "/", t["torque_limit"], "notes:", len(t["cart_notes"]))
    for t in meta["transitions"]:
        print("transition", t["from_segment"], "->", t["to_segment"], t["status"], f"{t['length_m']:.3f} m", f"{t['rehearsal_duration_s']:.2f}s", [(p["kind"], round(p["rehearsal_duration_s"], 2)) for p in t["phases"]])


if __name__ == "__main__":
    main()
