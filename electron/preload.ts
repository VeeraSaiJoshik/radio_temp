import { contextBridge, ipcRenderer } from 'electron';

const bridgeHost = process.env.RADCOPILOT_BRIDGE_HOST || '127.0.0.1';
const bridgePort = Number(process.env.RADCOPILOT_BRIDGE_PORT || '38100');
const bridgeBaseUrl = `http://${bridgeHost}:${bridgePort}`;
const eventsUrl = `ws://${bridgeHost}:${bridgePort}/api/events`;

interface RequestOptions {
  method?: string;
  body?: unknown;
}

async function request(route: string, { method = 'GET', body }: RequestOptions = {}): Promise<unknown> {
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
      // Use the HTTP status text if the bridge did not return JSON.
    }
    throw new Error(detail);
  }

  return response.json();
}

contextBridge.exposeInMainWorld('copilotDesktop', {
  bridgeBaseUrl,
  eventsUrl,
  getConfig: (): Promise<unknown> => ipcRenderer.invoke('desktop:get-config'),
  getState: (): Promise<unknown> => request('/api/state'),
  capture: (): Promise<unknown> => request('/api/capture', { method: 'POST' }),
  dismiss: (): Promise<unknown> => request('/api/dismiss', { method: 'POST' }),
  flag: (overrideNote: string): Promise<unknown> =>
    request('/api/flag', {
      method: 'POST',
      body: { override_note: overrideNote }
    }),
  sendLiveText: (text: string): Promise<unknown> => ipcRenderer.invoke('live:send-text', text),
  startMic: (): Promise<unknown> => ipcRenderer.invoke('live:start-mic'),
  stopMic: (): Promise<unknown> => ipcRenderer.invoke('live:stop-mic'),
  getLiveState: (): Promise<unknown> => ipcRenderer.invoke('live:get-state'),
  getLiveMediaAccessStatus: (mediaType: string): Promise<unknown> =>
    ipcRenderer.invoke('live:get-media-access-status', mediaType),
  prepareLiveMediaAccess: (mediaType: string): Promise<unknown> =>
    ipcRenderer.invoke('live:prepare-media-access', mediaType),
  openLiveMediaSettings: (mediaType: string): Promise<unknown> =>
    ipcRenderer.invoke('live:open-media-settings', mediaType),
  setIgnoreMouse: (ignore: boolean): void =>
    ipcRenderer.send('desktop:set-ignore-mouse', { ignore }),
  hideWindow: (): Promise<unknown> => ipcRenderer.invoke('desktop:hide-window'),
  showWindow: (): Promise<unknown> => ipcRenderer.invoke('desktop:show-window'),
  setWindowMode: (mode: string): Promise<unknown> => ipcRenderer.invoke('desktop:set-window-mode', mode),
  markLiveRendererReady: (): Promise<unknown> => ipcRenderer.invoke('live:renderer-ready'),
  sendLivePreviewFrame: (frame: unknown): void => ipcRenderer.send('live:preview-frame', frame),
  sendLiveAudioChunk: (chunk: unknown): void => ipcRenderer.send('live:audio-chunk', chunk),
  sendLiveAudioStreamEnd: (): void => ipcRenderer.send('live:audio-stream-end'),
  setLiveMicState: (active: boolean): void => ipcRenderer.send('live:mic-state', { active }),
  reportLiveMediaError: (code: string, message: string): void =>
    ipcRenderer.send('live:media-error', { code, message }),
  respondLiveCommand: (requestId: string, payload: unknown, error: unknown): void =>
    ipcRenderer.send('live:command-response', { requestId, payload, error }),
  onLiveCommand: (callback: (command: unknown) => void): void => {
    ipcRenderer.on('live:command', (_event, command) => callback(command));
  },
  onLiveEvent: (callback: (liveEvent: unknown) => void): void => {
    ipcRenderer.on('live:event', (_event, liveEvent) => callback(liveEvent));
  },
  onWindowModeChange: (callback: (payload: unknown) => void): void => {
    ipcRenderer.on('desktop:window-mode', (_event, payload) => callback(payload));
  },
  onDesktopError: (callback: (message: string) => void): void => {
    ipcRenderer.on('desktop:error', (_event, message) => callback(message));
  }
});
