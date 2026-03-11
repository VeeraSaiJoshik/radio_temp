import {
  app,
  BrowserWindow,
  desktopCapturer,
  dialog,
  globalShortcut,
  ipcMain,
  screen,
  session,
  shell,
  systemPreferences,
  Display,
  Rectangle
} from 'electron';
import { spawn, spawnSync, ChildProcess } from 'child_process';
import fs from 'fs';
import path from 'path';
import log from 'electron-log/main';

log.transports.file.level = 'debug';
log.transports.console.level = 'debug';
log.errorHandler.startCatching();

let liquidGlass: {
  addView: (handle: Buffer, options: { cornerRadius: number }) => number;
  unstable_setVariant: (id: number, variant: number) => void;
} | undefined;
try {
  liquidGlass = require('electron-liquid-glass');
} catch (err) {
  const error = err as Error;
  log.warn('electron-liquid-glass not available:', error.message);
}

import { loadLocalEnv } from './env';

if (process.env.NODE_ENV !== 'production') {
  try {
    require('electron-reload')(__dirname, {
      electron: require('electron') as string,
      hardResetMethod: 'exit',
      forceHardReset: true,
      awaitWriteFinish: true,
    });
  } catch { /* not installed in production */ }
}

import { getLiveRuntimeConfig } from './live/config';
import {
  ensureMicrophoneAccess,
  getMediaAccessInfo
} from './live/permissions';
import { ElectronLiveService } from './live/service';

const repoRoot = path.resolve(__dirname, '../..');
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

let bridgeProcess: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;
let liveService: ElectronLiveService | null = null;
let appIsQuitting = false;
let liveRendererReady = false;
let liveRendererReadyPromise: Promise<void> | null = null;
let resolveLiveRendererReady: (() => void) | null = null;
let liveCommandSequence = 0;
const liveCommandPending = new Map<string, {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
  timeoutId: ReturnType<typeof setTimeout>;
}>();
let windowMode: 'orb' | 'bar' = 'orb';
let expandedBounds: Rectangle | null = null;

resetLiveRendererReady();

function resetLiveRendererReady(): void {
  liveRendererReady = false;
  liveRendererReadyPromise = new Promise((resolve) => {
    resolveLiveRendererReady = resolve;
  });
}

function pythonCanStartBridge(python: string): boolean {
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

function resolvePythonExecutable(): string {
  const candidates: Array<{ candidate: string; label: string }> = [];
  const seen = new Set<string>();

  function addCandidate(candidate: string | undefined, label: string): void {
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
      log.info(`[bridge] Using Python interpreter: ${candidate} (${label})`);
      return candidate;
    }

    log.warn(
      `[bridge] Skipping Python interpreter without FastAPI/uvicorn: ${candidate} (${label})`
    );
  }

  return fallback;
}

function startBridge(): void {
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

  bridgeProcess.stdout!.on('data', (chunk: Buffer) => {
    process.stdout.write(`[bridge] ${chunk}`);
  });
  bridgeProcess.stderr!.on('data', (chunk: Buffer) => {
    process.stderr.write(`[bridge] ${chunk}`);
  });
  bridgeProcess.on('exit', (code: number | null, signal: NodeJS.Signals | null) => {
    bridgeProcess = null;
    if (!appIsQuitting) {
      log.error(
        `Bridge exited unexpectedly (code=${code}, signal=${signal || 'none'}).`
      );
    }
  });
}

async function waitForBridge(timeoutMs = 15000): Promise<void> {
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

    await new Promise<void>((resolve) => setTimeout(resolve, 250));
  }

  throw new Error(
    `Bridge did not become healthy on ${bridgeBaseUrl} within ${timeoutMs}ms.`
  );
}

interface BridgeRequestOptions {
  method?: string;
  body?: unknown;
}

