import { GoogleGenAI } from '@google/genai';
import log from 'electron-log/main';

import {
  CALL_HOTKEY_DECLARATION,
  COMMAND_TIMEOUT_MS,
  CLOSE_OVERLAY_DECLARATION,
  MAX_RECONNECTS,
  RECONNECT_DELAY_MS,
  TAKE_SCREENSHOT_DECLARATION,
  buildLiveConnectConfig,
  getLiveRuntimeConfig,
  LiveRuntimeConfig
} from './config';
import { bytesToBase64 } from './media_utils';
import {
  AckTimeoutError,
  LiveScreenshotTransport,
  LocalWebSocketUnavailable,
  ScreenshotCapturePayload,
  ScreenshotAckPayload
} from './screenshot_transport';
import { DiagnosisState } from '../models/diagnosis_state';

// ─── Public types ────────────────────────────────────────────────────────────

export interface LiveConnectionState {
  connected: boolean;
  message: string;
  phase: string;
  mic_active: boolean;
}

export interface TranscriptEntry {
  role: string;
  text: string;
}

export interface ScreenshotHistoryEntry {
  request_id: string | null;
  sent_at: string | null;
  reason: string;
  image_hash: string | null;
  image_b64?: string;
  backend_status: string;
  error: string | null;
  status?: string;
}

export interface ServiceState {
  enabled: boolean;
  session_id: string;
  live: LiveConnectionState;
  transcript_entries: TranscriptEntry[];
  screenshot_history: ScreenshotHistoryEntry[];
  diagnosis_results: DiagnosisState[];
  monitoring_tabs: string[];
}

export interface LiveEvent {
  type: string;
  [key: string]: unknown;
}

export interface RendererCommand {
  type: string;
  payload?: Record<string, unknown>;
  timeoutMs?: number;
}

export interface RendererCommandResult {
  ok?: boolean;
  image_b64?: string;
  image_hash?: string;
  mime_type?: string;
  [key: string]: unknown;
}

export interface ScreenshotToolResult {
  status: string;
  image_id: string | null;
  description: string;
}

export interface ToolCallResult {
  status: string;
  reason?: string;
  error: string | null;
}

interface ActiveToolCall {
  cancelled: boolean;
}

interface RecoverableMessage {
  index: number;
  kind: 'client' | 'tool';
  payload: unknown;
}

interface FunctionCall {
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
}

/** Minimal interface for the Gemini Live session returned by aiClient.live.connect() */
interface LiveSession {
  sendClientContent: (payload: unknown) => void;
  sendToolResponse: (payload: unknown) => void;
  sendRealtimeInput: (payload: unknown) => void;
  close: () => void;
}

interface LiveScreenshotTransportLike {
  start: () => Promise<void>;
  close: () => Promise<void>;
  sendCapture: (payload: ScreenshotCapturePayload) => Promise<ScreenshotAckPayload>;
}

export interface ElectronLiveServiceOptions {
  runtimeConfig?: LiveRuntimeConfig;
  eventSink?: (event: LiveEvent) => void;
  hotkeyTrigger?: () => Promise<unknown>;
  closeOverlayTrigger?: () => Promise<unknown>;
  rendererRequest?: (command: RendererCommand) => Promise<RendererCommandResult>;
  aiClient?: { live: { connect: (options: unknown) => Promise<LiveSession> } } | null;
  screenshotTransport?: LiveScreenshotTransportLike;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function cloneState(state: ServiceState): ServiceState {
  return {
    live: {
      connected: state.live.connected,
      message: state.live.message,
      phase: state.live.phase,
      mic_active: state.live.mic_active
    },
    transcript_entries: state.transcript_entries.map((entry) => ({ ...entry })),
    screenshot_history: state.screenshot_history.map((entry) => ({ ...entry })),
    session_id: state.session_id || '',
    enabled: state.enabled,
    diagnosis_results: state.diagnosis_results.map((d) => ({ ...d })),
    monitoring_tabs: [...state.monitoring_tabs]
  };
}

// ─── ElectronLiveService ─────────────────────────────────────────────────────

export class ElectronLiveService {
  runtimeConfig: LiveRuntimeConfig;
  eventSink: (event: LiveEvent) => void;
  hotkeyTrigger: () => Promise<unknown>;
  closeOverlayTrigger: () => Promise<unknown>;
  rendererRequest: (command: RendererCommand) => Promise<RendererCommandResult>;
  aiClient: { live: { connect: (options: unknown) => Promise<LiveSession> } } | null;

