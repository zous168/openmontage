#!/usr/bin/env node
/**
 * Build the vendored Remotion packages under vendor/remotion/packages/.
 *
 * Replicates the official per-package build (tsgo -d → CJS + d.ts, bun
 * bundle.ts → ESM) using plain tsc 5.9 + esbuild. Differences are
 * documented in vendor/remotion/README.md (vendor-patch.d.ts, toolchain).
 *
 * Per package:
 *   - CJS bundle  → the package.json `main` target (dist/index.js or dist/cjs/index.js)
 *   - ESM bundle  → the package.json `module` target (only for packages that ship ESM)
 *   - sub-entries → each exports key (besides ./package.json) with a JS target,
 *                   entry file src/<name>.ts(x) or src/<name>/index.ts(x)
 *   - d.ts        → tsc -p <pkg>/tsconfig.json (only when the package declares types)
 *
 * externals: every package dependency + Node builtins (esbuild packages:'external').
 * Build order: topological sort over the remotion dependency graph so tsc can
 * resolve d.ts of already-built packages.
 */
import {execFileSync} from 'node:child_process';
import {builtinModules} from 'node:module';
import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(import.meta.url);

const ROOT = path.resolve(import.meta.dirname, '..');
const VENDOR = path.join(ROOT, 'vendor', 'remotion');
const PACKAGES_DIR = path.join(VENDOR, 'packages');
const CONFIG = JSON.parse(fs.readFileSync(path.join(VENDOR, 'vendor.config.json'), 'utf8'));

let ESBUILD;
try {
  ESBUILD = require('esbuild');
} catch (err) {
  console.error(
    '[build-vendor] esbuild is not installed. Run `npm install` first ' +
      '(esbuild comes in as a dependency of the vendored @remotion/bundler).\n' +
      `  detail: ${err.message}`,
  );
  process.exit(1);
}
const TSC_BIN = path.join(ROOT, 'node_modules', 'typescript', 'bin', 'tsc');
if (!fs.existsSync(TSC_BIN)) {
  console.error(
    '[build-vendor] typescript is not installed. Run `npm install` first.',
  );
  process.exit(1);
}

const SKIP_BUILD = new Set(['compositor-win32-x64-msvc']);

/**
 * Per-package extra runtime files that the main bundle references via
 * `require.resolve('./...')` (esbuild cannot inline those) — they must
 * exist next to the bundle on disk. Mirrors upstream's tsc output, which
 * emits every src file.
 */
const RUNTIME_REQUIRE_FILES = {
  bundler: [
    ['src/setup-environment.ts', 'dist/setup-environment.js'],
    ['src/setup-sequence-stack-traces.ts', 'dist/setup-sequence-stack-traces.js'],
    ['src/fast-refresh/loader.ts', 'dist/fast-refresh/loader.js'],
    ['src/fast-refresh/runtime.ts', 'dist/fast-refresh/runtime.js'],
    ['src/esbuild-loader/index.ts', 'dist/esbuild-loader/index.js'],
  ],
};

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function log(msg) {
  console.log(`[build-vendor] ${msg}`);
}

function findEntryFile(dir, name) {
  // name may contain a slash (e.g. worker-server-entry); try <name>.ts,
  // <name>.tsx, <name>/index.ts, <name>/index.tsx in that order.
  for (const cand of [
    path.join(dir, `${name}.ts`),
    path.join(dir, `${name}.tsx`),
    path.join(dir, name, 'index.ts'),
    path.join(dir, name, 'index.tsx'),
  ]) {
    if (fs.existsSync(cand)) return cand;
  }
  return null;
}

/** Resolve the JS output targets of an exports value → [{outfile, format}] */
function jsTargetsForExport(value, pkgDir) {
  if (typeof value === 'string') return jsTargetsForExport({default: value}, pkgDir);
  const seen = new Set();
  const out = [];
  for (const key of ['module', 'import', 'require', 'default']) {
    const target = value[key];
    if (typeof target !== 'string' || target.endsWith('.d.ts') || seen.has(target)) continue;
    seen.add(target);
    out.push({outfile: path.join(pkgDir, target), format: target.endsWith('.mjs') ? 'esm' : 'cjs'});
  }
  return out;
}

/** Build one entry with esbuild; returns true on success */
function esbuildBundle({entryPoint, outfile, format}) {
  try {
    ESBUILD.buildSync({
      entryPoints: [entryPoint],
      outfile,
      bundle: true,
      format,
      platform: 'neutral',
      target: 'es2020',
      jsx: 'automatic',
      packages: 'external', // all package.json deps stay external
      external: builtinModules.concat(builtinModules.map((m) => `node:${m}`)),
      logLevel: 'warning',
    });
    return true;
  } catch (err) {
    log(`  FAIL (esbuild ${format}): ${err.errors?.[0]?.text ?? err.message}`);
    return false;
  }
}

/**
 * Copy the toolchain-compat ambient patch (Timer / Headers.entries, see
 * vendor/remotion/README.md) into the package src so tsc sees it.
 */
function ensureVendorPatch(pkgDir) {
  const template = path.join(VENDOR, 'vendor-patch.d.ts');
  if (!fs.existsSync(template)) return;
  // Always overwrite: the template is the single source of truth.
  fs.copyFileSync(template, path.join(pkgDir, 'src', 'vendor-patch.d.ts'));
}

/** tsc -d for packages that declare types; returns true on success */
function emitDeclarations(pkgDir) {
  const tsconfig = path.join(pkgDir, 'tsconfig.json');
  try {
    execFileSync(process.execPath, [TSC_BIN, '-p', tsconfig], {cwd: pkgDir, stdio: 'inherit'});
    return true;
  } catch {
    return false;
  }
}

