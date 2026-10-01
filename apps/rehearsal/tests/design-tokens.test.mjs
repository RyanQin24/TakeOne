/* The design system is one file or it is not a system.
 *
 * Every stylesheet under dist/ except takeone-tokens.css must express colour,
 * type, radius, elevation and motion through tokens. This test fails with a
 * file-and-line list, which doubles as the migration worklist.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { declarations, stylesheets } from './fixtures/css-scan.mjs';

const dist = new URL('../dist/', import.meta.url);
const TOKENS = 'takeone-tokens.css';

/* backdrop-filter survives in exactly one place: the scrim behind the command
 * palette and the setup sheet. Anything else is decoration. */
const SCRIM = /t1-palette|t1-sheet__scrim|t1-scrim/;

const NAMED_COLOURS = new Set([
  'white', 'black', 'red', 'green', 'blue', 'gray', 'grey', 'silver', 'orange',
  'yellow', 'purple', 'teal', 'navy', 'maroon', 'olive', 'lime', 'aqua', 'cyan',
  'fuchsia', 'magenta', 'gold', 'coral', 'salmon', 'crimson', 'indigo', 'violet',
  'khaki', 'tan', 'beige', 'ivory', 'snow', 'pink', 'brown', 'wheat', 'plum',
]);

const FUNCTIONAL_COLOUR = /(?:^|[\s,(])(rgba?|hsla?|hwb|lab|lch|oklab|oklch)\s*\(/i;
const HEX = /#[0-9a-fA-F]{3,8}(?![0-9a-zA-Z])/;
const GRADIENT = /(?:repeating-)?(?:linear|radial|conic)-gradient\s*\(/i;
const RAW_TIME = /(?:^|[\s,(])\d*\.?\d+m?s(?![0-9a-zA-Z])/i;
const RAW_EASING = /cubic-bezier\s*\(|\b(?:ease|ease-in|ease-out|ease-in-out|linear|step-start|step-end|steps)\b/i;

const isVar = (value) => /^var\(--t1-[a-z0-9-]+\)$/.test(value.trim());
const mentionsNamedColour = (value) =>
  value
    .toLowerCase()
    .split(/[^a-z-]+/)
    .some((word) => NAMED_COLOURS.has(word));

function violations(name, css) {
  const found = [];
  const at = (declaration, why) =>
    found.push(`${name}:${declaration.line}  ${declaration.property}: ${declaration.value}  — ${why}`);

  for (const declaration of declarations(css)) {
    const { property, value, selector, context } = declaration;
    const lower = value.toLowerCase();

    if (/!important/i.test(value)) at(declaration, 'no !important: fix the specificity instead');

    /* Colour. Only var(--t1-*) and color-mix() over one, plus the keywords that
     * carry no colour of their own. */
    const strippedMix = lower.replace(/color-mix\([^)]*\)/g, ' ');
    if (HEX.test(strippedMix) || FUNCTIONAL_COLOUR.test(strippedMix) || mentionsNamedColour(strippedMix)) {
      at(declaration, 'colour literal: use var(--t1-*) or color-mix() over one');
    }

    if (property === 'font-family' && !isVar(value) && value !== 'inherit') {
      at(declaration, 'font families are --t1-sans or --t1-mono');
    }

    if (property === 'font-size' && !isVar(value) && value !== 'inherit') {
      at(declaration, 'font sizes are --t1-text-* tokens');
    }

    if (/^border(-[a-z]+)?-radius$/.test(property) && !isVar(value) && value !== '0' && value !== 'inherit') {
      at(declaration, 'radii are --t1-r-* tokens');
    }

    if (property === 'box-shadow' && value !== 'none' && value !== 'var(--t1-shadow-overlay)') {
      at(declaration, 'the only elevation is var(--t1-shadow-overlay)');
    }

    if (GRADIENT.test(value)) at(declaration, 'no gradients');

    if (/backdrop-filter$/.test(property) && !SCRIM.test(selector) && !SCRIM.test(context)) {
      at(declaration, 'backdrop-filter belongs to the scrim only');
    }

    /* var(--t1-ease) contains the word "ease" and var(--t1-fast) stands in for a
     * time, so the motion checks look at what is left once tokens are removed. */
    const withoutTokens = lower.replace(/var\([^)]*\)/g, ' ');

    const killsMotion = /prefers-reduced-motion/.test(context);

    if (
      !killsMotion &&
      /^(transition|animation)(-duration|-delay)?$/.test(property) &&
      RAW_TIME.test(withoutTokens)
    ) {
      at(declaration, 'durations are --t1-fast, --t1-open or --t1-pulse');
    }

    if (/^(transition|animation)(-timing-function)?$/.test(property) && RAW_EASING.test(withoutTokens)) {
      at(declaration, 'easing is var(--t1-ease)');
    }
  }
  return found;
}

test('no stylesheet outside the token file defines a colour, face, size, radius, shadow, gradient or duration', async () => {
  const sheets = await stylesheets(dist, { exclude: [TOKENS] });
  assert.ok(sheets.length > 0, 'expected stylesheets under dist/');
  const found = sheets.flatMap((sheet) => violations(sheet.name, sheet.text));
  assert.deepEqual(
    found,
    [],
    `${found.length} design-token violations:\n` + found.join('\n'),
  );
});

test('the token file is tokens only — no selectors beyond :root, no rules', async () => {
  const css = await readTokens();
  const blocks = [...css.matchAll(/(^|\})\s*([^{}@]+)\{/g)].map((match) => match[2].trim());
  assert.deepEqual(
    blocks.filter((selector) => selector !== ':root'),
    [],
    'takeone-tokens.css may hold :root and @font-face and nothing else',
  );
});

test('every page loads the four stylesheets, in order, and no fifth', async () => {
  const { readdir, readFile } = await import('node:fs/promises');
  const pages = [];
  const walk = async (dir, prefix) => {
    for (const entry of await readdir(new URL(dir, dist), { withFileTypes: true })) {
      if (entry.isDirectory()) {
        await walk(dir + entry.name + '/', prefix + entry.name + '/');
      } else if (entry.name.endsWith('.html') && !entry.name.startsWith('_')) {
        pages.push({
          name: prefix + entry.name,
          html: await readFile(new URL(dir + entry.name, dist), 'utf8'),
        });
      }
    }
  };
  await walk('', '');
  assert.ok(pages.length > 0, 'expected pages under dist/');

  const wrong = [];
  for (const page of pages) {
    const links = [...page.html.matchAll(/<link[^>]+href="([^"]+\.css[^"]*)"/g)].map((m) => m[1]);
    const head = links.slice(0, 3).map((href) => href.replace(/\?.*$/, ''));
    if (
      head[0] !== '/takeone-tokens.css' ||
      head[1] !== '/takeone-base.css' ||
      head[2] !== '/takeone-components.css'
    ) {
      wrong.push(`${page.name}: first three stylesheets are ${JSON.stringify(head)}`);
    }
    if (links.length > 4) wrong.push(`${page.name}: loads ${links.length} stylesheets, at most 4 allowed`);
    if (/<style[\s>]/.test(page.html)) wrong.push(`${page.name}: ships an inline <style> block`);
  }
  assert.deepEqual(wrong, [], wrong.join('\n'));
});

async function readTokens() {
  const { readFile } = await import('node:fs/promises');
  return readFile(new URL(TOKENS, dist), 'utf8');
}