  _state: ServiceState;
  _stopRequested: boolean;
  _connectLoopPromise: Promise<void> | null;
  _session: LiveSession | null;
  _sessionClosedResolver: (() => void) | null;
  _sessionResumptionHandle: string;
  _recoverableMessages: RecoverableMessage[];
  _nextClientMessageIndex: number;
  _assistantOutputBuffer: string;
  _assistantModelBuffer: string;
  _turnAssistantEmissions: Set<string>;
  _pendingReconnectReason: string;
  _activeToolCalls: Map<string, ActiveToolCall>;
  _hasVisualInput: boolean;
  _visualAvailability: 'pending' | 'ready' | 'unavailable';
  _autoStartMicPending: boolean;
  _diagnosisStreamController: AbortController | null;

  constructor(options: ElectronLiveServiceOptions = {}) {
    this.runtimeConfig = options.runtimeConfig || getLiveRuntimeConfig();
    this.eventSink = options.eventSink || function noop() {};
    this.hotkeyTrigger =
      options.hotkeyTrigger ||
      (async function noopHotkey() {
        return { ok: false, error: 'Hotkey trigger not configured' };
      });
    this.closeOverlayTrigger =
      options.closeOverlayTrigger ||
      (async function noopCloseOverlay() {
        return { ok: false, error: 'Close overlay trigger not configured' };
      });
    this.rendererRequest =
      options.rendererRequest ||
      (async function unavailableRendererRequest() {
        throw Object.assign(new Error('Live renderer is not ready'), {
          code: 'renderer_unavailable'
        });
      });
    const genAi = this.runtimeConfig.enabled
      ? new GoogleGenAI({ apiKey: this.runtimeConfig.apiKey })
      : null;
    this.aiClient =
      options.aiClient !== undefined
        ? options.aiClient
        : (genAi as unknown as typeof this.aiClient);

    this._state = {
      enabled: this.runtimeConfig.enabled,
      session_id: '',
      live: {
        connected: false,
        message: this.runtimeConfig.initialMessage,
        phase: '',
        mic_active: false
      },
      transcript_entries: [],
      screenshot_history: [],
      diagnosis_results: [], 
      monitoring_tabs: []
    };

    this._stopRequested = false;
    this._connectLoopPromise = null;
    this._session = null;
    this._sessionClosedResolver = null;
    this._sessionResumptionHandle = '';
    this._recoverableMessages = [];
    this._nextClientMessageIndex = 0;
    this._assistantOutputBuffer = '';
    this._assistantModelBuffer = '';
    this._turnAssistantEmissions = new Set();
    this._pendingReconnectReason = '';
    this._activeToolCalls = new Map();
    this._hasVisualInput = false;
    this._visualAvailability = 'pending';
    this._autoStartMicPending = false;
    this._diagnosisStreamController = null;
  }

  getState(): ServiceState {
    return cloneState(this._state);
  }

  async start(): Promise<void> {
    log.info('[live] start() called — enabled=%s, model=%s, apiKey=%s',
      this.runtimeConfig.enabled,
      this.runtimeConfig.model,
      this.runtimeConfig.apiKey ? '***' + this.runtimeConfig.apiKey.slice(-4) : '(none)');
    if (!this.runtimeConfig.enabled || this._connectLoopPromise) {
      log.info('[live] start() skipped — enabled=%s, loopRunning=%s',
        this.runtimeConfig.enabled, Boolean(this._connectLoopPromise));
      return;
    }

    this._stopRequested = false;
    this._connectLoopPromise = this._runConnectLoop();
    this._diagnosisStreamController = new AbortController();
    this._subscribeToDiagnosisUpdates(this._diagnosisStreamController.signal).catch(() => {});
  }

  async stop(): Promise<void> {
    this._stopRequested = true;
    this._pendingReconnectReason = '';
    await this._stopMicCapture({ silent: true });

    if (this._session) {
      try {
        this._session.close();
      } catch (error) {
        // Ignore close failures while shutting down.
      }
    }

    if (this._diagnosisStreamController) {
      this._diagnosisStreamController.abort();
      this._diagnosisStreamController = null;
    }

    if (this._connectLoopPromise) {
      await this._connectLoopPromise.catch(function ignore() {});
      this._connectLoopPromise = null;
    }

    this._emitConnection(false, 'Gemini Live disconnected');
  }

  async sendText(text: string): Promise<{ ok: boolean }> {
    const cleaned = String(text || '').trim();
    if (!cleaned) {
      return { ok: true };
    }
    this._assertEnabled();
    this._assertConnected();

    await this._requestPreviewRefresh();
    this._appendTranscriptEntry('user', cleaned);
    this.eventSink({
      type: 'live.message',
      role: 'user',
      text: cleaned
    });
    this._sendClientContent(
      {
        turns: {
          role: 'user',
          parts: [{ text: this._decorateUserText(cleaned) }]
        },
        turnComplete: true
      },
      { replayable: true }
    );
    return { ok: true };
  }

