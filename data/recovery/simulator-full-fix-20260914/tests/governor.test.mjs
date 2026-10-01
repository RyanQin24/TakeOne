import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {createGovernor, stepGovernor, stoppingCorridor} from '../dist/governor.js';

const here = dirname(fileURLToPath(import.meta.url));
const cases = JSON.parse(readFileSync(join(here, 'governor-trace.json'), 'utf8'));

// Must match tests/make_governor_trace.py exactly, including using i * dt
// rather than an accumulated sum.
function rateAt(schedule, t) {
  let value = schedule[0][1];
  for (const [when, rate] of schedule) if (t >= when) value = rate;
  return value;
}

test('the browser governor reproduces the Python one step for step', () => {
  assert.ok(cases.length >= 4, 'need the full set of cases');
  for (const c of cases) {
    const g = createGovernor(c.limits, c.duration);
    let worst = 0;
    for (let i = 0; i < c.trace.length; i++) {
      const out = stepGovernor(g, c.dt, rateAt(c.schedule, i * c.dt));
      const want = c.trace[i];
      worst = Math.max(worst,
        Math.abs(out.s - want[0]), Math.abs(out.sdot - want[1]),
        Math.abs(out.sddot - want[2]), Math.abs(out.sdddot - want[3]));
    }
    assert.ok(worst < 1e-9,
      `case ${c.name}: browser and Python governors disagree by ${worst.toExponential(2)}`);
  }
});

test('the stopping corridor agrees across the two implementations', () => {
  for (const c of cases) {
    const g = createGovernor(c.limits, c.duration);
    for (let i = 0; i < c.trace.length; i++) {
      stepGovernor(g, c.dt, rateAt(c.schedule, i * c.dt));
    }
    const mine = stoppingCorridor(g);
    assert.ok(Math.abs(mine.phase - c.stopping_corridor.phase) < 1e-9,
      `case ${c.name}: corridor phase ${mine.phase} vs ${c.stopping_corridor.phase}`);
  }
});

test('a stop takes time and travels a corridor', () => {
  const g = createGovernor({max_rate: 0.2, max_accel: 0.4, max_jerk: 2.0,
                            tau_accel: 0.12, tau_jerk: 0.06}, 5);
  for (let i = 0; i < 400; i++) stepGovernor(g, 0.01, 0.2);
  assert.ok(g.sdot > 0.1, 'the governor should be up to speed');
  const before = g.s;
  let n = 0;
  while (g.sdot > 1e-9 && n < 5000) { stepGovernor(g, 0.01, 0); n += 1; }
  assert.ok(n > 5, 'stopping must take more than one frame; a freeze is not braking');
  assert.ok(g.s - before > 1e-4, 'the phase must advance while braking');
});

test('the phase never runs backwards or past one', () => {
  const g = createGovernor({max_rate: 0.5, max_accel: 0.6, max_jerk: 4.0,
                            tau_accel: 0.1, tau_jerk: 0.05}, 2);
  let previous = 0;
  for (let i = 0; i < 2000; i++) {
    const out = stepGovernor(g, 0.01, i % 200 < 100 ? 0.5 : 0);
    assert.ok(out.s >= previous - 1e-12, 'phase went backwards');
    assert.ok(out.s <= 1 + 1e-12, 'phase exceeded one');
    assert.ok(out.sdot >= -1e-12, 'phase rate went negative');
    previous = out.s;
  }
});

test('an out-of-range timestep is rejected rather than silently clamped', () => {
  const g = createGovernor({max_rate: 0.2, max_accel: 0.4, max_jerk: 2.0,
                            tau_accel: 0.12, tau_jerk: 0.06}, 5);
  assert.throws(() => stepGovernor(g, 0.2, 0.2), /timestep/);
  assert.throws(() => stepGovernor(g, 0, 0.2), /timestep/);
});
