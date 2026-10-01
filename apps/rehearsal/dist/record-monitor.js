/* A device name is not proof that the Record video element is playing. */
export function monitorDevices(devices, kind) {
  return kind === 'phone_lens_feed'
    ? devices.filter(device => !/(galaxy|s23|live streamer cam 313)/i.test(device.label))
    : devices;
}

export function attachMonitorVideo(video, track, {
  onReady, onError, makeStream = track => new MediaStream([track]),
  schedule = setTimeout, cancel = clearTimeout, timeoutMs = 8000,
}) {
  let active = true;
  const ready = () => {
    if (!active || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return;
    cancel(timer);
    onReady();
  };
  const failed = message => { if (active) onError(message); };
  const timer = schedule(() => failed(
    'The camera opened but no video frames arrived. Close other apps using this camera, check its USB connection, then retry.'
  ), timeoutMs);
  video.addEventListener('loadeddata', ready);
  video.addEventListener('playing', ready);
  video.srcObject = makeStream(track);
  Promise.resolve().then(() => video.play()).then(ready).catch(error => failed(
    `Camera playback failed: ${error?.message || error}. Press Open / retry camera.`
  ));
  return () => {
    active = false;
    cancel(timer);
    video.removeEventListener('loadeddata', ready);
    video.removeEventListener('playing', ready);
    video.srcObject = null;
    // The shared camera owns the track; this view must not stop voice's stream.
  };
}