  async startMicCapture(): Promise<{ ok: boolean }> {
    log.info('[live] startMicCapture() called');
    this._assertEnabled();
    this._assertConnected();

    if (this._state.live.mic_active) {
      return { ok: true };
    }

    try {
      await this.rendererRequest({
        type: 'live.start_mic',
        timeoutMs: COMMAND_TIMEOUT_MS
      });
    } catch (error) {
      const err = error as { code?: string; message?: string };
      this.notifyRendererError(
        err && err.code ? err.code : 'renderer_error',
        err && err.message ? err.message : 'Unable to start microphone capture'
      );
      throw error;
    }
    log.info('[live] Mic started — sampleRate=%d', this.runtimeConfig.micSampleRate);
    this._setMicActive(true);
    this._setPhase('Listening continuously');
    await this._requestPreviewRefresh();
    return { ok: true };
  }

  async stopMicCapture(): Promise<{ ok: boolean }> {
    if (!this.runtimeConfig.enabled) {
      return { ok: true };
    }

    await this._stopMicCapture({ silent: false });
    return { ok: true };
  }

  async submitPreviewFrame(frame: { bytes: Uint8Array; mimeType?: string } | null): Promise<void> {
    if (!this._state.live.connected || !this._session || !frame || !frame.bytes) {
      return;
    }

    if (!this._hasVisualInput) {
      log.info('[live] First preview frame received — enabling visual input');
      this._hasVisualInput = true;
      this._visualAvailability = 'ready';
      this._emitSystemMessage('[live] Screen preview ready');
      this._emitPermissionWarning('');
      if (!this._state.live.mic_active && !this._autoStartMicPending) {
        this._setPhase('Watching screen');
      }
      if (this._autoStartMicPending) {
        this._autoStartMicPending = false;
        try {
          await this.startMicCapture();
        } catch (error) {
          const err = error as Error;
          this._emitSystemMessage(`[live] Auto-mic failed: ${err.message}`);
        }
      }
    }

    this._session.sendRealtimeInput({
      video: {
        data: bytesToBase64(frame.bytes),
        mimeType: frame.mimeType || 'image/jpeg'
      }
    });
  }

  async submitAudioChunk(bytes: Uint8Array | null): Promise<void> {
    if (!this._state.live.connected || !this._session || !bytes) {
      return;
    }

    this._session.sendRealtimeInput({
      audio: {
        data: bytesToBase64(bytes),
        mimeType: `audio/pcm;rate=${this.runtimeConfig.micSampleRate}`
      }
    });
  }

  async submitAudioStreamEnd(): Promise<void> {
    if (!this._state.live.connected || !this._session) {
      return;
    }

    this._session.sendRealtimeInput({
      audioStreamEnd: true
    });
  }

  notifyMicState(active: boolean): void {
    this._setMicActive(Boolean(active));
    if (active) {
      this._emitPermissionWarning('');
    }
  }

  notifyRendererError(code: string, message: string): void {
    log.error('[live] Renderer error: code=%s message=%s', code, message);
    const errorMessage = message || 'Live media error';
    if (code === 'screen_unavailable' || code === 'screen_capture_failed') {
      this._hasVisualInput = false;
      this._visualAvailability = 'unavailable';
      this._autoStartMicPending = false;
      if (this._state.live.connected && !this._state.live.mic_active) {
        this._setPhase('Screen preview unavailable');
      }
    }
    this._emitSystemMessage(`[live] ${errorMessage}`);
    if (
      code === 'mic_unavailable' ||
      code === 'screen_unavailable' ||
      code === 'screen_capture_failed'
    ) {
      this._emitPermissionWarning(errorMessage);
    }
    if (code === 'mic_unavailable') {
      this._setMicActive(false);
      if (this._state.live.connected) {
        this._setPhase('Text only');
      }
    }
  }

  private async _runConnectLoop(): Promise<void> {
    let reconnects = 0;

    while (!this._stopRequested && reconnects < MAX_RECONNECTS) {
      if (reconnects > 0) {
        this._emitSystemMessage(
          `[live] Reconnecting (${reconnects}/${MAX_RECONNECTS})...`
        );
        await sleep(RECONNECT_DELAY_MS);
      }

      const shouldReconnect = await this._connectOnce();
      if (!shouldReconnect) {
        return;
      }
      reconnects += 1;
    }

    if (!this._stopRequested && reconnects >= MAX_RECONNECTS) {
      this._emitSystemMessage(
        `[live] Max reconnects (${MAX_RECONNECTS}) reached, stopping.`
      );
      this._emitConnection(false, 'Gemini Live unavailable');
    }
  }