async function bridgeRequest(route: string, { method = 'GET', body }: BridgeRequestOptions = {}): Promise<unknown> {
  const response = await fetch(`${bridgeBaseUrl}${route}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json() as { detail?: string };
      detail = payload.detail || detail;
    } catch (error) {
      // Ignore JSON parse failures and fall back to the HTTP status text.
    }
    throw new Error(detail);
  }

  return response.json();
}

function showWindow(): void {
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

function broadcastWindowMode(): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send('desktop:window-mode', { mode: windowMode });
}

function collapseOverlay(): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  applyWindowMode('orb');
  showWindow();
}

interface ExpandOptions {
  capture?: boolean;
}

async function expandOverlay(options: ExpandOptions = {}): Promise<void> {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  applyWindowMode('bar');
  showWindow();

  if (options.capture) {
    await triggerCapture();
  }
}

function getPanelBounds(display: Display = screen.getPrimaryDisplay()): Rectangle {
  const workArea = display.workArea;
  return {
    x: Math.round(workArea.x + (workArea.width - panelWidth) / 2),
    y: workArea.y + 22,
    width: panelWidth,
    height: panelHeight
  };
}

function getOrbBounds(display: Display = screen.getPrimaryDisplay()): Rectangle {
  const workArea = display.workArea;
  return {
    x: Math.round(workArea.x + workArea.width - orbWindowSize - orbWindowInset),
    y: Math.round(workArea.y + workArea.height - orbWindowSize - orbWindowInset),
    width: orbWindowSize,
    height: orbWindowSize
  };
}

function captureExpandedBounds(): void {
  if (!mainWindow || mainWindow.isDestroyed() || windowMode !== 'bar') {
    return;
  }
  expandedBounds = mainWindow.getBounds();
}

function applyWindowMode(mode: string): void {
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

async function triggerCapture(): Promise<void> {
  if (demoMode) {
    return;
  }

  try {
    await bridgeRequest('/api/capture', { method: 'POST' });
  } catch (error) {
    const err = error as Error;
    if (mainWindow) {
      mainWindow.webContents.send('desktop:error', err.message);
    }
  }
}

function selectPrimaryScreenSource(sources: Electron.DesktopCapturerSource[]): Electron.DesktopCapturerSource | null {
  const primaryDisplay = screen.getPrimaryDisplay();
  const primary = sources.find(
    (source) => String(source.display_id || '') === String(primaryDisplay.id || '')
  );
  return primary || sources[0] || null;
}

function configureDisplayMedia(): void {
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
          video: source ?? undefined,
          audio: 'loopback' as const
        });
      } catch (error) {
        const err = error as Error;
        log.error(`Display media request failed: ${err.message}`);
        callback({
          video: undefined,
          audio: 'loopback' as const
        });
      }
    },
    { useSystemPicker: false }
  );
}

function setMacActivationMode(mode: 'regular' | 'accessory' | 'prohibited'): void {
  if (process.platform !== 'darwin') {
    return;
  }

  try {
    app.setActivationPolicy(mode);
  } catch (error) {
    const err = error as Error;
    log.warn(`Failed to set macOS activation policy to ${mode}: ${err.message}`);
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
    const err = error as Error;
    log.warn(`Failed to update Dock visibility for ${mode}: ${err.message}`);
  }
}

async function prepareForMediaAccessPrompt(mediaType: string): Promise<ReturnType<typeof getMediaAccessInfo>> {
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

  await new Promise<void>((resolve) => setTimeout(resolve, 200));

  return mediaType === 'microphone'
    ? ensureMicrophoneAccess(systemPreferences, process.platform)
    : getMediaAccessInfo(systemPreferences, mediaType, process.platform);
}

async function openMacPermissionSettings(mediaType: string): Promise<{ ok: boolean }> {
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
    const err = error as Error;
    log.warn(`Failed to open macOS privacy settings for ${mediaType}: ${err.message}`);
  }

  if (!opened) {
    try {
      await shell.openExternal('x-apple.systempreferences:com.apple.preference.security');
      opened = true;
    } catch (error) {
      const err = error as Error;
      log.warn(`Failed to open macOS Security & Privacy settings: ${err.message}`);
    }
  }

  return { ok: opened };
}

function createWindow(): void {
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
  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));
  mainWindow.once('ready-to-show', () => {
    showWindow();
  });

  // Apply native liquid glass — window IS the glass surface
  mainWindow.webContents.once('did-finish-load', () => {
    if (liquidGlass) {
      try {
        const glassId = liquidGlass.addView(mainWindow!.getNativeWindowHandle(), {
          cornerRadius: 22
        });
        if (glassId >= 0) {
          liquidGlass.unstable_setVariant(glassId, 1); // clear — lighter, more transparent
          log.info(`Native liquid glass applied (glassId=${glassId})`);
        }
      } catch (err) {
        const error = err as Error;
        log.warn('Failed to apply liquid glass:', error.message);
      }
    }
  });

  mainWindow.webContents.on('did-start-loading', () => {
    resetLiveRendererReady();
    rejectPendingLiveCommands('Live renderer reloaded before responding.');
  });

  mainWindow.on('close', (event: Electron.Event) => {
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

function registerHotkey(): void {
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

function stopBridge(): void {
  if (!bridgeProcess) {
    return;
  }
  bridgeProcess.kill();
  bridgeProcess = null;
}

function rejectPendingLiveCommands(message: string): void {
  for (const [requestId, pending] of liveCommandPending.entries()) {
    clearTimeout(pending.timeoutId);
    pending.reject(new Error(message));
    liveCommandPending.delete(requestId);
  }
}

async function waitForLiveRendererReady(timeoutMs = 15000): Promise<void> {
  if (liveRendererReady) {
    return;
  }

  let timeoutId: ReturnType<typeof setTimeout>;
  const timeoutPromise = new Promise<void>((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(
        Object.assign(new Error('Live renderer did not become ready in time.'), {
          code: 'renderer_timeout'
        })
      );
    }, timeoutMs);
  });

  try {
    await Promise.race([liveRendererReadyPromise!, timeoutPromise]);
  } finally {
    clearTimeout(timeoutId!);
  }
}

interface LiveCommand {
  type: string;
  payload?: unknown;
  timeoutMs?: number;
}

async function sendLiveCommand(command: LiveCommand): Promise<unknown> {
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

    mainWindow!.webContents.send('live:command', {
      requestId,
      type: command.type,
      payload: command.payload || null
    });
  });
}

function emitLiveEvent(event: unknown): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send('live:event', event);
}

function buildLiveService(): ElectronLiveService {
  return new ElectronLiveService({
    runtimeConfig: desktopLiveConfig,
    rendererRequest: async (command) => {
      if (command.type === 'live.start_mic') {
        await ensureMicrophoneAccess(systemPreferences, process.platform);
      }
      return sendLiveCommand(command) as ReturnType<ElectronLiveService['rendererRequest']>;
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

// ─── IPC Handlers ─────────────────────────────────────────────────────────────

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

ipcMain.on('desktop:set-ignore-mouse', (_event, { ignore }: { ignore: boolean }) => {
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

ipcMain.handle('desktop:set-window-mode', async (_event, mode: string) => {
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

ipcMain.handle('live:get-media-access-status', async (_event, mediaType: string) =>
  getMediaAccessInfo(systemPreferences, mediaType, process.platform)
);
ipcMain.handle('live:prepare-media-access', async (_event, mediaType: string) =>
  prepareForMediaAccessPrompt(mediaType)
);
ipcMain.handle('live:open-media-settings', async (_event, mediaType: string) =>
  openMacPermissionSettings(mediaType)
);

ipcMain.handle('live:send-text', async (_event, text: string) => liveService!.sendText(text));
ipcMain.handle('live:start-mic', async () => liveService!.startMicCapture());
ipcMain.handle('live:stop-mic', async () => liveService!.stopMicCapture());
ipcMain.handle('live:renderer-ready', async () => {
  liveRendererReady = true;
  if (resolveLiveRendererReady) {
    resolveLiveRendererReady();
  }
  return { ok: true };
});

ipcMain.on('live:command-response', (_event, message: {
  requestId: string;
  payload?: unknown;
  error?: { message?: string; code?: string };
}) => {
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

ipcMain.on('live:preview-frame', (_event, payload: unknown) => {
  if (!liveService) {
    return;
  }
  void liveService.submitPreviewFrame(payload as { bytes: Uint8Array; mimeType?: string });
});

ipcMain.on('live:audio-chunk', (_event, payload: unknown) => {
  if (!liveService) {
    return;
  }
  const p = payload as { bytes?: Uint8Array } | Uint8Array | null;
  void liveService.submitAudioChunk(
    p && (p as { bytes?: Uint8Array }).bytes
      ? (p as { bytes: Uint8Array }).bytes
      : p as Uint8Array
  );
});

ipcMain.on('live:audio-stream-end', () => {
  if (!liveService) {
    return;
  }
  void liveService.submitAudioStreamEnd();
});

ipcMain.on('live:mic-state', (_event, payload: { active?: boolean } | null) => {
  if (!liveService) {
    return;
  }
  liveService.notifyMicState(Boolean(payload && payload.active));
});

ipcMain.on('live:media-error', (_event, payload: { code?: string; message?: string } | null) => {
  if (!liveService) {
    return;
  }
  liveService.notifyRendererError(
    payload && payload.code ? payload.code : 'renderer_error',
    payload && payload.message ? payload.message : 'Live media error'
  );
});

// ─── App lifecycle ─────────────────────────────────────────────────────────────

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
  //startBridge();
  //await waitForBridge();
  createWindow();
  registerHotkey();

  liveService = buildLiveService();
  await liveService.start();
}).catch((error: Error) => {
  const detail = error && error.message ? error.message : String(error);
  log.error(`Desktop startup failed: ${detail}`);
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

app.on('window-all-closed', () => {
  // Intentionally prevent default close behaviour — the overlay window is persistent.
});
