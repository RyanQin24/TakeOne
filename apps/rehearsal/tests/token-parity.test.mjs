/* The editor's token file is a generated copy, and a copy that can drift is
 * how 173 token names and 28 conflicting values happened. This test is what
 * makes the generator's wiring unnecessary to remember.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = new URL('../dist/takeone-tokens.css', import.meta.url);
const copy = new URL('../../editor/src/styles/takeone-tokens.css', import.meta.url);

test('the editor token copy is byte-identical to the rehearsal source', async () => {
  const [canonical, mirrored] = await Promise.all([readFile(source, 'utf8'), readFile(copy, 'utf8')]);
  assert.match(mirrored, /^\/\* GENERATED — do not edit by hand\./, 'the copy must carry the generated banner');
  assert.match(
    mirrored,
    /scripts\/sync-takeone-tokens\.mjs/,
    'the banner must name the command that regenerates it',
  );
  assert.ok(
    mirrored.endsWith(canonical),
    'the editor copy is stale — run `node scripts/sync-takeone-tokens.mjs` from the repository root',
  );
});
