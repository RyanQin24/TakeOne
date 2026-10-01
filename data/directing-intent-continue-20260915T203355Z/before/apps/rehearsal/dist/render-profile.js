// Opt-in, local diagnostics: /?profile=1. No telemetry or GPU readback.
export function renderProfile(renderers) {
  if (!new URLSearchParams(location.search).has('profile')) return null;
  const output = document.createElement('output');
  output.id = 'renderProfile';
  output.setAttribute('aria-label', 'Preview performance sample');
  output.style.cssText = 'position:fixed;bottom:4px;left:4px;z-index:1000;background:#101518ee;color:#ebeee9;padding:8px;font:11px monospace;pointer-events:none';
  document.body.append(output);
  renderers.forEach(r => {r.info.autoReset = false;});
  let start = performance.now(), frames = 0, draws = 0, triangles = 0, submitMs = 0;
  let totalFrames = 0, totalDraws = 0;
  const timer = setInterval(() => {
    const now = performance.now(), seconds = (now - start) / 1000;
    const sample = {seconds, fps:frames / seconds, frames, draws, trianglesPerFrame:frames ? triangles / frames : 0,
      submitMsPerFrame:frames ? submitMs / frames : 0, totalFrames, totalDraws};
    output.dataset.sample = JSON.stringify(sample);
    output.textContent = `${sample.fps.toFixed(1)} preview fps · ${draws} view draws / ${seconds.toFixed(1)} s · ${sample.submitMsPerFrame.toFixed(1)} ms CPU/frame`;
    start = now;frames = draws = triangles = submitMs = 0;
  }, 2000);
  window.addEventListener('pagehide', () => clearInterval(timer), {once:true});
  return {
    begin() {renderers.forEach(r => r.info.reset());return performance.now();},
    end(began, viewCount) {
      if (!viewCount) return;
      frames++;draws += viewCount;totalFrames++;totalDraws += viewCount;
      submitMs += performance.now() - began;
      triangles += renderers.reduce((sum,r) => sum + r.info.render.triangles, 0);
      output.dataset.lastFrame = JSON.stringify(renderers.map(r => ({canvas:r.domElement.id,
        calls:r.info.render.calls, triangles:r.info.render.triangles, width:r.domElement.width, height:r.domElement.height})));
    }
  };
}
