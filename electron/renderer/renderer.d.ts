// Type declarations for globals injected at runtime in the renderer process.
// - window.copilotDesktop is exposed by electron/preload.ts via contextBridge
// - window.LiveMediaUtils is exposed by electron/live/media_utils.ts (plain script)
// - window.LiveMediaController is exposed by electron/renderer/live_media.ts (plain script)

interface CopilotDesktopApi {
  bridgeBaseUrl: string;
  eventsUrl: string;
  getConfig: () => Promise<{
    hotkey: string;
    demoMode: boolean;
    livePreviewFps: number;
    livePreviewMaxWidth: number;
    livePreviewJpegQuality: number;
    liveMicSampleRate: number;
    screenshotJpegQuality: number;
  }>;
  getState: () => Promise<{
    session_id?: string;
    status_message?: string;
    permission_warning?: string;
    confirmation_message?: string;
    analysis?: RendererAnalysisResult | null;
    demo_mode?: boolean;
  }>;
  capture: () => Promise<unknown>;
  dismiss: () => Promise<unknown>;
  flag: (overrideNote: string) => Promise<unknown>;
  sendLiveText: (text: string) => Promise<unknown>;
  startMic: () => Promise<unknown>;
  stopMic: () => Promise<unknown>;
  getLiveState: () => Promise<{
    live?: {
      connected?: boolean;
      message?: string;
      phase?: string;
      mic_active?: boolean;
    };
    transcript_entries?: RendererTranscriptEntry[];
    screenshot_history?: RendererScreenshotEntry[];
    session_id?: string;
  }>;
  getLiveMediaAccessStatus: (mediaType: string) => Promise<{ status: string; message: string } | null>;
  prepareLiveMediaAccess: (mediaType: string) => Promise<{ status: string; message: string } | null>;
  openLiveMediaSettings: (mediaType: string) => Promise<unknown>;
  setIgnoreMouse: (ignore: boolean) => void;
  hideWindow: () => Promise<unknown>;
  showWindow: () => Promise<unknown>;
  setWindowMode: (mode: string) => Promise<unknown>;
  markLiveRendererReady: () => Promise<unknown>;
  sendLivePreviewFrame: (frame: unknown) => void;
  sendLiveAudioChunk: (chunk: unknown) => void;
  sendLiveAudioStreamEnd: () => void;
  setLiveMicState: (active: boolean) => void;
  reportLiveMediaError: (code: string, message: string) => void;
  respondLiveCommand: (requestId: string, payload: unknown, error: unknown) => void;
  onLiveCommand: (callback: (command: RendererLiveCommand) => void) => void;
  onLiveEvent: (callback: (liveEvent: RendererAppEvent) => void) => void;
  onWindowModeChange: (callback: (payload: { mode?: string }) => void) => void;
  onDesktopError: (callback: (message: string) => void) => void;
}

interface LiveMediaUtilsApi {
  base64ToBytes: (base64: string) => Uint8Array;
  bytesToBase64: (value: Uint8Array) => string;
  downsampleFloat32ToPcm16: (input: Float32Array, inputRate: number, outputRate: number) => Int16Array;
  float32ToPcm16: (input: Float32Array) => Int16Array;
  hashBytes: (value: Uint8Array) => Promise<string>;
  pcm16ToBytes: (value: Int16Array) => Uint8Array;
  pcm16ToFloat32: (value: Uint8Array) => Float32Array;
}

interface LiveMediaControllerOptions {
  desktop: CopilotDesktopApi;
  previewFps: number;
  previewMaxWidth: number;
  previewJpegQuality: number;
  micSampleRate: number;
  screenshotJpegQuality: number;
}

interface LiveMediaControllerClass {
  bootstrap: () => Promise<void>;
  handleLiveEvent: (event: RendererAppEvent) => Promise<void>;
  handleCommand: (command: RendererLiveCommand) => Promise<void>;
}

interface RendererAnalysisResult {
  finding: string;
  confidence: string;
  image_hash: string;
  recommendation: string;
  specialist_flags: string[];
}

interface RendererTranscriptEntry {
  role: string;
  text: string;
}

interface RendererScreenshotEntry {
  request_id?: string;
  reason?: string;
  image_hash?: string;
  image_b64?: string;
  backend_status?: string;
  status?: string;
}

interface RendererLiveCommand {
  requestId: string;
  type: string;
  payload?: Record<string, unknown>;
}

interface RendererAppEvent {
  type: string;
  message?: string;
  finding?: string;
  confidence?: string;
  image_hash?: string;
  recommendation?: string;
  specialist_flags?: string[];
  connected?: boolean;
  phase?: string;
  active?: boolean;
  role?: string;
  text?: string;
  is_final?: boolean;
  event?: RendererScreenshotEntry;
  data?: string;
  mime_type?: string;
}

interface Window {
  copilotDesktop: CopilotDesktopApi;
  LiveMediaUtils: LiveMediaUtilsApi;
  LiveMediaController: new (options: LiveMediaControllerOptions) => LiveMediaControllerClass;
}