/** Topological order over the remotion/@remotion dependency graph */
function buildOrder() {
  const pkgs = CONFIG.packages.filter((p) => !SKIP_BUILD.has(p));
  const depsOf = (p) => {
    const pkg = JSON.parse(fs.readFileSync(path.join(PACKAGES_DIR, p, 'package.json'), 'utf8'));
    const all = {
      ...(pkg.dependencies || {}),
      ...(pkg.peerDependencies || {}),
      ...(pkg.optionalDependencies || {}),
    };
    return Object.keys(all).filter(
      (d) => d === 'remotion' || (d.startsWith('@remotion/') && pkgs.includes(d.slice('@remotion/'.length))),
    );
  };
  const order = [];
  const visited = new Set();
  const visit = (p) => {
    if (visited.has(p)) return;
    visited.add(p);
    for (const d of depsOf(p)) {
      const depDir = d === 'remotion' ? 'core' : d.slice('@remotion/'.length);
      if (pkgs.includes(depDir)) visit(depDir);
    }
    order.push(p);
  };
  pkgs.forEach(visit);
  return order;
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

const failures = [];

for (const pkgName of buildOrder()) {
  const pkgDir = path.join(PACKAGES_DIR, pkgName);
  const pkgJson = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'));
  const srcDir = path.join(pkgDir, 'src');
  const distDir = path.join(pkgDir, 'dist');

  log(`=== ${pkgName} ===`);

  // 1. main entry
  const exportsMap = pkgJson.exports;
  const mainEntry = findEntryFile(srcDir, 'index');
  const mainTargets = [];
  if (typeof pkgJson.main === 'string') {
    // `"main": "dist"` means dist/index.js (Node directory resolution)
    const mainFile = path.extname(pkgJson.main) ? pkgJson.main : `${pkgJson.main}/index.js`;
    mainTargets.push({
      outfile: path.join(pkgDir, mainFile),
      format: 'cjs',
    });
  }
  if (typeof pkgJson.module === 'string') {
    mainTargets.push({
      outfile: path.join(pkgDir, pkgJson.module),
      format: 'esm',
    });
  }
  // exports["."] may declare extra import/module targets (e.g. renderer has
  // no `module` field but maps "import" to dist/esm/index.mjs).
  if (mainEntry && exportsMap && typeof exportsMap === 'object') {
    const dot = exportsMap['.'];
    if (dot && typeof dot === 'object') {
      for (const t of jsTargetsForExport(dot, pkgDir)) {
        if (!mainTargets.some((m) => m.outfile === t.outfile)) mainTargets.push(t);
      }
    }
  }

  // 2. sub-entries from exports map
  const subTargets = [];
  if (exportsMap && typeof exportsMap === 'object' && !Array.isArray(exportsMap)) {
    for (const [key, value] of Object.entries(exportsMap)) {
      if (key === './package.json' || key === '.') continue;
      const name = key.replace(/^\.\//, '');
      const entry = findEntryFile(srcDir, name);
      if (!entry) {
        log(`  skip sub-entry ${key} (no src/${name}.ts(x))`);
        continue;
      }
      for (const t of jsTargetsForExport(value, pkgDir)) subTargets.push({entryPoint: entry, ...t});
    }
  }

  // 3. run esbuild
  // NOTE: for packages that declare types, the CJS main target written here
  // (dist/index.js or dist/cjs/index.js) is later OVERWRITTEN by tsc's
  // per-file output (step 4) — tsc emits every src file, so the bundle is
  // redundant there but harmless. ESM targets (dist/esm/*.mjs) come from
  // esbuild only. Keep both: tsc output is the complete module tree that
  // require.resolve('./...') runtime paths depend on.
  let ok = true;
  if (mainEntry) {
    for (const t of mainTargets) {
      if (!esbuildBundle({entryPoint: mainEntry, ...t})) ok = false;
    }
  } else {
    log(`  WARN no src/index.ts(x) found`);
  }
  for (const t of subTargets) {
    if (!esbuildBundle(t)) ok = false;
  }

  // 3b. runtime files referenced via require.resolve('./...') by the bundle
  for (const [relSrc, relOut] of RUNTIME_REQUIRE_FILES[pkgName] ?? []) {
    const entryPoint = path.join(pkgDir, relSrc);
    if (!fs.existsSync(entryPoint)) {
      log(`  WARN runtime file missing: ${relSrc}`);
      continue;
    }
    if (!esbuildBundle({entryPoint, outfile: path.join(pkgDir, relOut), format: 'cjs'})) {
      ok = false;
    }
  }

  // 4. d.ts (only for packages that declare types)
  ensureVendorPatch(pkgDir);
  const declaresTypes =
    typeof pkgJson.types === 'string' ||
    (exportsMap && typeof exportsMap === 'object' &&
      Object.values(exportsMap).some((v) => v && typeof v === 'object' && typeof v.types === 'string'));
  if (declaresTypes && ok) {
    log(`  tsc -d ...`);
    if (!emitDeclarations(pkgDir)) ok = false;
  }

  if (!ok) failures.push(pkgName);
}

// cleanup incremental build info
for (const f of fs.readdirSync(PACKAGES_DIR, {withFileTypes: true})) {
  if (f.isDirectory()) {
    const tsb = path.join(PACKAGES_DIR, f.name, 'tsconfig.tsbuildinfo');
    if (fs.existsSync(tsb)) fs.unlinkSync(tsb);
  }
}

if (failures.length) {
  log(`FAILED packages: ${failures.join(', ')}`);
  process.exit(1);
}
log(`All ${CONFIG.packages.filter((p) => !SKIP_BUILD.has(p)).length} packages built.`);
