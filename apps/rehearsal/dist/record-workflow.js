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
  if (!phone) return 'Phone status unavailable · reconnect to TakeOne';
  if (phone.uncertain) return 'Previous recording outcome unknown — inspect the phone';
  if (phone.connection?.state === 'failed') return 'Phone check failed · open Phone setup to reconnect';
  if (!phone?.paired) return 'Not paired';
  if (phone.fingerprint && phone.observed?.fingerprint && phone.fingerprint !== phone.observed.fingerprint)
    return 'Phone settings changed since calibration — check Phone setup before filming';
  if (!phone.readiness?.ready) return phone.readiness?.reason || 'Phone setup incomplete';
  if (phone.connection?.state === 'checked') return 'Setup saved · last phone check succeeded';
  if (phone.connection?.state === 'stale') return 'Setup saved · phone check is out of date';
  return 'Setup saved · phone connection not checked this session';
}

export function phoneCalibrationLabel(phone) {
  if (phone?.focal_range_mm?.length === 2)
    return `Blackmagic reports ${phone.focal_range_mm[0]}–${phone.focal_range_mm[1]} mm · direct focal-length control`;
  const count = phone?.calibration_points || 0;
  return count < 2 ? `${count} measured ${count === 1 ? 'point' : 'points'} · at least two needed`
    : `${count} measured points · zoom estimated between measurements`;
}

export function phoneConnectionLabel(observed) {
  const product = typeof observed?.product === 'string' ? observed.product : observed?.product?.productName;
  const controllable = observed?.zoom_description?.controllable ?? observed?.controllable;
  return `${product || 'Camera'} · zoom ${controllable ? 'controllable' : 'not controllable'}`;
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
