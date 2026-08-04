#!/usr/bin/env node
/**
 * Build the vendored HyperFrames monorepo under vendor/hyperframes/packages/.
 *
 * The vendored copy is the full source checkout (each package ships its own
 * src/), so local modifications require rebuilding dist. This script replays
 * the upstream build chain WITHOUT bun (the monorepo's package manager)
 * using node/npx:
 *
 *   order (dependency topo-sorted):
 *     parsers → lint / studio-server / shader-transitions
 *             → core (runtime artifact + tsc + esm rewrite)
 *             → sdk / player / engine
 *             → producer (runtime modular + build.mjs)
 *             → cli (tsup + runtime + beat-analyzer + copy)
 *
 * `tsc`/`tsup`/`tsx` resolve from the repo-root node_modules/.bin; on Windows
 * the .bin dir is prepended to PATH because several upstream scripts invoke
 * bare `tsc` via child_process (build.mjs) and would fail without it.
 */
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';

const ROOT = path.resolve(import.meta.dirname, '..');
const PKGS = path.join(ROOT, 'vendor', 'hyperframes', 'packages');
const BIN = path.join(ROOT, 'node_modules', '.bin');

function run(cwd, args, extraEnv = {}) {
  console.log(`[hf-vendor] ${path.relative(PKGS, cwd) || '(root)'} $ ${args.join(' ')}`);
  execFileSync(args[0], args.slice(1), {
    cwd,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env: {
      ...process.env,
      ...extraEnv,
      PATH: `${BIN}${path.delimiter}${process.env.PATH ?? ''}`,
    },
  });
}

function pkg(name) {
  return path.join(PKGS, name);
}

// ---- leaf tsup packages ----
for (const name of ['parsers', 'lint', 'studio-server', 'shader-transitions']) {
  run(pkg(name), ['npx', 'tsup']);
}

// ---- core: runtime artifact + position-edits + tsc + esm rewrite ----
const core = pkg('core');
run(core, ['npx', 'tsx', 'scripts/build-hyperframes-runtime-artifact.ts']);
run(core, ['npx', 'tsx', 'scripts/build-position-edits-render.ts']);
run(core, ['npx', 'tsc']);
run(core, ['npx', 'tsx', 'scripts/rewrite-esm-extensions.ts']);

// ---- tsc packages ----
for (const name of ['sdk', 'engine']) {
  run(pkg(name), ['npx', 'tsc']);
}
// player: tsup (runtime-pin verify is upstream-only, skip)
run(pkg('player'), ['npx', 'tsup']);
// studio: vite + tsup — cli's build-copy waits for studio dist
run(pkg('studio'), ['npx', 'vite', 'build']);
run(pkg('studio'), ['npx', 'tsup']);

// ---- producer ----
const producer = pkg('producer');
run(producer, ['node', 'scripts/build-fonts.mjs']);
run(producer, ['npx', 'tsx', 'scripts/build-hf-early-stub.ts']);
// modular runtime variant, run from the monorepo root (upstream:
// `bun run --cwd ../.. build:hyperframes-runtime:modular`)
run(pkg('..'), ['npx', 'tsx', 'packages/core/scripts/build-hyperframes-runtime-artifact.ts'], {
  SANDBOX_RUNTIME_VARIANT: 'modular',
});
run(producer, ['node', 'build.mjs']);

// ---- cli ----
const cli = pkg('cli');
run(cli, ['node', 'scripts/build-fonts.mjs']);
run(cli, ['npx', 'tsup']);
run(cli, ['npx', 'tsx', 'scripts/build-runtime.ts']);
run(cli, ['node', 'scripts/build-beat-analyzer.mjs']);
run(cli, ['node', 'scripts/build-copy.mjs']);

console.log('[hf-vendor] HyperFrames vendor build complete.');
