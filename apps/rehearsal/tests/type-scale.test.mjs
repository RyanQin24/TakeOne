/* Twelve pixels is the floor and five sizes is the scale.
 *
 * The floor is what forces the density cut in §3.5: when 9px stops being
 * available the content stops fitting, and the copy has to go.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { declarations, stylesheets, tokenValues } from './fixtures/css-scan.mjs';

const dist = new URL('../dist/', import.meta.url);
const TOKENS = 'takeone-tokens.css';
const FLOOR_PX = 12;
const MAX_SIZES = 5;

const readTokens = async () => tokenValues(await readFile(new URL(TOKENS, dist), 'utf8'));

test('no type token is smaller than 12px', async () => {
  const tokens = await readTokens();
  const sizes = [...tokens].filter(([name]) => name.startsWith('--t1-text-'));
  assert.ok(sizes.length > 0, 'expected --t1-text-* tokens');
  const tooSmall = sizes
    .filter(([, value]) => {
      const px = /^(\d+(?:\.\d+)?)px$/.exec(value.trim());
      return px && Number(px[1]) < FLOOR_PX;
    })
    .map(([name, value]) => `${name}: ${value}`);
  assert.deepEqual(tooSmall, [], `below the ${FLOOR_PX}px floor:\n` + tooSmall.join('\n'));
});

test('the type scale has at most five sizes', async () => {
  const tokens = await readTokens();
  const scale = [...tokens.keys()].filter((name) => name.startsWith('--t1-text-'));
  assert.ok(
    scale.length <= MAX_SIZES,
    `${scale.length} type tokens, at most ${MAX_SIZES} allowed: ${scale.join(', ')}`,
  );
});

test('every font-size in the product resolves to one of those five', async () => {
  const tokens = await readTokens();
  const sheets = await stylesheets(dist, { exclude: [TOKENS] });
  const resolved = new Map();
  const unresolved = [];

  for (const sheet of sheets) {
    for (const declaration of declarations(sheet.text)) {
      if (declaration.property !== 'font-size') continue;
      const value = declaration.value.trim();
      if (value === 'inherit') continue;
      const reference = /^var\((--t1-[a-z0-9-]+)\)$/.exec(value);
      if (!reference || !tokens.has(reference[1])) {
        unresolved.push(`${sheet.name}:${declaration.line}  font-size: ${value}`);
        continue;
      }
      const size = tokens.get(reference[1]).trim();
      if (!resolved.has(size)) resolved.set(size, []);
      resolved.get(size).push(`${sheet.name}:${declaration.line}`);
    }
  }

  assert.deepEqual(
    unresolved,
    [],
    `${unresolved.length} font-size declarations do not name a type token:\n` + unresolved.join('\n'),
  );
  assert.ok(
    resolved.size <= MAX_SIZES,
    `${resolved.size} distinct rendered font sizes: ${[...resolved.keys()].join(', ')}`,
  );
});
