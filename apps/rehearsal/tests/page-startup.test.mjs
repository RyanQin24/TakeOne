import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// These controls are wired before the first model request. Removing them from
// markup prevents the entire simulator from loading, even when API tests pass.
for (const [page, ids] of [
  ['index.html', ['saveBtn', 'openBtn', 'openFile', 'exportBtn']],
  ['motor-test.html', ['referenceBtn', 'referenceCard', 'exportBtn']],
]) {
  test(`${page} retains controls required for simulator startup`, () => {
    const html = readFileSync(new URL(`../dist/${page}`, import.meta.url), 'utf8');
    for (const id of ids) {
      assert.equal((html.match(new RegExp(`id="${id}"`, 'g')) || []).length, 1,
        `${id} must exist exactly once before the simulator module starts`);
    }
  });
}
