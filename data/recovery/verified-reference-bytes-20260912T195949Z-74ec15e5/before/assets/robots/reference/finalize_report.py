"""Populate report evidence tables and freeze the downloadable evidence bundle."""
from pathlib import Path
import hashlib,json,zipfile,re,xml.etree.ElementTree as ET
import numpy as np

ROOT=Path(__file__).resolve().parent
DOC=ROOT.parent/'TAKE-ONE-Coordinated-Motion-Architecture.md'
report=json.loads((ROOT/'results/simulation_results.json').read_text())
results=report['results']
doc=DOC.read_text()
doc=doc.replace('v_{\x1b}(t)',r'v_{\rm braking}(t)')

urdf=ET.parse(ROOT/'upstream/so101_new_calib.urdf').getroot()
rows=['| Joint | Parent-to-joint translation (m) | Origin RPY (rad) | Published range (rad) |', '|---|---|---|---|']
for name in ['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll']:
    j=urdf.find(f"joint[@name='{name}']");o=j.find('origin');lim=j.find('limit')
    fmt=lambda s:', '.join(f'{x:.7g}' if abs(x)>1e-7 else '0' for x in np.fromstring(s,sep=' '))
    rows.append(f"| `{name}` | `({fmt(o.get('xyz'))})` | `({fmt(o.get('rpy'))})` | `{float(lim.get('lower')):.7g}` to `{float(lim.get('upper')):.7g}` |")
doc=doc.replace('<!-- JOINT_TABLE -->','\n'.join(rows))
vt=['| Executed dependency | Version |','|---|---|']+[f'| {k} | {v} |' for k,v in report['versions'].items()]
doc=doc.replace('<!-- VERSION_TABLE -->','\n'.join(vt))

metrics={
'five_joint_topology':lambda r:f"{r['arm_actuators']} arm actuators; {r['generalized_coordinates']} generalized coordinates",
'independent_urdf_fk':lambda r:f"100 poses: max {r['max_translation_error_m']*1e6:.3f} µm translation and {r['max_rotation_error_rad']:.3g} rad rotation difference between source representations",
'analytic_jacobians':lambda r:f"100 poses: position {r['position_max_abs_error']:.3g}, orientation {r['orientation_max_abs_error']:.3g}, image {r['image_max_abs_error']:.3g} maximum absolute finite-difference error",
'unreachable_goal_rejection':lambda r:f"2 m rise rejected; residual {r['residual_m']:.3f} m",
'both_2wd_models':lambda r:f"Analytic-arc endpoint difference {r['ackermann_endpoint_error_m']:.3g} m; assumed Ackermann minimum radius {r['ackermann_min_radius_at_30deg_m']:.3f} m",
'nonholonomic_rejections':lambda r:'Sideways velocity rejected; zero-speed Ackermann spin excluded; differential spin possible in its model',
'synthetic_camera_geometry':lambda r:f"Marker ID 7 detected; 100 noisy PnP trials, position p95 {r['translation_error_p95_m']*1000:.2f} mm",
'monocular_depth_ambiguity':lambda r:'Distinct points at 1 m and 2 m depth have the same pixel projection',
'synthetic_two_view_triangulation':lambda r:f"300 points; 0.6 m baseline and 1 px noise; position p95 {r['position_error_p95_m']*1000:.2f} mm, ideal known extrinsics",
'synthetic_localization_ekf':lambda r:f"XY RMSE {r['ekf_xy_rmse_m']*1000:.2f} mm vs biased odometry {r['odometry_xy_rmse_m']*1000:.2f} mm",
'plan_compiler':lambda r:f"{r['samples']} samples; max aim error {r['maximum_aim_error_deg']:.4f}°; joint speed {r['joint_v_max_rad_s']:.4f} rad/s, acceleration {r['joint_a_max_rad_s2']:.4f} rad/s², piecewise jerk {r['joint_jerk_piecewise_max_rad_s3']:.3f} rad/s³",
'request_revision_required':lambda r:f"Original exact-position request rejected: required change {r['largest_change_m']:.3f} m exceeds {r['requested_position_tolerance_m']:.3f} m tolerance",
'coupled_motion_feedback':lambda r:f"12-second arc, 600 ticks/run, 3 feedback-noise seeds; coordinated/replay framing RMSE ratio {r['rmse_ratio_to_open_loop']:.4f}",
'cross_arm_swept_samples':lambda r:f"{r['samples']} samples; minimum modeled cross-arm distance {r['minimum_distance_m']:.3f} m",
'obstacle_rejection':lambda r:f"Deliberate intersection detected; signed distance {r['penetration_signed_distance_m']:.3f} m",
'mujoco_arm_dynamics':lambda r:f"{r['physics_steps']} steps over 3 s; max joint error {r['max_joint_tracking_error_rad']:.4f} rad; force cap reached. Pass means stable integration only",
'illustrative_payload_capacity_gate':lambda r:f"Demand {r['maximum_inverse_dynamics_demand_Nm']:.3f} N·m exceeds allowed 0.800 N·m under assumed cap/margin",
'support_polygon_screen':lambda r:f"Nominal quasi-static margin {r['minimum_nominal_margin_m']:.3f} m; intentionally unstable case {r['deliberately_unstable_case_margin_m']:.3f} m",
'shared_phase_local_ruckig':lambda r:f"Local progress trajectory {r['duration_s']:.2f} s; bounds respected",
'runtime_fault_contracts':lambda r:f"{r['cases']} decision cases; no physical watchdog/stop claim",
'jerk_limited_stopping':lambda r:f"Jerk-limited stop including delay {r['stop_distance_with_delay_m']:.3f} m vs acceleration-only lower bound {r['acceleration_only_lower_bound_m']:.3f} m",
'3d_renderer':lambda r:'Actual modified-model render and dual-view 3D rehearsal clip',
'actor_beat_fixture':lambda r:'Synthetic entry, pause, loss, resume and exit; loss stays unknown rather than completing exit',
'shared_reference_contract':lambda r:f"Same-phase reference difference zero; 350 ms skew causes {r['independent_350ms_arm_schedule_max_joint_vector_error_rad']:.4f} rad joint-vector discrepancy",
'seedance_reference_contract':lambda r:'Reference and hash fixture produced; provider NOT called',
'ffmpeg_simulated_take_assembly':lambda r:f"Real FFmpeg assembly: {r['frames']} rendered frames, {r['duration_s']:.2f} seconds; no phone capture",
}
table=['| Executed check | Result | Measured outcome / interpretation |','|---|---|---|']
for name,r in results.items():table.append(f"| `{name}` | {'PASS' if r['passed'] else '**FAIL — retained**'} | {metrics[name](r)} |")
counts=f"**{sum(r['passed'] for r in results.values())} scenario checks passed; {sum(not r['passed'] for r in results.values())} payload-capacity check failed.** Passing a numerical scenario is not hardware approval.\n\n"
if '<!-- RESULT_TABLE -->' in doc:
    doc=doc.replace('<!-- RESULT_TABLE -->',counts+'\n'.join(table))
