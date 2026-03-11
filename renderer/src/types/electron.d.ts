// Type declarations for the preload-exposed copilotDesktop API
// and global live media utilities (loaded from electron/live/media_utils.js)

export interface DesktopConfig {
  bridgeBaseUrl: string;
  eventsUrl: string;
  hotkey: string;
  demoMode: boolean;
  livePreviewFps: number;
  livePreviewMaxWidth: number;
  livePreviewJpegQuality: number;
  liveMicSampleRate: number;
  screenshotJpegQuality: number;
}

export interface MediaAccessResult {
  status: 'granted' | 'denied' | 'restricted' | 'unknown';
  message?: string;
}

export interface LiveCommandPayload {
  ok?: boolean;
  image_b64?: string;
  image_hash?: string;
  mime_type?: string;
}

export interface LiveCommand {
  requestId: string;
  type: string;
  payload: unknown;
}

export interface LiveEvent {
  type: string;
  connected?: boolean;
  message?: string;
  phase?: string;
  active?: boolean;
  role?: string;
  text?: string;
  is_final?: boolean;
  data?: string;
  event?: ScreenshotEntry;
}

export interface LiveState {
  live: {
    connected: boolean;
    message: string;
    phase: string;
    mic_active: boolean;
  };
  transcript_entries: TranscriptEntry[];
  screenshot_history: ScreenshotEntry[];
  session_id: string;
  enabled: boolean;
}

export interface BridgeState {
  session_id?: string;
  status_message?: string;
  permission_warning?: string;
  confirmation_message?: string;
  analysis?: Analysis | null;
  demo_mode?: boolean;
}

export interface Analysis {
  finding: string;
  confidence: string;
  image_hash: string;
  recommendation: string;
  specialist_flags: string[];
}

export interface TranscriptEntry {
  role: 'user' | 'assistant' | 'system';
  text: string;
}

export interface ScreenshotEntry {
  request_id?: string;
  reason?: string;
  image_hash?: string;
  image_b64?: string;
  backend_status?: string;
  status?: string;
}

export interface PreviewFrame {
  bytes: Uint8Array;
  mimeType: string;
  imageHash: string;
}

export interface AudioChunk {
  bytes: Uint8Array;
}

export interface LiveMediaControllerOptions {
  desktop: CopilotDesktopAPI;
  previewFps: number;
  previewMaxWidth: number;
  previewJpegQuality: number;
  micSampleRate: number;
  screenshotJpegQuality: number;
}

export interface ILiveMediaController {
  bootstrap(): Promise<void>;
  handleCommand(command: LiveCommand): Promise<void>;
  handleLiveEvent(event: LiveEvent): Promise<void>;
  startPreviewLoop(): Promise<void>;
  stopPreviewLoop(): void;
}

export interface CopilotDesktopAPI {
  bridgeBaseUrl: string;
  eventsUrl: string;
  getConfig(): Promise<DesktopConfig>;
  getState(): Promise<BridgeState>;
  capture(): Promise<unknown>;
  dismiss(): Promise<unknown>;
  flag(overrideNote: string): Promise<unknown>;
  sendLiveText(text: string): Promise<unknown>;
  startMic(): Promise<unknown>;
  stopMic(): Promise<unknown>;
  getLiveState(): Promise<LiveState>;
  getLiveMediaAccessStatus(mediaType: string): Promise<MediaAccessResult>;
  prepareLiveMediaAccess(mediaType: string): Promise<MediaAccessResult>;
  openLiveMediaSettings(mediaType: string): Promise<{ ok: boolean }>;
  setIgnoreMouse(ignore: boolean): void;
  hideWindow(): Promise<{ ok: boolean }>;
  showWindow(): Promise<{ ok: boolean }>;
  setWindowMode(mode: string): Promise<{ ok: boolean; mode: string }>;
  markLiveRendererReady(): Promise<{ ok: boolean }>;
  sendLivePreviewFrame(frame: PreviewFrame): void;
  sendLiveAudioChunk(chunk: AudioChunk): void;
  sendLiveAudioStreamEnd(): void;
  setLiveMicState(active: boolean): void;
  reportLiveMediaError(code: string, message: string): void;
  respondLiveCommand(requestId: string, payload: LiveCommandPayload | null, error: { code: string; message: string } | null): void;
  onLiveCommand(callback: (command: LiveCommand) => void): void;
  onLiveEvent(callback: (event: LiveEvent) => void): void;
  onDesktopError(callback: (message: string) => void): void;
  onWindowModeChange(callback: (payload: { mode: 'orb' | 'bar' }) => void): void;
}

declare global {
  interface Window {
    copilotDesktop: CopilotDesktopAPI;
    LiveMediaController: new (options: LiveMediaControllerOptions) => ILiveMediaController;
    LiveMediaUtils: {
      base64ToBytes(base64: string): Uint8Array;
      bytesToBase64(bytes: Uint8Array): string;
      downsampleFloat32ToPcm16(input: Float32Array, inputSampleRate: number, outputSampleRate: number): Int16Array;
      float32ToPcm16(input: Float32Array): Int16Array;
      hashBytes(bytes: Uint8Array): Promise<string>;
      normalizeBytes(value: unknown): Uint8Array;
      pcm16ToBytes(value: Int16Array): Uint8Array;
      pcm16ToFloat32(value: Uint8Array): Float32Array;
    };
  }
}