  _emitPermissionWarning(message: string): void {
    this.eventSink({
      type: 'permission.warning',
      message: message || ''
    });
  }

  private async _connectOnce(): Promise<boolean> {
    log.info('[live] _connectOnce() — connecting to model=%s', this.runtimeConfig.model);
    let closed = false;
    const closeInfo = await new Promise<{ message: string }>(async (resolve) => {
      try {
        this._session = await this.aiClient!.live.connect({
          model: this.runtimeConfig.model,
          config: buildLiveConnectConfig(
            this.runtimeConfig,
            this._sessionResumptionHandle
          ),
          callbacks: {
            onopen: () => {
              log.info('[live] WebSocket opened — model=%s', this.runtimeConfig.model);
              this._emitConnection(true, `Gemini Live connected: ${this.runtimeConfig.model}`);
            },
            onmessage: (message: unknown) => {
              void this._handleServerMessage(message as Record<string, unknown>);
            },
            onerror: (event: unknown) => {
              const ev = event as { error?: { message?: string }; message?: string };
              const message =
                ev && ev.error && ev.error.message
                  ? ev.error.message
                  : ev && ev.message
                    ? ev.message
                    : 'Gemini Live socket error';
              log.error('[live] WebSocket error:', message);
              this._emitSystemMessage(`[live] ${message}`);
            },
            onclose: (event: unknown) => {
              const ev = event as { code?: number; reason?: string };
              log.info('[live] WebSocket closed — code=%s reason=%s',
                ev && ev.code, ev && ev.reason);
              if (closed) {
                return;
              }
              closed = true;
              resolve({
                message:
                  this._pendingReconnectReason ||
                  (ev && ev.reason) ||
                  'Gemini Live unavailable'
              });
            }
          }
        });

        log.info('[live] live.connect() resolved — session ready');
        this._hasVisualInput = false;
        this._visualAvailability = 'pending';
        this._autoStartMicPending =
          String(this.runtimeConfig.micMode || '').trim().toLowerCase() === 'continuous';
        await this._replayRecoverableMessages();
      } catch (error) {
        const err = error as Error;
        log.error('[live] live.connect() failed:', err.message || err);
        closed = true;
        resolve({
          message: err.message || String(err)
        });
      }
    });

    this._session = null;
    await this._stopMicCapture({ silent: true });

    if (this._stopRequested) {
      return false;
    }

    const disconnectMessage = this._pendingReconnectReason
      ? this._pendingReconnectReason
      : closeInfo.message || 'Gemini Live unavailable';
    this._pendingReconnectReason = '';
    this._emitConnection(false, disconnectMessage);
    return true;
  }

  private async _handleServerMessage(message: Record<string, unknown>): Promise<void> {
    const setupComplete = message.setupComplete as { sessionId?: string } | undefined;
    if (setupComplete && setupComplete.sessionId) {
      this._state.session_id = setupComplete.sessionId;
    }

    if (message.sessionResumptionUpdate) {
      this._updateSessionResumption(message.sessionResumptionUpdate as Record<string, unknown>);
    }

    const toolCallCancellation = message.toolCallCancellation as { ids?: string[] } | undefined;
    if (toolCallCancellation && Array.isArray(toolCallCancellation.ids)) {
      this._handleToolCallCancellation(toolCallCancellation.ids);
    }

    if (message.serverContent) {
      this._handleServerContent(message.serverContent as Record<string, unknown>);
    }

    const toolCall = message.toolCall as { functionCalls?: FunctionCall[] } | undefined;
    if (toolCall && Array.isArray(toolCall.functionCalls)) {
      await this._handleToolCalls(toolCall.functionCalls);
    }

    const goAway = message.goAway as { timeLeft?: string } | undefined;
    if (goAway) {
      const timeLeft = goAway.timeLeft ? ` (${goAway.timeLeft} left)` : '';
      this._pendingReconnectReason = `Gemini Live requested reconnect${timeLeft}`;
      if (this._session) {
        this._session.close();
      }
    }
  }

