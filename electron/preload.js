const { contextBridge, ipcRenderer } = require('electron');

const bridgeHost = process.env.RADCOPILOT_BRIDGE_HOST || '127.0.0.1';
const bridgePort = Number(process.env.RADCOPILOT_BRIDGE_PORT || '38100');
const bridgeBaseUrl = `http://${bridgeHost}:${bridgePort}`;
const eventsUrl = `ws://${bridgeHost}:${bridgePort}/api/events`;

async function request(route, { method = 'GET', body } = {}) {
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
      // Use the HTTP status text if the bridge did not return JSON.
    }
    throw new Error(detail);
  }

  return response.json();
}

contextBridge.exposeInMainWorld('copilotDesktop', {
  bridgeBaseUrl,
  eventsUrl,
  getConfig: () => ipcRenderer.invoke('desktop:get-config'),
  getState: () => request('/api/state'),
  capture: () => request('/api/capture', { method: 'POST' }),
  dismiss: () => request('/api/dismiss', { method: 'POST' }),
  flag: (overrideNote) =>
    request('/api/flag', {
      method: 'POST',
      body: { override_note: overrideNote }
    }),
  sendLiveText: (text) => ipcRenderer.invoke('live:send-text', text),
  startMic: () => ipcRenderer.invoke('live:start-mic'),
  stopMic: () => ipcRenderer.invoke('live:stop-mic'),
  getLiveState: () => ipcRenderer.invoke('live:get-state'),
  getLiveMediaAccessStatus: (mediaType) =>
    ipcRenderer.invoke('live:get-media-access-status', mediaType),
  prepareLiveMediaAccess: (mediaType) =>
    ipcRenderer.invoke('live:prepare-media-access', mediaType),
  openLiveMediaSettings: (mediaType) =>
    ipcRenderer.invoke('live:open-media-settings', mediaType),
  setIgnoreMouse: (ignore) =>
    ipcRenderer.send('desktop:set-ignore-mouse', { ignore }),
  hideWindow: () => ipcRenderer.invoke('desktop:hide-window'),
  showWindow: () => ipcRenderer.invoke('desktop:show-window'),
  setWindowMode: (mode) => ipcRenderer.invoke('desktop:set-window-mode', mode),
  markLiveRendererReady: () => ipcRenderer.invoke('live:renderer-ready'),
  sendLivePreviewFrame: (frame) => ipcRenderer.send('live:preview-frame', frame),
  sendLiveAudioChunk: (chunk) => ipcRenderer.send('live:audio-chunk', chunk),
  sendLiveAudioStreamEnd: () => ipcRenderer.send('live:audio-stream-end'),
  setLiveMicState: (active) => ipcRenderer.send('live:mic-state', { active }),
  reportLiveMediaError: (code, message) =>
    ipcRenderer.send('live:media-error', { code, message }),
  respondLiveCommand: (requestId, payload, error) =>
    ipcRenderer.send('live:command-response', { requestId, payload, error }),
  onLiveCommand: (callback) => {
    ipcRenderer.on('live:command', (_event, command) => callback(command));
  },
  onLiveEvent: (callback) => {
    ipcRenderer.on('live:event', (_event, liveEvent) => callback(liveEvent));
  },
  onWindowModeChange: (callback) => {
    ipcRenderer.on('desktop:window-mode', (_event, payload) => callback(payload));
  },
  onDesktopError: (callback) => {
    ipcRenderer.on('desktop:error', (_event, message) => callback(message));
  }
});
