#!/usr/bin/env node
/**
 * electron-dev-watch.js
 *
 * 1. Waits for Vite dev server to be ready
 * 2. Prepares the ReVU.app bundle once (fast — skips copy if binary unchanged)
 * 3. Launches the Electron binary directly (not via `open -a`) so env vars work
 * 4. Watches dist/electron/ — kills + relaunches Electron on any .js change
 */

const { spawnSync, spawn } = require('child_process');
const path = require('path');
const chokidar = require('chokidar');
const http = require('http');

const repoRoot = path.resolve(__dirname, '..');
const distScripts = path.join(repoRoot, 'dist', 'scripts');
const viteUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173';

// ── Step 1: wait for Vite dev server ─────────────────────────────────────────
function waitForVite(retries = 30) {
  return new Promise((resolve, reject) => {
    function attempt(n) {
      http.get(viteUrl, (res) => {
        res.resume();
        console.log('[watch] Vite dev server ready');
        resolve();
      }).on('error', () => {
        if (n <= 0) return reject(new Error('Vite dev server did not start in time'));
        setTimeout(() => attempt(n - 1), 500);
      });
    }
    attempt(retries);
  });
}

// ── Step 3: prepare bundle, get binary path ───────────────────────────────────
console.log('[watch] Waiting for Vite...');
waitForVite().then(() => {
console.log('[watch] Preparing Electron bundle...');
const prep = spawnSync('node', [path.join(distScripts, 'run-dev-electron.js'), '--prepare-only'], {
  cwd: repoRoot,
  env: { ...process.env, RADCOPILOT_LAUNCH_OPEN: '0' },
  encoding: 'utf8',
  stdio: ['inherit', 'pipe', 'inherit'],
});

if (prep.status !== 0) {
  console.error('[watch] Bundle preparation failed');
  process.exit(1);
}

const electronBinary = prep.stdout.trim();
console.log('[watch] Binary:', electronBinary);

// ── Step 2: spawn / respawn helpers ──────────────────────────────────────────
let child = null;
let restarting = false;

function launchElectron() {
  console.log('[watch] Launching Electron...');
  child = spawn(electronBinary, [repoRoot], {
    cwd: repoRoot,
    env: {
      ...process.env,
      NODE_ENV: 'development',
      VITE_DEV_SERVER_URL: process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173',
    },
    stdio: 'inherit',
  });

  child.on('exit', (code, signal) => {
    child = null;
    if (!restarting && signal !== 'SIGTERM' && signal !== 'SIGKILL') {
      console.log(`[watch] Electron exited (code=${code}) — not restarting`);
      process.exit(code ?? 0);
    }
    restarting = false;
  });
}

function restartElectron() {
  if (child) {
    restarting = true;
    console.log('[watch] Restarting Electron...');
    child.kill('SIGKILL');
    // Small delay to let the OS clean up the port/resources
    setTimeout(launchElectron, 300);
  } else {
    launchElectron();
  }
}

// ── Step 3: watch dist/electron/ ─────────────────────────────────────────────
const watchPath = path.join(repoRoot, 'dist', 'electron');
let debounceTimer = null;

chokidar.watch(watchPath, { ignoreInitial: true, awaitWriteFinish: { stabilityThreshold: 300 } })
  .on('change', (file) => {
    console.log('[watch] Changed:', path.relative(repoRoot, file));
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(restartElectron, 200);
  });

// ── Step 4: forward signals ───────────────────────────────────────────────────
function shutdown() {
  if (child) child.kill('SIGTERM');
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// ── Launch ────────────────────────────────────────────────────────────────────
launchElectron();
}).catch((err) => { console.error('[watch]', err.message); process.exit(1); });