  private _handleServerContent(serverContent: Record<string, unknown>): void {
    if (serverContent.interrupted) {
      this.eventSink({ type: 'live.audio_clear' });
      this._setPhase(this._state.live.mic_active ? 'Listening continuously' : 'Waiting for input');
    }

    interface ModelPart {
      inlineData?: { mimeType?: string; data?: string };
      text?: string;
    }
    const modelTurn = serverContent.modelTurn as { parts?: ModelPart[] } | undefined;
    const modelParts: ModelPart[] =
      modelTurn && Array.isArray(modelTurn.parts)
        ? modelTurn.parts
        : [];
    const textParts: string[] = [];

    for (const part of modelParts) {
      if (part.inlineData && part.inlineData.mimeType && part.inlineData.data) {
        if (String(part.inlineData.mimeType).startsWith('audio/')) {
          this.eventSink({
            type: 'live.audio',
            data: part.inlineData.data,
            mime_type: part.inlineData.mimeType
          });
        }
      }

      if (part.text) {
        textParts.push(String(part.text));
      }
    }

    if (textParts.length) {
      this._assistantModelBuffer = textParts.join('\n').trim();
    }

    const inputTranscription = serverContent.inputTranscription as {
      finished?: boolean;
      text?: string;
    } | undefined;
    if (
      inputTranscription &&
      inputTranscription.finished &&
      inputTranscription.text
    ) {
      const text = String(inputTranscription.text).trim();
      if (text) {
        this._appendTranscriptEntry('user', text);
        this.eventSink({
          type: 'live.user_transcript',
          text,
          is_final: true
        });
      }
    }

    const outputTranscription = serverContent.outputTranscription as {
      text?: string;
      finished?: boolean;
    } | undefined;
    if (outputTranscription && outputTranscription.text) {
      this._assistantOutputBuffer = String(outputTranscription.text).trim();
      if (outputTranscription.finished) {
        this._emitAssistantText(this._assistantOutputBuffer);
      }
    }

    if (serverContent.waitingForInput) {
      this._setPhase('Waiting for input');
    }

    if (serverContent.turnComplete || serverContent.generationComplete) {
      this._setPhase(this._state.live.mic_active ? 'Listening continuously' : 'Waiting for input');
      const fallback = this._assistantOutputBuffer || this._assistantModelBuffer;
      if (fallback) {
        this._emitAssistantText(fallback);
      }
      this._assistantOutputBuffer = '';
      this._assistantModelBuffer = '';
      this._turnAssistantEmissions.clear();
    }
  }

  async _handleToolCalls(functionCalls: FunctionCall[]): Promise<void> {
    for (const functionCall of functionCalls) {
      const functionName = functionCall.name || '';
      const functionCallId = functionCall.id || '';
      const args = functionCall.args || {};

      if (!functionCallId) {
        continue;
      }

      this._activeToolCalls.set(functionCallId, {
        cancelled: false
      });

      log.info('[live] Tool call: name=%s id=%s args=%j', functionName, functionCallId, args);

      let result: ScreenshotToolResult | ToolCallResult;
      if (functionName === TAKE_SCREENSHOT_DECLARATION.name) {
        result = await this._captureAndSendScreenshot(args, functionCallId);
      } else if (functionName === CALL_HOTKEY_DECLARATION.name) {
        result = await this._triggerHotkey(args);
      } else if (functionName === CLOSE_OVERLAY_DECLARATION.name) {
        result = await this._triggerCloseOverlay(args);
      } else {
        result = {
          status: 'error',
          image_id: null,
          error: `Unsupported tool: ${functionName}`
        };
      }

      const pending = this._activeToolCalls.get(functionCallId);
      this._activeToolCalls.delete(functionCallId);
      if (!pending || pending.cancelled || !this._session) {
        continue;
      }

      this._sendToolResponse(
        {
          functionResponses: [
            {
              id: functionCallId,
              name: functionName,
              response: result,
              scheduling: this.runtimeConfig.functionResponseScheduling
            }
          ]
        },
        { replayable: true }
      );
    }
  }

  _handleToolCallCancellation(ids: string[]): void {
    for (const id of ids) {
      const pending = this._activeToolCalls.get(id);
      if (pending) {
        pending.cancelled = true;
      }
    }
  }

  private async _captureAndSendScreenshot(
    args: Record<string, unknown>,
    functionCallId: string
  ): Promise<ScreenshotToolResult> {
    const requestId = crypto.randomUUID();
    const sentAt = new Date().toISOString();
    const reason =
      typeof args.reason === 'string' && args.reason.trim()
        ? args.reason.trim()
        : 'Gemini requested a screenshot';

    let capture: RendererCommandResult;
    try {
      capture = await this.rendererRequest({
        type: 'live.capture_screenshot',
        payload: { reason },
        timeoutMs: COMMAND_TIMEOUT_MS
      });
    } catch (error) {
      return this._buildScreenshotErrorResponse(requestId, sentAt, error as Error, null);
    }

    const imageBase64 = capture && capture.image_b64 ? capture.image_b64 : '';
    const imageHash = capture && capture.image_hash ? capture.image_hash : '';
    const pendingEvent: ScreenshotHistoryEntry = {
      request_id: requestId,
      sent_at: sentAt,
      reason,
      image_hash: imageHash,
      image_b64: imageBase64,
      backend_status: 'pending',
      error: null
    };
    this._upsertScreenshot(pendingEvent);


    try {
      const ack = await fetch("http://localhost:8000/get_image_id", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          image_hash: {
            "image_base64": imageBase64,
          }
        })
      });

