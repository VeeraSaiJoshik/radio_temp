const {
  app,
  BrowserWindow,
  desktopCapturer,
  dialog,
  globalShortcut,
  ipcMain,
  screen,
  session,
  shell,
  systemPreferences
} = require('electron');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

let liquidGlass;
try {
  liquidGlass = require('electron-liquid-glass');
} catch (err) {
  console.warn('electron-liquid-glass not available:', err.message);
}

const { loadLocalEnv } = require('./env');
const { getLiveRuntimeConfig } = require('./live/config');
const {
  ensureMicrophoneAccess,
  getMediaAccessInfo
} = require('./live/permissions');
const { ElectronLiveService } = require('./live/service');

const repoRoot = path.resolve(__dirname, '..');
loadLocalEnv(repoRoot);

const bridgeHost = process.env.RADCOPILOT_BRIDGE_HOST || '127.0.0.1';
const bridgePort = Number(process.env.RADCOPILOT_BRIDGE_PORT || '38100');
const bridgeBaseUrl = `http://${bridgeHost}:${bridgePort}`;
const eventsUrl = `ws://${bridgeHost}:${bridgePort}/api/events`;
const hotkey = process.env.RADCOPILOT_HOTKEY || 'CommandOrControl+Shift+R';
const demoMode = process.env.RADCOPILOT_DEMO === '1';
const startBackendServer = process.env.RADCOPILOT_NO_SERVER !== '1';
const desktopLiveConfig = getLiveRuntimeConfig({ demoMode });
const keepDockVisible =
  process.platform === 'darwin' &&
  (process.env.RADCOPILOT_KEEP_DOCK_VISIBLE === '1' || !app.isPackaged);
const panelWidth = 700;
const panelHeight = 520;
const orbWindowSize = 96;
const orbWindowInset = 16;

let bridgeProcess = null;
let mainWindow = null;
let liveService = null;
let appIsQuitting = false;
let liveRendererReady = false;
let liveRendererReadyPromise = null;
let resolveLiveRendererReady = null;
let liveCommandSequence = 0;
const liveCommandPending = new Map();
let windowMode = 'orb';
let expandedBounds = null;

resetLiveRendererReady();

function resetLiveRendererReady() {
  liveRendererReady = false;
  liveRendererReadyPromise = new Promise((resolve) => {
    resolveLiveRendererReady = resolve;
  });
}

function pythonCanStartBridge(python) {
  if (!python) {
    return false;
  }

  try {
    const probe = spawnSync(python, ['-c', 'import fastapi, uvicorn'], {
      env: process.env,
      stdio: 'ignore'
    });
    return probe.status === 0;
  } catch (error) {
    return false;
  }
}

function resolvePythonExecutable() {
  const candidates = [];
  const seen = new Set();

  function addCandidate(candidate, label) {
    if (!candidate || seen.has(candidate)) {
      return;
    }
    seen.add(candidate);
    candidates.push({ candidate, label });
  }

  addCandidate(process.env.RADCOPILOT_PYTHON, 'RADCOPILOT_PYTHON');

  const venv = process.env.VIRTUAL_ENV;
  if (venv) {
    addCandidate(path.join(venv, 'bin', 'python'), 'VIRTUAL_ENV');
  }

  addCandidate(path.join(repoRoot, '.venv', 'bin', 'python'), 'repo .venv');
  addCandidate(path.join(repoRoot, 'venv', 'bin', 'python'), 'repo venv');
  addCandidate('python3', 'PATH');

  let fallback = 'python3';

  for (const { candidate, label } of candidates) {
    const isPathCandidate = candidate.includes(path.sep);
    if (isPathCandidate && !fs.existsSync(candidate)) {
      continue;
    }

    fallback = candidate;

    if (pythonCanStartBridge(candidate)) {
      console.log(`[bridge] Using Python interpreter: ${candidate} (${label})`);
      return candidate;
    }

    console.warn(
      `[bridge] Skipping Python interpreter without FastAPI/uvicorn: ${candidate} (${label})`
    );
  }

  return fallback;
}

