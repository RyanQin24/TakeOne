// Offline trajectory review. This module has no actuator or camera API.
export function describeArmReview(review) {
  if (!review) return 'No trajectory to review.';
  const lines = [
    `${review.ok ? 'Rehearsal passed' : 'Rehearsal rejected'} · ${review.pose_source}`,
    `Plan: ${review.plan_id}`,
    'Simulation only. No arm movement command sent. Clearance and physical motion are not verified.',
    ...(review.program?.assumptions || []).map(v => `Proposed assumption: ${v}`),
  ];
  for (const step of review.segments || []) lines.push(
    `Segment ${step.index + 1}: ${step.duration_s.toFixed(2)} s${step.duration_proposed ? ' (proposed)' : ''}; ` +
    `maximum sampled error ${(step.maximum_position_error_m * 1000).toFixed(2)} mm, ` +
    `aim ${step.maximum_aim_error_deg.toFixed(2)}°, roll ${step.maximum_roll_error_deg.toFixed(2)}°; ` +
    `${step.sampled_path_passed ? 'passed' : 'rejected'}`,
  );
  for (const fault of review.faults || []) lines.push(`Blocked: ${fault.reason}`);
  return lines.join('\n');
}

export class ArmPanel {
  constructor({api, ensureSession, root = document}) {
    this.api = api;
    this.ensureSession = ensureSession;
    this.root = root;
    this.review = null;
    this.version = 0;
    root.getElementById('armSimPose').addEventListener('click', () => this.select('simulated'));
    root.getElementById('armReadPose').addEventListener('click', () => this.select('measured_snapshot'));
    root.getElementById('armTime').addEventListener('input', () => this.draw());
  }

  async select(source) {
    const version = ++this.version;
    this.review = null;
    this.draw();
    this.root.getElementById('armReview').textContent = source === 'simulated'
      ? 'Selecting a synthetic starting pose…' : 'Reading encoder registers only; no torque or goal writes…';
    try {
      await this.ensureSession();
      const result = await this.api('pose', {source});
      if (version !== this.version) return;
      this.root.getElementById('armReview').textContent = `${result.pose_source} start selected. Ask TO for an arm movement.\n${result.message}`;
    } catch (error) {
      if (version === this.version) this.root.getElementById('armReview').textContent = error.message;
    }
  }

  async refresh() {
    const version = ++this.version;
    this.review = null;
    this.draw();
    try {
      const result = await this.api('review', {});
      if (version !== this.version) return;
      this.review = result.review;
      this.root.getElementById('armReview').textContent = describeArmReview(this.review);
      const slider = this.root.getElementById('armTime');
      slider.max = Math.max(0, (this.review?.frames?.length || 1) - 1);
      slider.value = 0;
      slider.disabled = !this.review?.frames?.length;
      this.draw();
    } catch (error) {
      if (version === this.version) this.root.getElementById('armReview').textContent = error.message;
    }
  }

  close() {
    ++this.version;
    this.review = null;
    this.root.getElementById('armReview').textContent = 'Session closed. Select a new starting pose before rehearsal.';
    this.root.getElementById('armTime').disabled = true;
    this.draw();
  }

  draw() {
    const canvas = this.root.getElementById('armCanvas');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const frames = this.review?.frames || [];
    const label = this.root.getElementById('armPoseDetail');
    if (!frames.length) { label.textContent = 'No trajectory. The chart is not a live camera view.'; return; }
    const i = Math.min(frames.length - 1, Number(this.root.getElementById('armTime').value));
    const frame = frames[i];
    const xs = frames.flatMap(f => [f.position_m[0], f.desired_position_m[0]]);
    const zs = frames.flatMap(f => [f.position_m[2], f.desired_position_m[2]]);
    const midX = (Math.min(...xs) + Math.max(...xs)) / 2;
    const midZ = (Math.min(...zs) + Math.max(...zs)) / 2;
    const span = Math.max(0.06, Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs));
    const scale = Math.min(canvas.width - 50, canvas.height - 50) / span;
    const project = p => [canvas.width / 2 + (p[0] - midX) * scale, canvas.height / 2 - (p[2] - midZ) * scale];
    for (const [key, color] of [['desired_position_m', '#999'], ['position_m', '#50c9a2']]) {
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
      frames.forEach((f, n) => { const p = project(f[key]); n ? ctx.lineTo(...p) : ctx.moveTo(...p); });
      ctx.stroke();
    }
    const p = project(frame.position_m);
    ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(...p, 4, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#f7bb5c'; ctx.beginPath(); ctx.moveTo(...p);
    ctx.lineTo(p[0] + 25 * frame.forward[0], p[1] - 25 * frame.forward[2]); ctx.stroke();
    label.textContent = `${frame.time_s.toFixed(2)} s · tool XYZ ${frame.position_m.map(v => v.toFixed(4)).join(', ')} m · ` +
      `joint angles ${frame.qpos.slice(this.review.program.role === 'phone' ? 3 : 8, this.review.program.role === 'phone' ? 8 : 13).map(v => (v * 180 / Math.PI).toFixed(1)).join(', ')}°`;
  }
}
