// Pure playback math shared by the editor and its regression tests.
export const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

export function timecode(seconds) {
  const centiseconds = Math.round(Math.max(0, seconds) * 100);
  return `${String(Math.floor(centiseconds / 6000)).padStart(2, '0')}:${String(Math.floor(centiseconds / 100) % 60).padStart(2, '0')}.${String(centiseconds % 100).padStart(2, '0')}`;
}

export function framePair(frames, seconds) {
  if (!frames?.length || !Number.isFinite(seconds)) throw new Error('A finite time and preview frames are required.');
  const time = clamp(seconds, 0, frames.at(-1).time_s);
  let lo = 0, hi = frames.length - 1;
  while (lo < hi) {
    const middle = Math.ceil((lo + hi) / 2);
    if (frames[middle].time_s <= time) lo = middle;
    else hi = middle - 1;
  }
  const a = frames[lo], b = frames[Math.min(lo + 1, frames.length - 1)];
  if (a.segment_id && b.segment_id && a.segment_id !== b.segment_id) return {a,b:a,mix:0};
  return {a, b, mix: b.time_s === a.time_s ? 0 : (time - a.time_s) / (b.time_s - a.time_s)};
}

export function verticalFov(focalMm, aspect = 16 / 9) {
  return 2 * Math.atan(36 / aspect / (2 * focalMm)) * 180 / Math.PI;
}

export function advance(time, delta, duration, loop) {
  if (![time, delta, duration].every(Number.isFinite) || duration <= 0 || delta < 0) throw new Error('Invalid playback time.');
  const next = time + delta;
  return {time: loop ? next % duration : Math.min(next, duration), ended: !loop && next >= duration};
}
