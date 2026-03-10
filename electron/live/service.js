const { GoogleGenAI } = require('@google/genai');

const {
  CALL_HOTKEY_DECLARATION,
  COMMAND_TIMEOUT_MS,
  CLOSE_OVERLAY_DECLARATION,
  MAX_RECONNECTS,
  RECONNECT_DELAY_MS,
  TAKE_SCREENSHOT_DECLARATION,
  buildLiveConnectConfig,
  getLiveRuntimeConfig
} = require('./config');
const { bytesToBase64 } = require('./media_utils');
const {
  AckTimeoutError,
  LiveScreenshotTransport,
  LocalWebSocketUnavailable
} = require('./screenshot_transport');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function cloneState(state) {
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
    enabled: state.enabled
  };
}

class ElectronLiveService {
  constructor(options = {}) {
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
    this.aiClient =
      options.aiClient ||
      (this.runtimeConfig.enabled
        ? new GoogleGenAI({ apiKey: this.runtimeConfig.apiKey })
        : null);
    this.screenshotTransport =
      options.screenshotTransport ||
      new LiveScreenshotTransport({
        url: this.runtimeConfig.screenshotWsUrl,
        ackTimeoutMs: this.runtimeConfig.screenshotAckTimeoutMs,
        retryDelayMs: this.runtimeConfig.screenshotRetryDelayMs,
        onStatus: (message) => this._emitSystemMessage(message)
      });

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
      screenshot_history: []
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
  }

  getState() {
    return cloneState(this._state);
  }

  async start() {
    console.log('[live] start() called — enabled=%s, model=%s, apiKey=%s',
      this.runtimeConfig.enabled,
      this.runtimeConfig.model,
      this.runtimeConfig.apiKey ? '***' + this.runtimeConfig.apiKey.slice(-4) : '(none)');
    if (!this.runtimeConfig.enabled || this._connectLoopPromise) {
      console.log('[live] start() skipped — enabled=%s, loopRunning=%s',
        this.runtimeConfig.enabled, Boolean(this._connectLoopPromise));
      return;
    }

    await this.screenshotTransport.start();
    this._stopRequested = false;
    this._connectLoopPromise = this._runConnectLoop();
  }

  async stop() {
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

    if (this._connectLoopPromise) {
      await this._connectLoopPromise.catch(function ignore() {});
      this._connectLoopPromise = null;
    }

    await this.screenshotTransport.close();
    this._emitConnection(false, 'Gemini Live disconnected');
  }

  async sendText(text) {
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

  async startMicCapture() {
    console.log('[live] startMicCapture() called');
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
      this.notifyRendererError(
        error && error.code ? error.code : 'renderer_error',
        error && error.message ? error.message : 'Unable to start microphone capture'
      );
      throw error;
    }
    console.log('[live] Mic started — sampleRate=%d', this.runtimeConfig.micSampleRate);
    this._setMicActive(true);
    this._setPhase('Listening continuously');
    await this._requestPreviewRefresh();
    return { ok: true };
  }

  async stopMicCapture() {
    if (!this.runtimeConfig.enabled) {
      return { ok: true };
    }

    await this._stopMicCapture({ silent: false });
    return { ok: true };
  }