function startBridge() {
  if (bridgeProcess) {
    return;
  }

  const python = resolvePythonExecutable();
  const args = [
    path.join(repoRoot, 'main.py'),
    '--bridge',
    '--bridge-host',
    bridgeHost,
    '--bridge-port',
    String(bridgePort)
  ];

  if (!startBackendServer) {
    args.push('--no-server');
  }
  if (demoMode) {
    args.push('--demo');
  }

  bridgeProcess = spawn(python, args, {
    cwd: repoRoot,
    env: process.env,
    stdio: ['ignore', 'pipe', 'pipe']
  });

  bridgeProcess.stdout.on('data', (chunk) => {
    process.stdout.write(`[bridge] ${chunk}`);
  });
  bridgeProcess.stderr.on('data', (chunk) => {
    process.stderr.write(`[bridge] ${chunk}`);
  });
  bridgeProcess.on('exit', (code, signal) => {
    bridgeProcess = null;
    if (!appIsQuitting) {
      console.error(
        `Bridge exited unexpectedly (code=${code}, signal=${signal || 'none'}).`
      );
    }
  });
}

async function waitForBridge(timeoutMs = 15000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(`${bridgeBaseUrl}/api/health`);
      if (response.ok) {
        return;
      }
    } catch (error) {
      // Bridge is still booting.
    }

    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  throw new Error(
    `Bridge did not become healthy on ${bridgeBaseUrl} within ${timeoutMs}ms.`
  );
}

