// Both event stamps and the snapshot stamp use the server's monotonic epoch.
// Only the time since receiving that snapshot uses the browser's local clock.
export function elapsedTakeSeconds(take, snapshotNs, receivedAt, now) {
  const start = take?.events?.find(event => event.kind === 'start_acknowledged')?.ack_monotonic_ns;
  if (!start || !snapshotNs || !Number.isFinite(receivedAt)) return 0;
  const stop = take.events.find(event => event.kind === 'stop_acknowledged')?.ack_monotonic_ns;
  const running = take.state === 'recording' && !stop;
  const elapsed = Number(BigInt(stop || snapshotNs) - BigInt(start)) / 1e9;
  return Math.max(0, elapsed + (running ? Math.max(0, now - receivedAt) / 1000 : 0));
}