  async submitPreviewFrame(frame) {
    if (!this._state.live.connected || !this._session || !frame || !frame.bytes) {
      return;
    }

    if (!this._hasVisualInput) {
      console.log('[live] First preview frame received — enabling visual input');
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
          this._emitSystemMessage(`[live] Auto-mic failed: ${error.message}`);
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

  async submitAudioChunk(bytes) {
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

  async submitAudioStreamEnd() {
    if (!this._state.live.connected || !this._session) {
      return;
    }

    this._session.sendRealtimeInput({
      audioStreamEnd: true
    });
  }

  notifyMicState(active) {
    this._setMicActive(Boolean(active));
    if (active) {
      this._emitPermissionWarning('');
    }
  }

  notifyRendererError(code, message) {
    console.error('[live] Renderer error: code=%s message=%s', code, message);
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

  async _runConnectLoop() {
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

  _emitPermissionWarning(message) {
    this.eventSink({
      type: 'permission.warning',
      message: message || ''
    });
  }

  async _connectOnce() {
    console.log('[live] _connectOnce() — connecting to model=%s', this.runtimeConfig.model);
    let closed = false;
    const closeInfo = await new Promise(async (resolve) => {
      try {
        this._session = await this.aiClient.live.connect({
          model: this.runtimeConfig.model,
          config: buildLiveConnectConfig(
            this.runtimeConfig,
            this._sessionResumptionHandle
          ),
          callbacks: {
            onopen: () => {
              console.log('[live] WebSocket opened — model=%s', this.runtimeConfig.model);
              this._emitConnection(true, `Gemini Live connected: ${this.runtimeConfig.model}`);
            },
            onmessage: (message) => {
              void this._handleServerMessage(message);
            },
            onerror: (event) => {
              const message =
                event && event.error && event.error.message
                  ? event.error.message
                  : event && event.message
                    ? event.message
                    : 'Gemini Live socket error';
              console.error('[live] WebSocket error:', message);
              this._emitSystemMessage(`[live] ${message}`);
            },
            onclose: (event) => {
              console.log('[live] WebSocket closed — code=%s reason=%s',
                event && event.code, event && event.reason);
              if (closed) {
                return;
              }
              closed = true;
              resolve({
                message:
                  this._pendingReconnectReason ||
                  (event && event.reason) ||
                  'Gemini Live unavailable'
              });
            }
          }
        });

        console.log('[live] live.connect() resolved — session ready');
        this._hasVisualInput = false;
        this._visualAvailability = 'pending';
        this._autoStartMicPending =
          String(this.runtimeConfig.micMode || '').trim().toLowerCase() === 'continuous';
        await this._replayRecoverableMessages();
      } catch (error) {
        console.error('[live] live.connect() failed:', error.message || error);
        closed = true;
        resolve({
          message: error.message || String(error)
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

  async _handleServerMessage(message) {
    if (message.setupComplete && message.setupComplete.sessionId) {
      this._state.session_id = message.setupComplete.sessionId;
    }

    if (message.sessionResumptionUpdate) {
      this._updateSessionResumption(message.sessionResumptionUpdate);
    }

    if (message.toolCallCancellation && Array.isArray(message.toolCallCancellation.ids)) {
      this._handleToolCallCancellation(message.toolCallCancellation.ids);
    }

    if (message.serverContent) {
      this._handleServerContent(message.serverContent);
    }

    if (message.toolCall && Array.isArray(message.toolCall.functionCalls)) {
      await this._handleToolCalls(message.toolCall.functionCalls);
    }

    if (message.goAway) {
      const timeLeft = message.goAway.timeLeft ? ` (${message.goAway.timeLeft} left)` : '';
      this._pendingReconnectReason = `Gemini Live requested reconnect${timeLeft}`;
      if (this._session) {
        this._session.close();
      }
    }
  }

  _handleServerContent(serverContent) {
    if (serverContent.interrupted) {
      this.eventSink({ type: 'live.audio_clear' });
      this._setPhase(this._state.live.mic_active ? 'Listening continuously' : 'Waiting for input');
    }

    const modelParts =
      serverContent.modelTurn && Array.isArray(serverContent.modelTurn.parts)
        ? serverContent.modelTurn.parts
        : [];
    const textParts = [];

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

    if (
      serverContent.inputTranscription &&
      serverContent.inputTranscription.finished &&
      serverContent.inputTranscription.text
    ) {
      const text = String(serverContent.inputTranscription.text).trim();
      if (text) {
        this._appendTranscriptEntry('user', text);
        this.eventSink({
          type: 'live.user_transcript',
          text,
          is_final: true
        });
      }
    }

    if (serverContent.outputTranscription && serverContent.outputTranscription.text) {
      this._assistantOutputBuffer = String(serverContent.outputTranscription.text).trim();
      if (serverContent.outputTranscription.finished) {
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

  async _handleToolCalls(functionCalls) {
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

      console.log('[live] Tool call: name=%s id=%s args=%j', functionName, functionCallId, args);

      let result;
      if (functionName === TAKE_SCREENSHOT_DECLARATION.name) {
        result = await this._captureAndSendScreenshot(args, functionCallId);
      } else if (functionName === CALL_HOTKEY_DECLARATION.name) {
        result = await this._triggerHotkey(args);
      } else if (functionName === CLOSE_OVERLAY_DECLARATION.name) {
        result = await this._triggerCloseOverlay(args);
      } else {
        result = {
          status: 'error',
          request_id: null,
          image_hash: null,
          sent_at: null,
          backend_status: 'unsupported_tool',
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

  _handleToolCallCancellation(ids) {
    for (const id of ids) {
      const pending = this._activeToolCalls.get(id);
      if (pending) {
        pending.cancelled = true;
      }
    }
  }

  async _captureAndSendScreenshot(args, functionCallId) {
    const requestId = crypto.randomUUID();
    const sentAt = new Date().toISOString();
    const reason =
      typeof args.reason === 'string' && args.reason.trim()
        ? args.reason.trim()
        : 'Gemini requested a screenshot';

    let capture;
    try {
      capture = await this.rendererRequest({
        type: 'live.capture_screenshot',
        payload: { reason },
        timeoutMs: COMMAND_TIMEOUT_MS
      });
    } catch (error) {
      return this._buildScreenshotErrorResponse(requestId, sentAt, error, null);
    }

    const imageBase64 = capture && capture.image_b64 ? capture.image_b64 : '';
    const imageHash = capture && capture.image_hash ? capture.image_hash : '';
    const pendingEvent = {
      request_id: requestId,
      sent_at: sentAt,
      reason,
      image_hash: imageHash,
      image_b64: imageBase64,
      backend_status: 'pending',
      error: null
    };
    this._upsertScreenshot(pendingEvent);

    const payload = {
      type: 'screenshot.capture',
      request_id: requestId,
      session_id: this._state.session_id || '',
      timestamp: sentAt,
      reason,
      mime_type: capture.mime_type || 'image/jpeg',
      image_b64: imageBase64,
      image_hash: imageHash,
      source: 'gemini_live_tool'
    };

    try {
      const ack = await this.screenshotTransport.sendCapture(payload);
      const activeToolCall = this._activeToolCalls.get(functionCallId);
      if (activeToolCall && activeToolCall.cancelled) {
        return {
          status: 'error',
          request_id: requestId,
          image_hash: imageHash,
          sent_at: sentAt,
          backend_status: 'cancelled',
          error: 'Tool call was cancelled before completion'
        };
      }

      if (ack.status !== 'ok') {
        const failedResult = {
          status: 'error',
          request_id: requestId,
          image_hash: imageHash,
          sent_at: sentAt,
          backend_status: String(ack.status || 'error'),
          error: ack.error || 'Local backend returned an error ack'
        };
        this._upsertScreenshot({
          ...pendingEvent,
          ...failedResult
        });
        return failedResult;
      }

      const result = {
        status: 'ok',
        request_id: requestId,
        image_hash: imageHash,
        sent_at: sentAt,
        backend_status: 'ok',
        error: null
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
        error,
        imageHash
      );
      this._upsertScreenshot({
        ...pendingEvent,
        ...failedResult
      });
      return failedResult;
    }
  }

  async _triggerHotkey(args) {
    const reason =
      typeof args.reason === 'string' && args.reason.trim()
        ? args.reason.trim()
        : 'User requested hotkey';

    try {
      await this.hotkeyTrigger();
      this._emitSystemMessage(`[live] Hotkey triggered: ${reason}`);
      return { status: 'ok', reason, error: null };
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      this._emitSystemMessage(`[live] Hotkey trigger failed: ${message}`);
      return { status: 'error', reason, error: message };
    }
  }

  async _triggerCloseOverlay(args) {
    const reason =
      typeof args.reason === 'string' && args.reason.trim()
        ? args.reason.trim()
        : 'User requested close';

    try {
      await this.closeOverlayTrigger();
      this._emitSystemMessage(`[live] Overlay closed: ${reason}`);
      return { status: 'ok', reason, error: null };
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      this._emitSystemMessage(`[live] Overlay close failed: ${message}`);
      return { status: 'error', reason, error: message };
    }
  }

  _buildScreenshotErrorResponse(requestId, sentAt, error, imageHash) {
    return {
      status: 'error',
      request_id: requestId,
      image_hash: imageHash,
      sent_at: sentAt,
      backend_status: this._classifyScreenshotError(error),
      error: error && error.message ? error.message : String(error)
    };
  }

  _classifyScreenshotError(error) {
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

  _updateSessionResumption(update) {
    if (update.newHandle) {
      this._sessionResumptionHandle = update.newHandle;
    }

    if (update.lastConsumedClientMessageIndex == null) {
      return;
    }

    const lastConsumed = Number.parseInt(update.lastConsumedClientMessageIndex, 10);
    if (!Number.isFinite(lastConsumed)) {
      return;
    }

    this._recoverableMessages = this._recoverableMessages.filter(
      (entry) => entry.index > lastConsumed
    );
  }

  async _replayRecoverableMessages() {
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

  _sendClientContent(payload, options = {}) {
    this._assertConnected();
    this._session.sendClientContent(payload);
    if (options.replayable) {
      this._recordRecoverableMessage('client', payload);
    }
  }

  _sendToolResponse(payload, options = {}) {
    this._assertConnected();
    this._session.sendToolResponse(payload);
    if (options.replayable) {
      this._recordRecoverableMessage('tool', payload);
    }
  }

  _recordRecoverableMessage(kind, payload) {
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

  _decorateUserText(text) {
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

  _appendTranscriptEntry(role, text) {
    const cleaned = String(text || '').trim();
    if (!cleaned) {
      return;
    }
    this._state.transcript_entries.push({ role, text: cleaned });
    this._state.transcript_entries = this._state.transcript_entries.slice(-100);
  }

  _upsertScreenshot(entry) {
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

  _emitAssistantText(text) {
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

  _emitSystemMessage(text) {
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

  _emitConnection(connected, message) {
    console.log('[live] Connection state: connected=%s message=%s', connected, message);
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

  _setPhase(phase) {
    this._state.live.phase = phase || '';
    this.eventSink({
      type: 'live.phase',
      phase: this._state.live.phase
    });
  }

  _setMicActive(active) {
    this._state.live.mic_active = Boolean(active);
    this.eventSink({
      type: 'live.mic',
      active: this._state.live.mic_active
    });
  }

  async _requestPreviewRefresh() {
    if (!this._state.live.connected) {
      return;
    }

    try {
      await this.rendererRequest({
        type: 'live.refresh_preview',
        timeoutMs: COMMAND_TIMEOUT_MS
      });
    } catch (error) {
      this.notifyRendererError(error.code || 'preview_error', error.message);
    }
  }

  async _stopMicCapture(options = {}) {
    const silent = Boolean(options.silent);
    try {
      await this.rendererRequest({
        type: 'live.stop_mic',
        timeoutMs: COMMAND_TIMEOUT_MS
      });
    } catch (error) {
      if (!silent) {
        this.notifyRendererError(error.code || 'mic_unavailable', error.message);
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

  _assertEnabled() {
    if (!this.runtimeConfig.enabled) {
      throw new Error('Gemini Live is disabled.');
    }
  }

  _assertConnected() {
    if (!this._session || !this._state.live.connected) {
      throw new Error('Gemini Live session is not running');
    }
  }
}

module.exports = {
  ElectronLiveService,
  cloneState
};
