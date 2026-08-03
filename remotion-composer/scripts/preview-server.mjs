#!/usr/bin/env node
/**
 * NLE preview server for Backlot's interactive timeline editor.
 *
 * Bundles src/preview.tsx once with @remotion/bundler (bundle() returns the
 * output DIRECTORY, not a URL — rendering/selecting accepts the directory
 * as serveUrl) and serves it over a small static HTTP server on --port.
 * The preview.tsx component polls the Backlot NLE draft endpoint itself, so
 * edits show up without recompiling.
 *
 * --public-dir <path> makes the project directory's assets reachable:
 * bundle() copies it into <outDir>/public, which is where Remotion's
 * staticFile() resolves /public/... requests against.
 *
 * Usage:
 *   node scripts/preview-server.mjs --port=3450 --public-dir=<project_dir>
 */
import {createRequire} from 'node:module';
import {createReadStream, existsSync, statSync} from 'node:fs';
import {createServer} from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

// CJS require — same rationale as render.mjs (see comment there).
const require = createRequire(import.meta.url);
const {bundle} = require('@remotion/bundler');

const args = process.argv.slice(2);
function get(name) {
  const prefix = `--${name}=`;
  const hit = args.find((a) => a.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : null;
}

const port = get('port') ? Number(get('port')) : 3450;
const publicDir = get('public-dir') ? path.resolve(get('public-dir')) : undefined;
const here = path.dirname(fileURLToPath(import.meta.url));
const entryPoint = path.resolve(here, '..', 'src', 'preview.tsx');

const outDir = await bundle({
  entryPoint,
  publicDir,
  onProgress: () => {},
});

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json',
  '.css': 'text/css; charset=utf-8',
  '.wasm': 'application/wasm',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.srt': 'text/plain; charset=utf-8',
};

// Path traversal guard: every resolved path must stay inside outDir.
function safeJoin(outDirRoot, urlPath) {
  const target = path.normalize(path.join(outDirRoot, urlPath));
  const root = path.resolve(outDirRoot) + path.sep;
  if (!target.startsWith(root) && target !== path.resolve(outDirRoot)) {
    return null;
  }
  return target;
}

const server = createServer((req, res) => {
  try {
    let urlPath;
    try {
      urlPath = decodeURIComponent(new URL(req.url, `http://localhost:${port}`).pathname);
    } catch {
      res.writeHead(400);
      res.end('bad request');
      return;
    }
    let filePath = safeJoin(outDir, urlPath === '/' ? 'index.html' : urlPath);
    if (!filePath) {
      // Traversal attempt (.. / %2e%2e escaping the bundle dir)
      res.writeHead(403);
      res.end('forbidden');
      return;
    }
    // dev-server style fallback to index.html for unknown routes
    if (!existsSync(filePath) || statSync(filePath).isDirectory()) {
      filePath = safeJoin(outDir, 'index.html');
    }
    if (!filePath || !existsSync(filePath)) {
      res.writeHead(404);
      res.end('not found');
      return;
    }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(filePath).toLowerCase()] ?? 'application/octet-stream',
    });
    createReadStream(filePath).pipe(res);
  } catch (err) {
    res.writeHead(500);
    res.end('internal error');
  }
});

server.listen(port, '127.0.0.1', () => {
  console.log(`PREVIEW_URL=http://localhost:${port}`);
});
