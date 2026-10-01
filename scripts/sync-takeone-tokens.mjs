/* Mirror the canonical TakeOne tokens into the editor.
 *
 * The single source of truth is apps/rehearsal/dist/takeone-tokens.css. The
 * editor is a separate Vite application served by a different process, so it
 * cannot link that file at runtime; this script copies it verbatim into
 * apps/editor/src/styles/takeone-tokens.css behind a generated banner.
 *
 *   node scripts/sync-takeone-tokens.mjs           write the copy
 *   node scripts/sync-takeone-tokens.mjs --check   fail if the copy is stale
 *
 * It is wired into apps/rehearsal's `check` script and apps/editor's `build`,
 * so a stale copy cannot survive a normal development loop. The earlier version
 * of this script was deliberately not wired into anything, and the copy drifted
 * by nineteen of twenty-five shared colour values in three days.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, "../apps/rehearsal/dist/takeone-tokens.css");
const target = resolve(here, "../apps/editor/src/styles/takeone-tokens.css");

const BANNER = `/* GENERATED — do not edit by hand.
 *
 * Mirrored byte-for-byte from apps/rehearsal/dist/takeone-tokens.css by
 * scripts/sync-takeone-tokens.mjs. That file is the single source of truth for
 * TakeOne colour, type, space and motion. Fonts are served from
 * apps/editor/public/fonts, which holds the same files as
 * apps/rehearsal/dist/fonts.
 *
 * Regenerate with:  node scripts/sync-takeone-tokens.mjs
 */

`;

const canonical = readFileSync(source, "utf8");
if (!canonical.includes(":root")) throw new Error(`No :root token block in ${source}`);
const expected = BANNER + canonical;

if (process.argv.includes("--check")) {
  let actual = "";
  try {
    actual = readFileSync(target, "utf8");
  } catch {
    actual = "";
  }
  if (actual !== expected) {
    process.stderr.write(
      "apps/editor/src/styles/takeone-tokens.css is stale.\n" +
        "Run: node scripts/sync-takeone-tokens.mjs\n",
    );
    process.exit(1);
  }
  process.stdout.write("takeone tokens in sync\n");
} else {
  writeFileSync(target, expected, "utf8");
  process.stdout.write(`wrote ${target}\n`);
}
