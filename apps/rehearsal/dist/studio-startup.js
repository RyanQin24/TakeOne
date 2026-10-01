/* Deliberately dependency-free: module or GPU failure must not leave a spinner. */
(() => {
  const byId = id => document.getElementById(id);
  let recovering = false;
  function reload(retry = 0) {
    const url = new URL(location.href);
    if (retry) url.searchParams.set('studioRetry', String(retry));
    else url.searchParams.delete('studioRetry');
    location.replace(url.href);
  }
  function fail(error) {
    if (recovering) return;
    const detail = String(error?.message || error || 'Startup did not finish.');
    const transient = /failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed|loading the 3d javascript modules timed out/i.test(detail);
    const attempts = Number(new URL(location.href).searchParams.get('studioRetry')) || 0;
    if (transient && attempts < 2) {
      // A failed dependency stays in this document's module map. Importing the
      // root again cannot repair it: reload the preview's whole module graph.
      recovering = true;
      const message = `Reconnecting the planned frame (${attempts + 1}/2)…`;
      if (byId('loadingText')) byId('loadingText').textContent = message;
      if (byId('phoneLoadingText')) byId('phoneLoadingText').textContent = message;
      if (document.body.dataset.recordMonitor === 'true')
        parent.postMessage({type:'takeone:plan-loading', message}, location.origin);
      setTimeout(() => reload(attempts + 1), 750);
      return;
    }
    const graphics = /webgl|graphics|context|gpu/i.test(detail);
    const advice = graphics
      ? 'This browser could not start the 3D graphics engine. Check Chrome Settings → System → graphics acceleration, then relaunch Chrome. Your script is still saved.'
      : 'The 3D studio could not start. Reload this page; if it persists, copy the error below. Your script is still saved.';
    const world = byId('worldPanel');
    if (world) world.dataset.previewState = 'error';
    const loading = byId('loading');
    if (loading) { loading.hidden = false; loading.classList.add('error'); }
    if (byId('loadingText')) byId('loadingText').textContent = `${advice}\n${detail}`;
    if (byId('status')) byId('status').textContent = 'Studio startup failed';
    const retry = byId('retryPreview');
    if (retry) { retry.hidden = false; retry.textContent = 'Reload studio'; retry.onclick = () => reload(); }
    const camera = byId('phoneLoadingText');
    if (camera) camera.textContent = detail;
    if (document.body.dataset.recordMonitor === 'true') {
      parent.postMessage({type:'takeone:plan-error', message:detail}, location.origin);
    }
    console.error('Shot Studio startup:', error);
  }
  const timer = setTimeout(() => fail(new Error('Loading the 3D JavaScript modules timed out.')), 20000);
  import('/orbit.js').then(() => clearTimeout(timer), error => { clearTimeout(timer); fail(error); });
})();