else:
    doc=re.sub(r'\*\*\d+ scenario checks passed;.*?(?=\n\n### 12\.4)',lambda _:counts+'\n'.join(table),doc,flags=re.S)
runs=results['coupled_motion_feedback']['runs']
table=['| Scenario | Mean framing RMSE, focal-normalized | Mean base endpoint error (m) | Highest per-run p95 QP setup + solve (ms) |','|---|---:|---:|---:|']
for name,values in runs.items():
    avg=lambda key:float(np.mean([v[key] for v in values]))
    qp=[v['qp_setup_solve_p95_ms'] for v in values if v['qp_setup_solve_p95_ms'] is not None]
    ms=f'{max(qp):.3f}' if qp else 'not used'
    table.append(f"| {name.replace('_',' ')} | {avg('image_rmse_normalized'):.6f} | {avg('base_endpoint_error_m'):.6f} | {ms} |")
summary='\n'.join(table)+'\n\nThe numerical improvement is specific to this synthetic fixture. QP timing excludes perception, bus communication and motor response; it is not an end-to-end latency measurement.'
if '<!-- CONTROL_SUMMARY -->' in doc:doc=doc.replace('<!-- CONTROL_SUMMARY -->',summary)
else:doc=re.sub(r'\| Scenario \| Mean framing RMSE, focal-normalized.*?(?=\n\n### 12\.5)',lambda _:summary,doc,flags=re.S)
assert '<!--' not in doc
assert all(ord(c)>=32 or c in '\n\t\r' for c in doc)
DOC.write_text(doc)

pkgs={'mujoco':'mujoco','osqp':'osqp','cv2':'opencv-python-headless','ruckig':'ruckig','numpy':'numpy','scipy':'scipy'}
import importlib.metadata
requirements=[f'{pkg}=={importlib.metadata.version(pkg)}' for pkg in list(pkgs.values())+['matplotlib']]
(ROOT/'requirements.txt').write_text('\n'.join(requirements)+'\n')

manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in str(p) and p.name!='sha256.json'}
(ROOT/'results/sha256.json').write_text(json.dumps(manifest,indent=2))
archive=ROOT.parent/'TAKE-ONE-Simulation-Evidence.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    z.write(DOC,DOC.name)
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and '__pycache__' not in str(p):z.write(p,str(p.relative_to(ROOT.parent)))
print(json.dumps({'document':str(DOC),'words':len(doc.split()),'archive':str(archive),'archive_bytes':archive.stat().st_size,'checks':len(results),'failed':[k for k,r in results.items() if not r['passed']]}))
