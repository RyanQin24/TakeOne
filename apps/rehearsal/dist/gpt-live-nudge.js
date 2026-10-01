// The model can prepare a review. Only this separate operator button requests execution.
export class NudgePanel {
  constructor({api, ensureSession, inform}) {
    Object.assign(this, {api, ensureSession, inform});
    this.review = null;
    this.runId = null;
    this.epoch = 0;
    this.busy = false;
    this.timer = null;
    this.expiry = null;
    this.$ = id => document.getElementById(id);
    this.$('nudgePrepare').addEventListener('click', () => this.prepare());
    this.$('nudgeReady').addEventListener('change', () => this.updateButton());
    this.$('nudgeRun').addEventListener('click', () => this.start());
    this.$('nudgeStop').addEventListener('click', () => this.stop());
  }

  updateButton() {
    this.$('nudgeRun').disabled = !this.review || !this.$('nudgeReady').checked || this.busy || !!this.runId;
    this.$('nudgePrepare').disabled = this.busy || !!this.runId;
  }

  display(result) {
    if (result?.review) this.setReview(result.review);
    if (result?.cart_test?.pending) this.setReview(result.cart_test.pending);
  }

  discardReview() {
    clearTimeout(this.expiry);
    this.review = null;
    this.$('nudgeReady').checked = false;
    this.$('nudgeReview').textContent = 'No cart test prepared. An arm request cannot authorize cart movement.';
    if (!this.runId) this.$('nudgeState').textContent = 'Previous cart review cancelled.';
    this.updateButton();
  }

  setReview(review) {
    if (this.review?.review_id === review.review_id) return;
    clearTimeout(this.expiry);
    this.review = review;
    this.$('nudgeReady').checked = false;
    this.$('nudgeReview').textContent = [
      `Proposed direction: ${review.direction} (relative to chassis heading).`,
      `Exactly ${review.duration_s} s at logical wheel commands ${review.logical_commands.join(', ')}.`,
      `Actual UART values: ${review.transmitted_wire}; configured wiring polarity ${review.wire_polarity}.`,
      `Cart ${review.cart_port}, USB identity ${review.usb_serial}. Both arms excluded.`,
      'Startup and shutdown request zero speed for 0.1 s each. Travel, direction and braking are not physically verified.',
      'No promised distance. No automatic repeat, reverse, or escalation if it does not move.',
      `Plan: ${review.plan_id}. Approval expires in ${review.expires_in_s} s.`,
    ].join('\n');
    this.$('nudgeState').textContent = 'Awaiting your review — no hardware command sent.';
    this.expiry = setTimeout(() => {
      this.review = null; this.updateButton();
      if (!this.runId) this.$('nudgeState').textContent = 'Review expired. Prepare a new test.';
    }, review.expires_in_s * 1000);
    this.updateButton();
  }

  async prepare() {
    if (this.busy || this.runId) return;
    this.busy = true; this.review = null; this.updateButton();
    const epoch = this.epoch;
    try {
      await this.ensureSession();
      const result = await this.api('prepare', {direction: 'forward'});
      if (epoch !== this.epoch) return;
      this.display(result);
    } catch (error) {
      if (epoch === this.epoch) this.$('nudgeState').textContent = error.message;
    } finally {
      if (epoch === this.epoch) {this.busy = false; this.updateButton();}
    }
  }

  async start() {
    if (!this.review || !this.$('nudgeReady').checked || this.busy || this.runId) return;
    const review = this.review, epoch = this.epoch;
    this.review = null; this.busy = true; clearTimeout(this.expiry); this.updateButton();
    this.$('nudgeState').textContent = 'Launching your approved one-shot test…';
    try {
      const result = await this.api('start', {review_id: review.review_id, plan_id: review.plan_id,
        request_id: crypto.randomUUID(), operator_ready: true});
      if (epoch !== this.epoch) return;
      this.runId = result.run_id;
      this.$('nudgeStop').disabled = false;
      void this.pulse(epoch);
    } catch (error) {
      // Never retry Start after an uncertain network outcome. Request Stop instead.
      try {await this.api('stop', {});} catch {}
      if (epoch === this.epoch) this.$('nudgeState').textContent = `Start failed/uncertain: ${error.message}. Stop requested; verify the cart physically.`;
    } finally {
      if (epoch === this.epoch) {this.busy = false; this.updateButton();}
    }
  }

  async pulse(epoch) {
    if (epoch !== this.epoch || !this.runId) return;
    try {
      const result = await this.api('heartbeat', {run_id: this.runId});
      if (epoch !== this.epoch) return;
      this.$('nudgeState').textContent = `Controller: ${result.phase}${result.error ? ' — ' + result.error : ''}. Physical motion/stopping not verified.`;
      if (!result.active) {
        this.runId = null; this.$('nudgeStop').disabled = true; this.updateButton();
        this.inform(`Cart commissioning result: ${result.phase}. ${result.error || ''} Command completion is not proof of physical travel or stopping. Ask the operator what they observed.`);
        return;
      }
      this.timer = setTimeout(() => this.pulse(epoch), 250);
    } catch (error) {
      if (epoch !== this.epoch) return;
      this.$('nudgeState').textContent = `Connection lost: ${error.message}. Worker lease will cancel; use physical abort if needed. No automatic resume.`;
      try {await this.api('stop', {});} catch {}
      // No reconnection/retry loop after losing the control lease.
      this.runId = null; this.updateButton();
    }
  }

  async stop() {
    this.review = null; this.updateButton();
    try { await this.api('stop', {}); this.$('nudgeState').textContent = 'Stop requested. Verify physically that the cart stopped.'; }
    catch (error) { this.$('nudgeState').textContent = `Stop not confirmed: ${error.message}. Use physical abort.`; }
  }

  close() {
    ++this.epoch;
    clearTimeout(this.timer); clearTimeout(this.expiry);
    this.review = null; this.runId = null; this.busy = false;
    this.$('nudgeReady').checked = false;
    this.$('nudgeStop').disabled = true;
    this.$('nudgeState').textContent = 'Session closed. Any pending review is cancelled; verify physical state after a run.';
    this.updateButton();
  }
}
