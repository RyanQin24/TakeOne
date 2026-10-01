// Coalesce editor changes into one frame, then sleep until something changes.
// This schedules browser drawing only; it never schedules robot commands.
export const WORLD_VIEW = 1, PHONE_VIEW = 2, ALL_VIEWS = 3;

export class RenderLoop {
  constructor({paint, request = callback => requestAnimationFrame(callback), cancel = id => cancelAnimationFrame(id)}) {
    this.paint = paint;this.request = request;this.cancel = cancel;
    this.pending = null;this.dirty = 0;this.visible = true;
  }
  invalidate(views = ALL_VIEWS) {
    this.dirty |= views;
    if (this.visible && this.pending === null) this.pending = this.request(now => this.frame(now));
  }
  frame(now) {
    this.pending = null;
    const dirty = this.dirty;this.dirty = 0;
    const moving = this.paint(now, dirty);
    if (moving || this.dirty) this.invalidate(0);
  }
  setVisible(visible) {
    this.visible = visible;
    if (!visible && this.pending !== null) {this.cancel(this.pending);this.pending = null;}
    if (visible) this.invalidate();
  }
}

export function previewQuality(mode, pixelRatio = 1) {
  return mode === 'detailed' ? {pixelRatio:Math.min(pixelRatio, 1.5), shadows:true}
    : {pixelRatio:Math.min(pixelRatio, 1), shadows:false};
}
