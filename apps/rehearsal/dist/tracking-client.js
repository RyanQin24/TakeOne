// Explicit Start owns a worker. Polling from other tabs does not renew its lease.
export class TrackingClient {
  constructor({request = (url, options) => fetch(url, options), changed = () => {}} = {}) {
    this.request = request;this.changed = changed;
    this.state = {active:false,phase:'idle'};this.starting = false;this.ownedRun = null;
    this.sequence = 0;this.stopRequested = false;this.requestId = null;this.requestOptions = null;
  }
  async api(path, body, keepalive = false) {
    const response = await this.request('/api/tracking/' + path, body === undefined ? {} : {
      method:'POST',keepalive,headers:{'Content-Type':'application/json','X-TakeOne-Tracking-Token':this.state.token},
      body:JSON.stringify(body)
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Tracking connection unavailable.');
    return result;
  }
  update(state) {this.state = state;this.changed();}
  async poll() {
    const sequence = this.sequence;
    const state = this.ownedRun === this.state.run_id && this.state.active ?
      await this.api('heartbeat',{run_id:this.ownedRun}) : await this.api('status');
    if (sequence === this.sequence) this.update(state);
  }
  async start(mode, armsEnabled) {
    if (this.starting || this.state.active) return;
    this.starting = true;this.stopRequested = false;this.sequence++;this.changed();
    const options = {mode,arms_enabled:mode === 'arms' || armsEnabled};
    if (JSON.stringify(options) !== this.requestOptions) this.requestId = null;
    this.requestOptions = JSON.stringify(options);
    this.requestId ||= crypto.randomUUID();
    try {
      const state = await this.api('start',{...options,request_id:this.requestId});
      this.ownedRun = state.run_id;this.requestId = null;this.update(state);
      if (this.stopRequested) await this.stop();
    } finally {this.starting = false;this.changed();}
  }
  async stop() {
    this.stopRequested = true;this.sequence++;
    if (this.state.active) this.update(await this.api('stop',{run_id:this.state.run_id}));
  }
  leave() {
    this.stopRequested = true;
    if (this.ownedRun === this.state.run_id && this.state.active)
      this.api('stop',{run_id:this.ownedRun},true).catch(() => {});
  }
}
