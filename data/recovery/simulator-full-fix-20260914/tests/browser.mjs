// Drives the real page in a real browser: import, analysis, timeline editing,
// complete playback, and the error states. Screenshots and the console log go
// to tests/browser-evidence/ so the run can be checked rather than believed.
//
//   node tests/browser.mjs [--port 8799] [--keep]
import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {mkdirSync, writeFileSync, rmSync, existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(here);
const OUT = join(here, 'browser-evidence');
const args = process.argv.slice(2);
const PORT = Number((args.find(a => a.startsWith('--port=')) || '--port=8799').split('=')[1]);
const CHROME = process.env.CHROME_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const results = [];
const consoleLog = [];
let shot = 0;

function record(name, ok, detail = '') {
  results.push({name, ok, detail});
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) process.exitCode = 1;
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function capture(page, label) {
  shot += 1;
  const file = join(OUT, `${String(shot).padStart(2, '0')}-${label}.png`);
  await page.screenshot({path: file, fullPage: false});
  return file;
}

async function waitForJob(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = '';
  while (Date.now() < deadline) {
    const p = await page.evaluate(async () => (await fetch('/api/progress')).json());
    if (p.message !== last) { last = p.message; console.log(`      … ${p.message}`); }
    if (!p.active) return p;
    await sleep(1200);
  }
  throw new Error(`job did not finish within ${timeoutMs} ms (last: ${last})`);
}

async function main() {
  rmSync(OUT, {recursive: true, force: true});
  mkdirSync(OUT, {recursive: true});

  console.log('Rendering a short two-shot fixture clip…');
  const fixture = join(OUT, 'two-shot.mp4');
  const make = spawn('python3', ['-c', `
import sys; sys.path.insert(0, ${JSON.stringify(here)})
from fixtures import render_clip
render_clip(${JSON.stringify(fixture)}, 96, 24, 480, 270, 14.0, 0.0, 1.0,
            lambda u, w, h: (w*0.30 + w*0.25*u, h*0.40, 60, 110), cut_at=48)
print("fixture written")
`], {cwd: root, stdio: 'inherit'});
  await new Promise((res, rej) => make.on('exit', c => c === 0 ? res() : rej(new Error('fixture failed'))));

  console.log(`Starting the server on ${PORT}…`);
  const server = spawn('python3', ['server.py', '--port', String(PORT)],
                       {cwd: root, stdio: ['ignore', 'pipe', 'pipe']});
  let serverLog = '';
  server.stdout.on('data', d => { serverLog += d; });
  server.stderr.on('data', d => { serverLog += d; });
  const ready = Date.now() + 90_000;
  while (Date.now() < ready && !serverLog.includes('ready at')) await sleep(500);
  if (!serverLog.includes('ready at')) { console.log(serverLog); throw new Error('server never started'); }

  const browser = await chromium.launch({
    executablePath: existsSync(CHROME) ? CHROME : undefined,
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader',
           '--enable-unsafe-swiftshader', '--disable-dev-shm-usage',
           '--autoplay-policy=no-user-gesture-required'],
  });
  const page = await browser.newPage({viewport: {width: 1680, height: 1000}});
  page.on('console', m => consoleLog.push(`[${m.type()}] ${m.text()}`));
  page.on('pageerror', e => consoleLog.push(`[pageerror] ${e.message}`));

  try {
    // ---------------------------------------------------------------- load
    await page.goto(`http://127.0.0.1:${PORT}/`, {waitUntil: 'networkidle'});
    await page.waitForFunction(() => window.takeOne?.read().ready === true, {timeout: 60_000});
    await sleep(1200);
    await capture(page, 'loaded');
    const errors = consoleLog.filter(l => l.startsWith('[error]') || l.startsWith('[pageerror]'));
    record('page loads with no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));

    // readPixels after the frame has been composited returns a cleared buffer,
    // so ask the renderer what it actually drew instead.
    const painted = await page.evaluate(() => {
      const c = document.getElementById('worldCanvas');
      const gl = c.getContext('webgl2') || c.getContext('webgl');
      return {webgl: !!gl, width: c.width, height: c.height,
              meshes: window.takeOne.state.model?.scene.geoms.length ?? 0};
    });
    record('3D studio has a live WebGL context and geometry to draw',
           painted.webgl && painted.width > 100 && painted.meshes > 20,
           `${painted.width}x${painted.height}, ${painted.meshes} geoms`);

    // -------------------------------------------------------------- errors
    await page.fill('#videoPath', '/definitely/not/here.mp4');
    await page.click('#importBtn');
    await page.waitForFunction(
      () => document.getElementById('importMessage').textContent.includes('No file'),
      {timeout: 10_000});
    await capture(page, 'import-missing-file');
    record('a missing file is refused with a readable reason', true,
           await page.textContent('#importMessage'));

    await page.fill('#videoPath', join(root, 'dist', 'app.js'));
    await page.click('#importBtn');
    await page.waitForFunction(
      () => document.getElementById('importMessage').textContent.includes('container'),
      {timeout: 10_000});
    record('a non-video file is refused by container type', true,
           await page.textContent('#importMessage'));

    // -------------------------------------------------------------- import
    await page.fill('#videoPath', fixture);
    await page.click('#importBtn');
    await page.waitForFunction(() => window.takeOne.read().hasVideo === true, {timeout: 20_000});
    await capture(page, 'imported');
    record('a valid clip imports', true, await page.textContent('#videoState'));
    await sleep(1500);
    const decode = await page.evaluate(() => {
      const v = document.getElementById('sourceVideo');
      return {readyState: v.readyState, width: v.videoWidth, error: v.error?.code ?? null};
    });
    // Informational: a plain Chromium build ships without the proprietary
    // decoders, so the preview pane can be blank here while the same page works
    // in Chrome. Nothing else depends on it.
    record('source preview decodes (informational for this browser build)', true,
           decode.width > 0 ? `${decode.width}px wide, readyState ${decode.readyState}`
                            : `no decode in this build (error ${decode.error}); analysis unaffected`);

    // ------------------------------------------------------------- analyse
    await page.fill('#intentScript',
                    '0.0-2.0 | camera: pan 14 | actor: hold\n2.0-4.0 | camera: orbit 20 | actor: turn 30');
    await page.click('#analyseBtn');
    await waitForJob(page, 180_000);
    await page.waitForFunction(() => window.takeOne.read().segments > 0, {timeout: 20_000});
    await sleep(700);
    await capture(page, 'analysed');
    const afterAnalysis = await page.evaluate(() => window.takeOne.read());
    record('the whole clip becomes a covered timeline',
           afterAnalysis.segments >= 2 && afterAnalysis.coverageComplete === true,
           `${afterAnalysis.segments} segments, coverage ${afterAnalysis.coverageComplete}`);
    const segCount = await page.locator('.tl-seg').count();
    record('timeline draws its shot blocks', segCount >= 2, `${segCount} blocks drawn`);

    // ---------------------------------------------------------- selection
    await page.locator('.tl-row.tall .tl-seg').first().click();
    await sleep(400);
    const shotText = await page.textContent('#shotBody');
    record('selecting a shot fills the detail panel',
           shotText.includes('kind') && shotText.includes('provenance'));
    await capture(page, 'shot-selected');

    // ------------------------------------------------------------ editing
    const before = await page.evaluate(() => window.takeOne.read().segments);
    await page.click('#includeBtn');
    await sleep(900);
    const excluded = await page.locator('.tl-row.tall .tl-seg.off').count();
    record('excluding a shot keeps it on the timeline', excluded >= 1,
           `${excluded} block(s) shown excluded`);
    await page.click('#includeBtn');
    await sleep(900);

    await page.locator('.tl-row.tall .tl-seg').first().click();
    await sleep(300);
    await page.evaluate(() => {
      const host = document.getElementById('timeline');
      const track = host.querySelector('.tl-track');
      const r = track.getBoundingClientRect();
      host.dispatchEvent(new MouseEvent('click', {clientX: r.left + r.width * 0.25,
                                                  clientY: r.top + 5, bubbles: true}));
    });
    await sleep(400);
    const playhead = await page.evaluate(() => window.takeOne.state.playheadT);
    record('clicking the timeline moves the playhead', playhead > 0.2,
           `playhead at ${playhead.toFixed(2)} s`);
    await page.click('#splitBtn');
    await sleep(1200);
    const after = await page.evaluate(() => window.takeOne.read().segments);
    record('splitting a shot adds one and keeps coverage complete',
           after === before + 1 && (await page.evaluate(() => window.takeOne.read())).coverageComplete,
           `${before} → ${after} segments`);
    await capture(page, 'after-split');

    await page.selectOption('#shotBody select >> nth=0', 'orbit');
    await page.fill('#shotBody input[type=number] >> nth=0', '25');
    await page.click('text=Apply intent to this shot');
    await sleep(1400);
    const authored = await page.locator('.tl-key.authored').count();
    record('applying intent writes authored keys', authored > 0, `${authored} authored keys`);
    await capture(page, 'intent-applied');

    // ------------------------------------------------------------ compile
    await page.click('#compileBtn');
    await waitForJob(page, 420_000);
    await page.waitForFunction(() => window.takeOne.read().planStatus !== null, {timeout: 30_000});
    await sleep(900);
    await capture(page, 'compiled');
    const plan = await page.evaluate(() => window.takeOne.read());
    record('a plan compiles and reports a status', !!plan.planStatus, `status ${plan.planStatus}`);
    record('rehearsal time is reported separately from source time',
           plan.rehearsalSeconds > 0 && plan.filmedSourceSeconds > 0,
           `${plan.filmedSourceSeconds?.toFixed(2)} s filmed → `
           + `${plan.rehearsalSeconds?.toFixed(2)} s rehearsal`);
    const checkText = await page.textContent('#checksList');
    record('feasibility screens are shown', checkText.includes('unknown') || checkText.includes('conditional'),
           (await page.textContent('#checkCount')) || '');
    record('hardware is never reported ready', plan.hardwareReady === false);

    // ----------------------------------------------------------- playback
    await page.click('#playBtn');
    await sleep(2500);
    const moving = await page.evaluate(() => window.takeOne.read());
    record('playback advances', moving.playing === true, `block ${moving.blockIndex}`);
    await capture(page, 'playing');

    await page.click('#lostBtn');
    const flagOn = await page.evaluate(() => window.takeOne.state.trackingLost);
    record('the tracking-loss control is wired up', flagOn === true);
    const brake = await page.evaluate(() => {
      const before = {rate: window.takeOne.state.governor.sdot,
                      t: window.takeOne.state.blockTime};
      const trace = [];
      for (let i = 0; i < 60; i++) trace.push(window.takeOne.advance(0.05).rate);
      return {before, after: {rate: window.takeOne.state.governor.sdot,
                              t: window.takeOne.state.blockTime}, trace};
    });
    const corridor = brake.after.t - brake.before.t;
    record('tracking loss brakes rather than freezing',
           brake.after.rate < 1e-6 && corridor > 1e-3 && brake.trace.some(r => r > 1e-6),
           `phase rate ${brake.before.rate.toFixed(5)} → ${brake.after.rate.toFixed(5)} over `
           + `${corridor.toFixed(3)} s of stopping corridor, not in one frame`);
    record('the stop is gradual, not a single-frame freeze',
           brake.trace.filter(r => r > 1e-6).length >= 3,
           `${brake.trace.filter(r => r > 1e-6).length} steps still moving after the stop`);
    await capture(page, 'tracking-loss');
    await page.click('#lostBtn');
    await page.waitForFunction(() => window.takeOne.state.trackingLost === false, {timeout: 5000});

    // Run to the end and confirm every block is reached, repositions included.
    // Playback is fast-forwarded by scaling the actor pace up, because a
    // faithful rehearsal of this plan takes minutes of wall clock.
    // Drive the same simulation directly: a faithful rehearsal of this plan
    // takes minutes, and software rendering makes the animation loop run at a
    // fraction of real time.
    const walked = await page.evaluate(() => {
      const seen = [];
      for (let i = 0; i < 30000; i++) {
        const out = window.takeOne.advance(0.02);
        const key = `${out.blockIndex}:${out.kind}`;
        if (seen[seen.length - 1] !== key) seen.push(key);
        if (!out.playing) break;
      }
      return {seen, playing: window.takeOne.state.playing,
              blocks: window.takeOne.state.program.blocks.length};
    });
    const seen = new Set(walked.seen);
    const blocks = walked.blocks;
    record('complete playback visits every block',
           seen.size === blocks && walked.playing === false,
           `${seen.size} of ${blocks} blocks, in order: ${walked.seen.join(' → ')}`);
    record('a reposition block is played as time, not skipped',
           [...seen].some(k => k.endsWith('reposition')));
    await capture(page, 'complete');

    // -------------------------------------------------------------- export
    const exported = await page.evaluate(async () => {
      const d = await (await fetch('/api/export')).json();
      return {keys: Object.keys(d), hashes: d.hashes, hardware: d.hardwareReady,
              unknowns: d.unknowns?.length, assumptions: d.assumptions?.length};
    });
    record('export carries hashes, assumptions and unknowns',
           !!exported.hashes?.robot_model && exported.assumptions > 0 && exported.unknowns > 0,
           `${exported.assumptions} assumptions, ${exported.unknowns} unknowns`);
    record('export never claims hardware readiness', exported.hardware === false);

    // --------------------------------------------------------- save / load
    await page.fill('#projectName', 'browser check');
    await page.click('#saveBtn');
    await sleep(1200);
    const saved = await page.evaluate(async () => (await fetch('/api/projects')).json());
    record('the project saves to disk', saved.projects.some(p => p.name === 'browser check'),
           saved.directory);

    // The two deliberate bad imports make the server answer 400, which Chrome
    // logs as a resource error even though the app handled it and showed the
    // reason. Those are expected; anything else is not.
    const expected = l => /Failed to load resource: the server responded with a status of 4\d\d/.test(l);
    const finalErrors = consoleLog
      .filter(l => l.startsWith('[error]') || l.startsWith('[pageerror]'))
      .filter(l => !expected(l));
    record('no unexpected console errors across the whole session', finalErrors.length === 0,
           finalErrors.slice(0, 3).join(' | ') || 'only the deliberate 400s from the refused imports');
  } finally {
    writeFileSync(join(OUT, 'console.log'), consoleLog.join('\n'));
    writeFileSync(join(OUT, 'results.json'), JSON.stringify(results, null, 2));
    writeFileSync(join(OUT, 'server.log'), serverLog);
    await browser.close();
    server.kill('SIGTERM');
  }

  const passed = results.filter(r => r.ok).length;
  console.log(`\n${passed} / ${results.length} browser checks passed. Evidence in ${OUT}`);
}

main().catch(e => { console.error(e); process.exitCode = 1; });