      const data = await ack.json()

      const activeToolCall = this._activeToolCalls.get(functionCallId);
      if (activeToolCall && activeToolCall.cancelled) {
        return {
          status: 'error',
          image_id: requestId,
          description: 'Tool call was cancelled before completion'
        };
      }

      if (!ack.ok) {
        const failedResult: ScreenshotToolResult = {
          status: 'error',
          image_id: requestId,
          description: String(ack.body) || 'Local backend returned an error ack'
        };
        this._upsertScreenshot({
          ...pendingEvent,
          ...failedResult
        });
        return failedResult;
      }

      const image_id = (data as {pass: string, status: string, image_id: string}).image_id;
      if(this._state.monitoring_tabs.includes(image_id)) {
        return {
          status: 'ok',
          image_id: requestId,
          description: 'This image id already exists in our local _state, use your tools in order to navigate the UI to this tab because it already exists'
        };
      }

      if (image_id) {
        const rawImageResponse = await fetch(`http://localhost:8000/database/raw_image/${image_id}`);

        if (rawImageResponse.ok) {
          const rawImageData = await rawImageResponse.json();
          this.eventSink({
            type: 'live.raw_image',
            image_id,
            image_b64: rawImageData.image_b64
          });
        }

        if (!this._state.monitoring_tabs.includes(image_id)) {
          this._state.monitoring_tabs.push(image_id);
        }
        this._emitDiagnosisUpdate();
        void this._pollDiagnosis(image_id);
      }

