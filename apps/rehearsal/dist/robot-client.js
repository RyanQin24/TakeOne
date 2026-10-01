// Browser control owns an explicit finite run. Preview events never call start().
export class RobotClient {
  constructor({request = (url, options) => fetch(url, options), changed = () => {}, now = () => performance.now()} = {}) {
    this.request = request; this.changed = changed; this.now = now;
    this.state = {active:false, phase:'idle'}; this.plan = null; this.generation = 0;
    this.pending = false; this.ownsRun = false; this.observedAt = now();
    this.sequence = 0;this.starting = false;this.stopRequested = false;this.requestId = null;
  }
  async api(path, body) {
    const response = await this.request('/api/robot/' + path, body === undefined ? {} : {
      method:'POST', headers:{'Content-Type':'application/json', 'X-TakeOne-Robot-Token':this.state.token},
      body:JSON.stringify(body)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Robot connection unavailable.');
    return result;
  }
  update(state) {this.state = state;this.observedAt = this.now();this.changed();}
  invalidate() {this.generation++;this.plan = null;this.requestId = null;this.changed();}
  async poll() {
    const sequence = this.sequence;
    const state = this.ownsRun && this.state.active ? await this.api('heartbeat', {run_id:this.state.run_id}) : await this.api('status');
    if (sequence === this.sequence) this.update(state);
  }
  async prepare(settings, shot) {
    if (this.pending || this.state.active) return;
    this.pending = true;this.plan = null;const generation = ++this.generation;this.changed();
    try {
      const result = await this.api('prepare', {settings, ...(shot ? {shot} : {})});
      if (generation === this.generation) this.plan = result;
    } finally {this.pending = false;this.changed();}
  }
  async start() {
    if (!this.plan || this.pending || this.state.active) return;
    this.sequence++;this.pending = true;this.starting = true;this.stopRequested = false;this.changed();
    try {
      this.requestId ||= crypto.randomUUID();
      this.update(await this.api('start', {plan_id:this.plan.plan_id, request_id:this.requestId}));
      this.requestId = null;
      this.ownsRun = true;
      if (this.stopRequested) await this.stop();
    } finally {this.pending = false;this.starting = false;this.changed();}
  }
  async stop() {
    this.stopRequested = true;this.sequence++;
    if (this.state.active) this.update(await this.api('stop', {run_id:this.state.run_id}));
  }
  clock() {
    const duration = this.state.duration_s || 1;
    const elapsed = this.state.elapsed_s || 0;
    return Math.max(0, Math.min(duration, elapsed + (['aiming','running'].includes(this.state.phase) ? (this.now() - this.observedAt) / 1000 : 0)));
  }
  previewTime(preview) {
    const elapsed = this.clock(), setup = this.state.orbit_start_s || 0;
    return elapsed <= setup ? elapsed : Math.min(preview.duration_s,
      (preview.orbit_start_s || 0) + (elapsed - setup) / (this.state.orbit_duration_s || this.state.duration_s) * (preview.orbit_duration_s || preview.duration_s));
  }
  leave() {
    if (this.ownsRun && this.state.active) {
      this.request('/api/robot/stop', {method:'POST',keepalive:true,
        headers:{'Content-Type':'application/json','X-TakeOne-Robot-Token':this.state.token},
        body:JSON.stringify({run_id:this.state.run_id})}).catch(() => {});
    }
  }
}
