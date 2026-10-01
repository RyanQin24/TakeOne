// Bind the compiler's actor samples to the identical captured rig-frame window.
// There is deliberately no second attention or arm solver in the browser.
export function bindPerformers(preview, segment) {
  const samples = segment.performance_samples;
  if (!samples) return preview;
  if (samples.length !== preview.frames.length || samples.some((sample, index) =>
      Math.abs(sample.time_s - preview.frames[index].time_s) > 1e-7)) {
    throw new Error('Actor and rig samples use different source windows. Recompile this script.');
  }
  preview.frames.forEach((frame, index) => {
    frame.performers = structuredClone(samples[index].actors);
  });
  return preview;
}

export function performerSummary(poses, names) {
  if (!poses) return [];
  return Object.entries(poses).map(([id, pose]) => {
    const attention = pose.look_target ? `head toward ${pose.look_target}` : 'authored head direction';
    const error = (pose.attention_error_rad || 0) * 180 / Math.PI;
    const gesture = pose.gesture ? ` · ${pose.gesture} (proxy)` : '';
    return `${names.get(id) || id}: ${attention}${gesture}` +
      (error > 1 ? ` · target outside head range by ${error.toFixed(1)}°; turn the body` : '');
  });
}
