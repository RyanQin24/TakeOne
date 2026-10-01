// The Record clock is local to the selected shot, never to the whole script.
export function shotTime(scene, seconds) {
  return Math.max(0, Math.min(scene?.duration_s || 0, Number.isFinite(seconds) ? seconds : 0));
}

export function shotPreview(source, segment) {
  const selected = {...segment, t0_s:0, duration_s:source.duration_s,
    setup_s:source.orbit_start_s, filming_s:source.orbit_duration_s};
  return {...source, segments:[selected],
    frames:source.frames.map(frame=>({...frame, segment_id:segment.segment_id}))};
}

export async function startRobotShot(robot, scene, {signal} = {}) {
  const checkCancelled = () => { if (signal?.aborted) throw new Error('Shot start cancelled.'); };
  checkCancelled();
  if (!scene?.robot?.settings || !scene.robot.window?.plan_id)
    throw new Error('This shot has no reviewed robot movement. Reload the plan before filming.');
  await robot.poll();
  checkCancelled();
  if (robot.state.active) throw new Error('Stop the current robot shot first.');
  if (robot.state.tracking_active) throw new Error('Stop live tracking before filming this shot.');
  if (!robot.state.phone?.enabled || !robot.state.phone?.ready)
    throw new Error(robot.state.phone?.reason || 'Enable iPhone capture before filming this shot.');
  await robot.prepare(scene.robot.settings, scene.robot.window);
  checkCancelled();
  if (!robot.plan) throw new Error('The selected shot could not be prepared.');
  await robot.start();
  if (signal?.aborted) { await robot.stop(); checkCancelled(); }
  if (!robot.state.active || robot.state.error)
    throw new Error(robot.state.error || 'The robot shot did not start.');
}
