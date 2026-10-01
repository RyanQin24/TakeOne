/* A small CSS reader for the design-system tests.
 *
 * It is deliberately not a real parser. It strips comments while preserving
 * line numbers, then walks characters tracking brace depth, paren depth and
 * quotes so that a `;` inside `url(data:...)` or a `:` inside a selector does
 * not split a declaration. That is enough to answer the only questions the
 * enforcement tests ask: which property, which value, which line, which
 * selector.
 */
import { readdir, readFile } from 'node:fs/promises';

export function stripComments(css) {
  let out = '';
  let i = 0;
  while (i < css.length) {
    if (css[i] === '/' && css[i + 1] === '*') {
      const end = css.indexOf('*/', i + 2);
      const stop = end === -1 ? css.length : end + 2;
      for (let k = i; k < stop; k += 1) out += css[k] === '\n' ? '\n' : ' ';
      i = stop;
      continue;
    }
    out += css[i];
    i += 1;
  }
  return out;
}

export function declarations(css) {
  const clean = stripComments(css);
  const found = [];
  const stack = [];
  let buffer = '';
  let bufferLine = 1;
  let line = 1;
  let parens = 0;
  let quote = '';

  const flush = () => {
    const text = buffer.trim();
    buffer = '';
    if (!text) return;
    const colon = text.indexOf(':');
    if (colon < 0) return;
    found.push({
      property: text.slice(0, colon).trim().toLowerCase(),
      value: text.slice(colon + 1).trim(),
      line: bufferLine,
      selector: stack.length ? stack[stack.length - 1] : '',
      context: stack.join(' > '),
    });
  };

  for (let i = 0; i < clean.length; i += 1) {
    const ch = clean[i];
    if (ch === '\n') {
      line += 1;
      if (!buffer.trim()) bufferLine = line;
      buffer += ' ';
      continue;
    }
    if (quote) {
      buffer += ch;
      if (ch === quote && clean[i - 1] !== '\\') quote = '';
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      buffer += ch;
      continue;
    }
    if (ch === '(') parens += 1;
    if (ch === ')') parens = Math.max(0, parens - 1);
    if (parens === 0) {
      if (ch === '{') {
        stack.push(buffer.trim().replace(/\s+/g, ' '));
        buffer = '';
        bufferLine = line;
        continue;
      }
      if (ch === '}') {
        flush();
        stack.pop();
        bufferLine = line;
        continue;
      }
      if (ch === ';') {
        flush();
        bufferLine = line;
        continue;
      }
    }
    if (!buffer.trim() && /\s/.test(ch)) {
      bufferLine = line;
      continue;
    }
    buffer += ch;
  }
  flush();
  return found;
}

export async function stylesheets(root, { exclude = [] } = {}) {
  const found = [];
  const walk = async (dir, prefix) => {
    const entries = await readdir(new URL(dir, root), { withFileTypes: true });
    for (const entry of entries) {
      const name = prefix + entry.name;
      if (entry.isDirectory()) {
        await walk(dir + entry.name + '/', name + '/');
        continue;
      }
      if (!entry.name.endsWith('.css')) continue;
      if (exclude.includes(name)) continue;
      found.push({ name, text: await readFile(new URL(dir + entry.name, root), 'utf8') });
    }
  };
  await walk('', '');
  found.sort((a, b) => a.name.localeCompare(b.name));
  return found;
}

export function tokenValues(css) {
  const values = new Map();
  for (const declaration of declarations(css)) {
    if (declaration.property.startsWith('--')) values.set(declaration.property, declaration.value);
  }
  return values;
}
