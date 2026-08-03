#!/usr/bin/env node
/**
 * Programmatic Remotion renderer — replaces `npx remotion render` subprocess
 * calls from tools/video/video_compose.py with in-process @remotion/renderer
 * renderMedia() calls. Parameter contract is 1:1 with the old CLI call so the
 * Python side only changes the executable.
 *
 * Usage (equals-form args, Windows-safe):
 *   node scripts/render.mjs --entry=src/index.tsx --composition=Explainer \
 *     --output=renders/out.mp4 --props=<path> --public-dir=<path> \
 *     --width=1280 --height=720 --timeout=120000
 *
 * NOTE: bundle() starts an in-process webpack dev server that keeps the Node
 * process alive — always end with process.exit().
 */
// Load the vendored packages via CJS require: their package.json exports
// only conditionally expose ESM, and Node's named-export detection on the
// esbuild CJS bundles is unreliable. CJS require always resolves the
// `require` condition and avoids the issue entirely.
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {cpus} from 'node:os';
import path from 'node:path';

const require = createRequire(import.meta.url);
const {bundle} = require('@remotion/bundler');
const {renderMedia, selectComposition} = require('@remotion/renderer');

const args = process.argv.slice(2);

function get(name) {
  const prefix = `--${name}=`;
  const hit = args.find((a) => a.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : null;
}

const entry = get('entry');
const compositionId = get('composition');
const output = get('output');
const propsPath = get('props');
const publicDir = get('public-dir');
const width = get('width');
const height = get('height');
const timeoutMs = get('timeout');

if (!entry || !compositionId || !output) {
  console.error(
    'render.mjs requires --entry, --composition and --output (equals-form args).',
  );
  process.exit(1);
}

let inputProps = {};
if (propsPath) {
  try {
    inputProps = JSON.parse(readFileSync(propsPath, 'utf8'));
  } catch (err) {
    console.error(`render.mjs: cannot read props file ${propsPath}: ${err.message}`);
    process.exit(1);
  }
}

// --width/--height behave like the Remotion CLI: they override the
// composition's output dimensions directly.
const widthNum = width !== null ? Number(width) : NaN;
const heightNum = height !== null ? Number(height) : NaN;
if (width !== null && !Number.isFinite(widthNum)) {
  console.error(`render.mjs: invalid --width value "${width}"`);
  process.exit(1);
}
if (height !== null && !Number.isFinite(heightNum)) {
  console.error(`render.mjs: invalid --height value "${height}"`);
  process.exit(1);
}

try {
  console.error(`Bundling ${entry} ...`);
  const serveUrl = await bundle({
    entryPoint: path.resolve(entry),
    publicDir: publicDir ? path.resolve(publicDir) : undefined,
    onProgress: () => {},
  });

  console.error(`Selecting composition ${compositionId} ...`);
  const composition = await selectComposition({
    serveUrl,
    id: compositionId,
    inputProps,
  });

  if (Number.isFinite(widthNum)) composition.width = widthNum;
  if (Number.isFinite(heightNum)) composition.height = heightNum;

  console.error(
    `Rendering ${compositionId} (${composition.width}x${composition.height}, ` +
      `${composition.durationInFrames} frames @ ${composition.fps}fps) -> ${output}`,
  );
  await renderMedia({
    serveUrl,
    composition,
    codec: 'h264',
    outputLocation: path.resolve(output),
    inputProps,
    concurrency: Math.max(1, cpus().length - 1),
    crf: 18,
    jpegQuality: 80,
    overwrite: true,
    timeoutInMilliseconds: timeoutMs ? Number(timeoutMs) : 120000,
    onProgress: () => {},
  });

  console.error(`Render complete: ${output}`);
} catch (err) {
  console.error(
    `render.mjs failed: ${err?.message ?? err}\n` +
      (err?.stack ? `${String(err.stack).split('\n').slice(0, 6).join('\n')}` : ''),
  );
  process.exit(1);
}
process.exit(0);