      const result: ScreenshotToolResult = {
        status: 'ok',
        image_id: requestId,
        description: 'Screenshot captured and acknowledged by local backend'
      };
      this._upsertScreenshot({
        ...pendingEvent,
        ...result
      });
      return result;
    } catch (error) {
      const failedResult = this._buildScreenshotErrorResponse(
        requestId,
        sentAt,
        error as Error,
        imageHash
      );
      this._upsertScreenshot({
        ...pendingEvent,
        ...failedResult
      });
      return failedResult;
    }
  }

  private async _triggerHotkey(args: Record<string, unknown>): Promise<ToolCallResult> {
    const reason =
      typeof args.reason === 'string' && args.reason.trim()
        ? args.reason.trim()
        : 'User requested hotkey';

    try {
      await this.hotkeyTrigger();
      this._emitSystemMessage(`[live] Hotkey triggered: ${reason}`);
      return { status: 'ok', reason, error: null };
    } catch (error) {
      const err = error as Error;
      const message = err && err.message ? err.message : String(err);
      this._emitSystemMessage(`[live] Hotkey trigger failed: ${message}`);
      return { status: 'error', reason, error: message };
    }
  }

  private async _triggerCloseOverlay(args: Record<string, unknown>): Promise<ToolCallResult> {
    const reason =
      typeof args.reason === 'string' && args.reason.trim()
        ? args.reason.trim()
        : 'User requested close';

    try {
      await this.closeOverlayTrigger();
      this._emitSystemMessage(`[live] Overlay closed: ${reason}`);
      return { status: 'ok', reason, error: null };
    } catch (error) {
      const err = error as Error;
      const message = err && err.message ? err.message : String(err);
      this._emitSystemMessage(`[live] Overlay close failed: ${message}`);
      return { status: 'error', reason, error: message };
    }
  }

  private async _pollDiagnosis(image_id: string): Promise<void> {
    const maxAttempts = 10;
    const intervalMs = 2000;

    for (let i = 0; i < maxAttempts; i++) {
      try {
        const response = await fetch(`http://localhost:8000/database/diagnosis/${image_id}`);
        if (response.ok) {
          const data = await response.json() as {
            image_id: string;
            progress_tree: DiagnosisState['progress_tree'];
            percent_completion: number;
            annotations: DiagnosisState['annotations'];
            overall_diagnosis_context: string;
          };

          const diagnosisState: DiagnosisState = {
            diagnosis_id: data.image_id,
            progress_tree: data.progress_tree,
            percent_completion: data.percent_completion,
            annotations: data.annotations,
            overall_diagnosis_context: data.overall_diagnosis_context
          };

          const idx = this._state.diagnosis_results.findIndex(
            d => d.diagnosis_id === image_id
          );
          if (idx === -1) {
            this._state.diagnosis_results.push(diagnosisState);
          } else {
            this._state.diagnosis_results[idx] = diagnosisState;
          }

          this.eventSink({ type: 'live.diagnosis', diagnosis: diagnosisState });

          if (data.percent_completion >= 1.0) break;
        }
      } catch {
        // retry on next interval
      }

      await new Promise<void>(r => setTimeout(r, intervalMs));
    }
  }

  private _buildScreenshotErrorResponse(
    requestId: string,
    sentAt: string,
    error: Error,
    imageHash: string | null
  ): ScreenshotToolResult {
    return {
      status: 'error',
      image_id: requestId,
      description: error && error.message ? error.message : String(error)
    };
  }

  private _classifyScreenshotError(error: Error & { code?: string }): string {
    if (error instanceof AckTimeoutError) {
      return 'ack_timeout';
    }
    if (error instanceof LocalWebSocketUnavailable) {
      return 'socket_unavailable';
    }
    if (error && error.code === 'permission_denied') {
      return 'permission_denied';
    }
    if (error && error.code === 'renderer_unavailable') {
      return 'socket_unavailable';
    }
    return 'capture_failed';
  }

  _updateSessionResumption(update: Record<string, unknown>): void {
    if (update.newHandle) {
      this._sessionResumptionHandle = String(update.newHandle);
    }

    if (update.lastConsumedClientMessageIndex == null) {
      return;
    }

    const lastConsumed = Number.parseInt(String(update.lastConsumedClientMessageIndex), 10);
    if (!Number.isFinite(lastConsumed)) {
      return;
    }

    this._recoverableMessages = this._recoverableMessages.filter(
      (entry) => entry.index > lastConsumed
    );
  }

  async _replayRecoverableMessages(): Promise<void> {
    if (!this._session || !this._recoverableMessages.length) {
      return;
    }

    const pending = [...this._recoverableMessages].sort((left, right) => left.index - right.index);
    this._recoverableMessages = [];
    for (const entry of pending) {
      if (!this._session) {
        break;
      }

      if (entry.kind === 'client') {
        this._sendClientContent(entry.payload, { replayable: true });
      } else if (entry.kind === 'tool') {
        this._sendToolResponse(entry.payload, { replayable: true });
      }
    }
  }

  private _sendClientContent(payload: unknown, options: { replayable?: boolean } = {}): void {
    this._assertConnected();
    this._session!.sendClientContent(payload);
    if (options.replayable) {
      this._recordRecoverableMessage('client', payload);
    }
  }

  private _sendToolResponse(payload: unknown, options: { replayable?: boolean } = {}): void {
    this._assertConnected();
    this._session!.sendToolResponse(payload);
    if (options.replayable) {
      this._recordRecoverableMessage('tool', payload);
    }
  }

  _recordRecoverableMessage(kind: 'client' | 'tool', payload: unknown): void {
    if (!this.runtimeConfig.transparentSessionResumption) {
      return;
    }
    this._recoverableMessages.push({
      index: this._nextClientMessageIndex,
      kind,
      payload
    });
    this._nextClientMessageIndex += 1;
  }

  private _decorateUserText(text: string): string {
    const cleaned = String(text || '').trim();
    if (!cleaned) {
      return '';
    }

    if (this._visualAvailability === 'unavailable') {
      return (
        `${cleaned}\n\n` +
        '[System note: Live display capture is currently unavailable. ' +
        'Do not claim to see the screen. If visual context is required, say that screen sharing is unavailable.]'
      );
    }

    if (!this._hasVisualInput) {
      return (
        `${cleaned}\n\n` +
        '[System note: No preview frame or screenshot has been received in this session yet. ' +
        'Do not claim to see the screen or infer on-screen details until visual input arrives.]'
      );
    }

    return cleaned;
  }

  private _appendTranscriptEntry(role: string, text: string): void {
    const cleaned = String(text || '').trim();
    if (!cleaned) {
      return;
    }
    this._state.transcript_entries.push({ role, text: cleaned });
    this._state.transcript_entries = this._state.transcript_entries.slice(-100);
  }

  private async _subscribeToDiagnosisUpdates(signal: AbortSignal): Promise<void> {
    while (!signal.aborted) {
      try {
        const response = await fetch('http://localhost:8000/database/diagnosis/stream', { signal });
        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop()!;

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                this._handleDiagnosisUpdate(data);
              } catch {
                // ignore malformed SSE data
              }
            }
          }
        }
      } catch {
        if (signal.aborted) break;
        await sleep(3000);
      }
    }
  }

  private _handleDiagnosisUpdate(data: Record<string, unknown>): void {
    const image_id = data.image_id as string;
    if (!image_id || !this._state.monitoring_tabs.includes(image_id)) return;

    const diagnosisState: DiagnosisState = {
      diagnosis_id: image_id,
      progress_tree: data.progress_tree as DiagnosisState['progress_tree'],
      percent_completion: data.percent_completion as number,
      annotations: data.annotations as DiagnosisState['annotations'],
      overall_diagnosis_context: data.overall_diagnosis_context as string
    };

    const index = this._state.diagnosis_results.findIndex((d) => d.diagnosis_id === image_id);
    if (index !== -1) {
      this._state.diagnosis_results[index] = diagnosisState;
    } else {
      this._state.diagnosis_results.push(diagnosisState);
    }

    this._emitDiagnosisUpdate();
  }

  private _emitDiagnosisUpdate(): void {
    this.eventSink({
      type: 'live.diagnosis_update',
      diagnosis_results: this._state.diagnosis_results.map((d) => ({ ...d })),
      monitoring_tabs: [...this._state.monitoring_tabs]
    });
  }

  private _upsertScreenshot(entry: ScreenshotHistoryEntry): void {
    const requestId = entry.request_id;
    const history = this._state.screenshot_history;
    const currentIndex = history.findIndex((item) => item.request_id === requestId);
    if (currentIndex === -1) {
      history.unshift(entry);
    } else {
      history[currentIndex] = entry;
      if (currentIndex !== 0) {
        history.unshift(history.splice(currentIndex, 1)[0]);
      }
    }
    this._state.screenshot_history = history.slice(0, 5);
    this.eventSink({
      type: 'live.screenshot',
      event: { ...entry }
    });
  }

  private _emitAssistantText(text: string): void {
    const cleaned = String(text || '').trim();
    if (!cleaned || this._turnAssistantEmissions.has(cleaned)) {
      return;
    }
    this._turnAssistantEmissions.add(cleaned);
    this._appendTranscriptEntry('assistant', cleaned);
    this.eventSink({
      type: 'live.message',
      role: 'assistant',
      text: cleaned
    });
  }

  private _emitSystemMessage(text: string): void {
    const cleaned = String(text || '').trim();
    if (!cleaned) {
      return;
    }
    this._appendTranscriptEntry('system', cleaned);
    this.eventSink({
      type: 'live.message',
      role: 'system',
      text: cleaned
    });
  }

  private _emitConnection(connected: boolean, message: string): void {
    log.info('[live] Connection state: connected=%s message=%s', connected, message);
    this._state.live.connected = Boolean(connected);
    this._state.live.message = message || (connected ? 'Gemini Live connected' : 'Gemini Live unavailable');
    if (!connected) {
      this._state.live.phase = '';
      this._state.live.mic_active = false;
    }
    this.eventSink({
      type: 'live.connection',
      connected: this._state.live.connected,
      message: this._state.live.message
    });
  }

  private _setPhase(phase: string): void {
    this._state.live.phase = phase || '';
    this.eventSink({
      type: 'live.phase',
      phase: this._state.live.phase
    });
  }

  private _setMicActive(active: boolean): void {
    this._state.live.mic_active = Boolean(active);
    this.eventSink({
      type: 'live.mic',
      active: this._state.live.mic_active
    });
  }

  private async _requestPreviewRefresh(): Promise<void> {
    if (!this._state.live.connected) {
      return;
    }

    try {
      await this.rendererRequest({
        type: 'live.refresh_preview',
        timeoutMs: COMMAND_TIMEOUT_MS
      });
    } catch (error) {
      const err = error as { code?: string; message?: string };
      this.notifyRendererError(err.code || 'preview_error', err.message || '');
    }
  }

  private async _stopMicCapture(options: { silent?: boolean } = {}): Promise<void> {
    const silent = Boolean(options.silent);
    try {
      await this.rendererRequest({
        type: 'live.stop_mic',
        timeoutMs: COMMAND_TIMEOUT_MS
      });
    } catch (error) {
      if (!silent) {
        const err = error as { code?: string; message?: string };
        this.notifyRendererError(err.code || 'mic_unavailable', err.message || '');
      }
    }

    if (this._state.live.connected && this._session) {
      this._session.sendRealtimeInput({
        audioStreamEnd: true
      });
    }
    this._setMicActive(false);
    if (!silent) {
      this._setPhase('Waiting for input');
    }
  }

  private _assertEnabled(): void {
    if (!this.runtimeConfig.enabled) {
      throw new Error('Gemini Live is disabled.');
    }
  }

  private _assertConnected(): void {
    if (!this._session || !this._state.live.connected) {
      throw new Error('Gemini Live session is not running');
    }
  }
}
