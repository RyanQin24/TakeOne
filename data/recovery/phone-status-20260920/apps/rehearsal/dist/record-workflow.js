/* Recording intent is independent of person detection. No robot commands. */
export function visibleSubject(people, selected) {
  if (people.some(person => person.track_id === selected)) return selected;
  return people.length === 1 ? people[0].track_id : '';
}

export function framingAimError(error) {
  // The controller requires each axis within its deadband, not vector length.
  return Array.isArray(error) && error.length === 2
    ? Math.max(Math.abs(error[0]), Math.abs(error[1])) : null;
}

export function subjectLabel(person) {
  return `${person.track_id} · detected`;
}

export function phoneReadinessLabel(phone) {
  if (!phone?.paired) return 'Not paired';
  if (phone.uncertain) return 'Previous recording outcome unknown — inspect the phone';
  if (phone.fingerprint && phone.observed?.fingerprint && phone.fingerprint !== phone.observed.fingerprint)
    return 'Phone settings changed since calibration — check Phone setup before filming';
  if (!phone.readiness?.ready) return phone.readiness?.reason || 'Phone setup incomplete';
  if (phone.last_result?.recording_confirmed && phone.last_result?.stop_confirmed)
    return 'Setup complete · last recording start/stop confirmed';
  return phone.observed ? 'Setup complete · phone connection checked' : 'Setup complete · phone connection not checked this session';
}

export async function startManualScene(client, { watching, onStopped, shot, signal } = {}) {
  if (signal?.aborted) return {started:false, reason:'Shot start cancelled.'};
  if (watching) {
    const stopped = await client.stopObserving();
    if (!stopped) return {started:false, reason:'Could not stop automatic framing. No manual take was started.'};
    onStopped?.(stopped);
  }
  if (signal?.aborted) return {started:false, reason:'Shot start cancelled.'};
  // stopObserving refreshes state: automatic roll may have won the race.
  const before = client.snapshot();
  if (!before.canStart) return {started:false, reason:before.error || 'Recorder is busy or disconnected. Stop or resolve the current take before recording another scene.'};
  await client.startTake(undefined, undefined, 'phone', shot);
  const after = client.snapshot();
  const started = Boolean(after.take?.take_id && after.take.take_id !== before.take?.take_id
    && ['starting', 'recording'].includes(after.take.state));
  return {started, reason:started ? '' : after.error || 'Recording was not confirmed. Check Phone setup and the take status.'};
}
