// Ground coordinates are metres. One displayed square is exactly one foot.
export const FOOT_M = 0.3048;
export const feet = metres => metres / FOOT_M;
export const metres = feetValue => feetValue * FOOT_M;
export const examplePath = () => Array.from({length:13},(_,i) => {
  const angle = Math.PI/2+i*Math.PI/12;return [2.5*Math.cos(angle),2.5*Math.sin(angle)];
});
export class PathDraft {
  constructor(points = examplePath()) {this.points = structuredClone(points);this.history = [];}
  checkpoint() {this.history.push(structuredClone(this.points));if (this.history.length > 40) this.history.shift();}
  replace(points) {this.checkpoint();this.points = structuredClone(points);}
  append(point, spacing = .04) {
    const last = this.points.at(-1);
    if (this.points.length >= 512 || (last && Math.hypot(point[0]-last[0],point[1]-last[1]) < spacing)) return false;
    this.points.push(point.map(v => Math.round(v * 10000) / 10000));return true;
  }
  undo() {if (this.history.length) this.points = this.history.pop();}
  close() {if (this.points.length > 2) {this.checkpoint();this.append(this.points[0], .001);}}
  endpoint(which, point) {if (this.points.length < 2) return;this.checkpoint();this.points[which === 'start' ? 0 : this.points.length-1] = point;}
}