async function bridgeRequest(route, { method = 'GET', body } = {}) {
  const response = await fetch(`${bridgeBaseUrl}${route}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (error) {
      // Ignore JSON parse failures and fall back to the HTTP status text.
    }
    throw new Error(detail);
  }

  return response.json();
}

function showWindow() {
  if (!mainWindow) {
    return;
  }

  applyWindowMode(windowMode);
  mainWindow.setIgnoreMouseEvents(false);
  mainWindow.setAlwaysOnTop(true, 'screen-saver', 1);
  mainWindow.setVisibleOnAllWorkspaces(true, {
    visibleOnFullScreen: true,
    skipTransformProcessType: true
  });
  mainWindow.show();
  mainWindow.focus();
  mainWindow.webContents.focus();
  mainWindow.moveTop();
}

function broadcastWindowMode() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send('desktop:window-mode', { mode: windowMode });
}

function collapseOverlay() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  applyWindowMode('orb');
  showWindow();
}

async function expandOverlay(options = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  applyWindowMode('bar');
  showWindow();

  if (options.capture) {
    await triggerCapture();
  }
}

function getPanelBounds(display = screen.getPrimaryDisplay()) {
  const workArea = display.workArea;
  return {
    x: Math.round(workArea.x + (workArea.width - panelWidth) / 2),
    y: workArea.y + 22,
    width: panelWidth,
    height: panelHeight
  };
}

function getOrbBounds(display = screen.getPrimaryDisplay()) {
  const workArea = display.workArea;
  return {
    x: Math.round(workArea.x + workArea.width - orbWindowSize - orbWindowInset),
    y: Math.round(workArea.y + workArea.height - orbWindowSize - orbWindowInset),
    width: orbWindowSize,
    height: orbWindowSize
  };
}

function captureExpandedBounds() {
  if (!mainWindow || mainWindow.isDestroyed() || windowMode !== 'bar') {
    return;
  }
  expandedBounds = mainWindow.getBounds();
}

function applyWindowMode(mode) {
  windowMode = mode === 'orb' ? 'orb' : 'bar';
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  if (windowMode === 'orb') {
    expandedBounds = expandedBounds || mainWindow.getBounds();
    const display = screen.getDisplayMatching(mainWindow.getBounds());
    mainWindow.setBounds(getOrbBounds(display), true);
    broadcastWindowMode();
    return;
  }

  const display = screen.getDisplayMatching(mainWindow.getBounds());
  const bounds = expandedBounds || getPanelBounds(display);
  mainWindow.setBounds(bounds, true);
  broadcastWindowMode();
}

async function triggerCapture() {
  if (demoMode) {
    return;
  }

  try {
    await bridgeRequest('/api/capture', { method: 'POST' });
  } catch (error) {
    if (mainWindow) {
      mainWindow.webContents.send('desktop:error', error.message);
    }
  }
}

function selectPrimaryScreenSource(sources) {
  const primaryDisplay = screen.getPrimaryDisplay();
  const primary = sources.find(
    (source) => String(source.display_id || '') === String(primaryDisplay.id || '')
  );
  return primary || sources[0] || null;
}

function configureDisplayMedia() {
  session.defaultSession.setDisplayMediaRequestHandler(
    async (_request, callback) => {
      try {
        const sources = await desktopCapturer.getSources({
          types: ['screen'],
          thumbnailSize: { width: 1, height: 1 },
          fetchWindowIcons: false
        });
        const source = selectPrimaryScreenSource(sources);
        callback({
          video: source,
          audio: 'none'
        });
      } catch (error) {
        console.error(`Display media request failed: ${error.message}`);
        callback({
          video: null,
          audio: 'none'
        });
      }
    },
    { useSystemPicker: false }
  );
}

function setMacActivationMode(mode) {
  if (process.platform !== 'darwin') {
    return;
  }

  try {
    app.setActivationPolicy(mode);
  } catch (error) {
    console.warn(`Failed to set macOS activation policy to ${mode}: ${error.message}`);
  }

  if (!app.dock) {
    return;
  }

  try {
    if (mode === 'regular' || keepDockVisible) {
      app.dock.show();
    } else {
      app.dock.hide();
    }
  } catch (error) {
    console.warn(`Failed to update Dock visibility for ${mode}: ${error.message}`);
  }
}

async function prepareForMediaAccessPrompt(mediaType) {
  if (process.platform !== 'darwin') {
    return mediaType === 'microphone'
      ? ensureMicrophoneAccess(systemPreferences, process.platform)
      : getMediaAccessInfo(systemPreferences, mediaType, process.platform);
  }

  setMacActivationMode('regular');

  if (mainWindow && !mainWindow.isDestroyed()) {
    showWindow();
    mainWindow.focus();
    mainWindow.webContents.focus();
  }
  app.focus({ steal: true });

  await new Promise((resolve) => setTimeout(resolve, 200));

  return mediaType === 'microphone'
    ? ensureMicrophoneAccess(systemPreferences, process.platform)
    : getMediaAccessInfo(systemPreferences, mediaType, process.platform);
}

async function openMacPermissionSettings(mediaType) {
  if (process.platform !== 'darwin') {
    return { ok: false };
  }

  const privacyPane =
    mediaType === 'microphone' ? 'Privacy_Microphone' : 'Privacy_ScreenCapture';
  let opened = false;

  try {
    await shell.openExternal(
      `x-apple.systempreferences:com.apple.preference.security?${privacyPane}`
    );
    opened = true;
  } catch (error) {
    console.warn(`Failed to open macOS privacy settings for ${mediaType}: ${error.message}`);
  }

  if (!opened) {
    try {
      await shell.openExternal('x-apple.systempreferences:com.apple.preference.security');
      opened = true;
    } catch (error) {
      console.warn(`Failed to open macOS Security & Privacy settings: ${error.message}`);
    }
  }

  return { ok: opened };
}

function createWindow() {
  const display = screen.getPrimaryDisplay();
  const initialBounds = windowMode === 'orb' ? getOrbBounds(display) : getPanelBounds(display);

  mainWindow = new BrowserWindow({
    x: initialBounds.x,
    y: initialBounds.y,
    width: initialBounds.width,
    height: initialBounds.height,
    show: false,
    transparent: true,
    frame: false,
    hasShadow: false,
    skipTaskbar: true,
    acceptFirstMouse: true,
    resizable: false,
    movable: true,
    fullscreenable: false,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      backgroundThrottling: false
    }
  });
  expandedBounds = getPanelBounds(display);

  // Keep the overlay out of the user's own screenshots and screen shares.
  mainWindow.setContentProtection(true);
  mainWindow.setAlwaysOnTop(true, 'screen-saver', 1);
  mainWindow.setVisibleOnAllWorkspaces(true, {
    visibleOnFullScreen: true,
    skipTransformProcessType: true
  });
  mainWindow.setWindowButtonVisibility(false);
  // In development, load the Vite dev server; in production, load the built output.
  const viteDevUrl = process.env.VITE_DEV_SERVER_URL;
  if (viteDevUrl) {
    mainWindow.loadURL(viteDevUrl);
  } else {
    mainWindow.loadFile(path.join(__dirname, 'renderer-dist', 'index.html'));
  }
  mainWindow.once('ready-to-show', () => {
    showWindow();
  });

  // Apply native liquid glass — window IS the glass surface
  mainWindow.webContents.once('did-finish-load', () => {
    if (liquidGlass) {
      try {
        const glassId = liquidGlass.addView(mainWindow.getNativeWindowHandle(), {
          cornerRadius: 22
        });
        if (glassId >= 0) {
          liquidGlass.unstable_setVariant(glassId, 1); // clear — lighter, more transparent
          console.log(`Native liquid glass applied (glassId=${glassId})`);
        }
      } catch (err) {
        console.warn('Failed to apply liquid glass:', err.message);
      }
    }
  });

  mainWindow.webContents.on('did-start-loading', () => {
    resetLiveRendererReady();
    rejectPendingLiveCommands('Live renderer reloaded before responding.');
  });

  mainWindow.on('close', (event) => {
    if (appIsQuitting) {
      return;
    }
    event.preventDefault();
    collapseOverlay();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
    resetLiveRendererReady();
    rejectPendingLiveCommands('Live renderer window closed.');
  });

  mainWindow.on('move', () => {
    captureExpandedBounds();
  });
}

function registerHotkey() {
  globalShortcut.unregisterAll();
  globalShortcut.register(hotkey, async () => {
    if (!mainWindow) {
      return;
    }

    if (mainWindow.isVisible() && windowMode === 'bar') {
      collapseOverlay();
      return;
    }

    await expandOverlay({ capture: true });
  });
}

function stopBridge() {
  if (!bridgeProcess) {
    return;
  }
  bridgeProcess.kill();
  bridgeProcess = null;
}

function rejectPendingLiveCommands(message) {
  for (const [requestId, pending] of liveCommandPending.entries()) {
    clearTimeout(pending.timeoutId);
    pending.reject(new Error(message));
    liveCommandPending.delete(requestId);
  }
}

async function waitForLiveRendererReady(timeoutMs = 15000) {
  if (liveRendererReady) {
    return;
  }

  let timeoutId;
  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(
        Object.assign(new Error('Live renderer did not become ready in time.'), {
          code: 'renderer_timeout'
        })
      );
    }, timeoutMs);
  });

  try {
    await Promise.race([liveRendererReadyPromise, timeoutPromise]);
  } finally {
    clearTimeout(timeoutId);
  }
}

async function sendLiveCommand(command) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    throw Object.assign(new Error('Live renderer window is not available.'), {
      code: 'renderer_unavailable'
    });
  }

  await waitForLiveRendererReady(command.timeoutMs || 15000);

  const requestId = `cmd-${Date.now()}-${++liveCommandSequence}`;
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      liveCommandPending.delete(requestId);
      reject(
        Object.assign(
          new Error(`Live renderer command timed out: ${command.type}`),
          { code: 'renderer_timeout' }
        )
      );
    }, command.timeoutMs || 15000);

    liveCommandPending.set(requestId, {
      resolve,
      reject,
      timeoutId
    });

    mainWindow.webContents.send('live:command', {
      requestId,
      type: command.type,
      payload: command.payload || null
    });
  });
}

function emitLiveEvent(event) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send('live:event', event);
}

function buildLiveService() {
  return new ElectronLiveService({
    runtimeConfig: desktopLiveConfig,
    rendererRequest: async (command) => {
      if (command.type === 'live.start_mic') {
        await ensureMicrophoneAccess(systemPreferences, process.platform);
      }
      return sendLiveCommand(command);
    },
    eventSink: emitLiveEvent,
    hotkeyTrigger: async () => {
      await expandOverlay({ capture: true });
    },
    closeOverlayTrigger: async () => {
      collapseOverlay();
    }
  });
}

ipcMain.handle('desktop:get-config', async () => ({
  bridgeBaseUrl,
  eventsUrl,
  hotkey,
  demoMode,
  livePreviewFps: desktopLiveConfig.previewFps,
  livePreviewMaxWidth: desktopLiveConfig.previewMaxWidth,
  livePreviewJpegQuality: desktopLiveConfig.previewJpegQuality,
  liveMicSampleRate: desktopLiveConfig.micSampleRate,
  screenshotJpegQuality: 85
}));

ipcMain.on('desktop:set-ignore-mouse', (_event, { ignore }) => {
  if (!mainWindow) return;
  if (ignore) {
    mainWindow.setIgnoreMouseEvents(true, { forward: true });
  } else {
    mainWindow.setIgnoreMouseEvents(false);
  }
});

ipcMain.handle('desktop:hide-window', async () => {
  collapseOverlay();
  return { ok: true, mode: 'orb' };
});

ipcMain.handle('desktop:show-window', async () => {
  showWindow();
  return { ok: true, mode: windowMode };
});

ipcMain.handle('desktop:set-window-mode', async (_event, mode) => {
  applyWindowMode(mode);
  return { ok: true, mode: windowMode };
});

ipcMain.handle('live:get-state', async () => {
  if (!liveService) {
    return {
      live: {
        connected: false,
        message: 'Gemini Live unavailable',
        phase: '',
        mic_active: false
      },
      transcript_entries: [],
      screenshot_history: [],
      session_id: '',
      enabled: false
    };
  }
  return liveService.getState();
});

ipcMain.handle('live:get-media-access-status', async (_event, mediaType) =>
  getMediaAccessInfo(systemPreferences, mediaType, process.platform)
);
ipcMain.handle('live:prepare-media-access', async (_event, mediaType) =>
  prepareForMediaAccessPrompt(mediaType)
);
ipcMain.handle('live:open-media-settings', async (_event, mediaType) =>
  openMacPermissionSettings(mediaType)
);

ipcMain.handle('live:send-text', async (_event, text) => liveService.sendText(text));
ipcMain.handle('live:start-mic', async () => liveService.startMicCapture());
ipcMain.handle('live:stop-mic', async () => liveService.stopMicCapture());
ipcMain.handle('live:renderer-ready', async () => {
  liveRendererReady = true;
  if (resolveLiveRendererReady) {
    resolveLiveRendererReady();
  }
  return { ok: true };
});

ipcMain.on('live:command-response', (_event, message) => {
  const pending = liveCommandPending.get(message.requestId);
  if (!pending) {
    return;
  }

  clearTimeout(pending.timeoutId);
  liveCommandPending.delete(message.requestId);

  if (message.error) {
    pending.reject(
      Object.assign(new Error(message.error.message || 'Live renderer error'), {
        code: message.error.code || 'renderer_error'
      })
    );
    return;
  }

  pending.resolve(message.payload);
});

ipcMain.on('live:preview-frame', (_event, payload) => {
  if (!liveService) {
    return;
  }
  void liveService.submitPreviewFrame(payload);
});

ipcMain.on('live:audio-chunk', (_event, payload) => {
  if (!liveService) {
    return;
  }
  void liveService.submitAudioChunk(payload && payload.bytes ? payload.bytes : payload);
});

ipcMain.on('live:audio-stream-end', () => {
  if (!liveService) {
    return;
  }
  void liveService.submitAudioStreamEnd();
});

ipcMain.on('live:mic-state', (_event, payload) => {
  if (!liveService) {
    return;
  }
  liveService.notifyMicState(Boolean(payload && payload.active));
});

ipcMain.on('live:media-error', (_event, payload) => {
  if (!liveService) {
    return;
  }
  liveService.notifyRendererError(
    payload && payload.code ? payload.code : 'renderer_error',
    payload && payload.message ? payload.message : 'Live media error'
  );
});

app.whenReady().then(async () => {
  // Grant all media permission requests from the renderer (mic, camera, screen).
  // macOS 26 TCC doesn't recognise unsigned dev Electron, so we handle it here.
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    const allowed = ['media', 'mediaKeySystem', 'microphone', 'camera', 'display-capture'];
    callback(allowed.includes(permission));
  });
  session.defaultSession.setPermissionCheckHandler((_webContents, permission) => {
    const allowed = ['media', 'mediaKeySystem', 'microphone', 'camera', 'display-capture'];
    return allowed.includes(permission);
  });

  if (process.platform === 'darwin') {
    setMacActivationMode(keepDockVisible ? 'regular' : 'accessory');
  }

  configureDisplayMedia();
  startBridge();
  await waitForBridge();
  createWindow();
  registerHotkey();

  liveService = buildLiveService();
  await liveService.start();
}).catch((error) => {
  const detail = error && error.message ? error.message : String(error);
  console.error(`Desktop startup failed: ${detail}`);
  dialog.showErrorBox(
    'ReVU failed to start',
    `${detail}\n\nCheck that a project virtualenv with FastAPI/uvicorn is installed.`
  );
  app.exit(1);
});

app.on('activate', () => {
  if (!mainWindow) {
    createWindow();
  } else {
    showWindow();
  }
});

app.on('will-quit', () => {
  appIsQuitting = true;
  globalShortcut.unregisterAll();
  rejectPendingLiveCommands('Application is quitting.');
  if (liveService) {
    void liveService.stop();
  }
  stopBridge();
});

app.on('window-all-closed', (event) => {
  event.preventDefault();
});
