const test = require('node:test');
const assert = require('node:assert/strict');

const { ElectronLiveService } = require('./service');

function createRuntimeConfig() {
  return {
    enabled: true,
    apiKey: 'test-key',
    initialMessage: 'Gemini Live connecting...',
    model: 'gemini-test-live',
    screenshotWsUrl: 'ws://localhost/live/screenshot',
    screenshotAckTimeoutMs: 50,
    screenshotRetryDelayMs: 5,
    previewFps: 2,
    previewMaxWidth: 960,
    previewJpegQuality: 45,
    voiceName: 'Kore',
    micMode: 'continuous',
    micSampleRate: 16000,
    micChunkMs: 20,
    contextTriggerTokens: 24576,
    contextTargetTokens: 16384,
    systemPrompt: 'system',
    bootstrapPrompt: 'bootstrap',
    functionResponseScheduling: 'WHEN_IDLE',
    transparentSessionResumption: false
  };
}

function createService(overrides = {}) {
  const events = [];
  const rendererCalls = [];
  const fakeSession = {
    clientContents: [],
    toolResponses: [],
    realtimeInputs: [],
    closeCount: 0,
    sendClientContent(payload) {
      this.clientContents.push(payload);
    },
    sendToolResponse(payload) {
      this.toolResponses.push(payload);
    },
    sendRealtimeInput(payload) {
      this.realtimeInputs.push(payload);
    },
    close() {
      this.closeCount += 1;
    }
  };

  const service = new ElectronLiveService({
    runtimeConfig: createRuntimeConfig(),
    eventSink: (event) => events.push(event),
    rendererRequest: async (command) => {
      rendererCalls.push(command);
      if (command.type === 'live.capture_screenshot') {
        return {
          image_b64: 'aGVsbG8=',
          image_hash: 'hash-123',
          mime_type: 'image/jpeg'
        };
      }
      return { ok: true };
    },
    screenshotTransport: {
      start: async () => {},
      close: async () => {},
      sendCapture: async () => ({
        type: 'screenshot.ack',
        request_id: 'ignored',
        status: 'ok',
        error: null
      })
    },
    ...overrides
  });

  service._session = fakeSession;
  service._state.live.connected = true;
  service._state.session_id = 'session-1';

  return {
    events,
    fakeSession,
    rendererCalls,
    service
  };
}

test('sendText appends user transcript, sends client content, and records replayable state', async () => {
  const { service, fakeSession, rendererCalls } = createService();

  await service.sendText('  take screenshot  ');

  assert.equal(fakeSession.clientContents.length, 1);
  assert.match(
    fakeSession.clientContents[0].turns.parts[0].text,
    /No preview frame or screenshot has been received in this session yet/u
  );
  assert.equal(service.getState().transcript_entries.at(-1).text, 'take screenshot');
  assert.equal(service._recoverableMessages.length, 0);
  assert.equal(rendererCalls.at(-1).type, 'live.refresh_preview');
});

test('sendText uses plain user text after a preview frame has been delivered', async () => {
  const { service, fakeSession } = createService();

  await service.submitPreviewFrame({
    bytes: new Uint8Array([1, 2, 3]),
    mimeType: 'image/jpeg'
  });
  await service.sendText('what is on screen');

  assert.equal(fakeSession.clientContents.at(-1).turns.parts[0].text, 'what is on screen');
});

test('sendText warns the model when screen capture is unavailable', async () => {
  const { service, fakeSession } = createService();

  service.notifyRendererError(
    'screen_unavailable',
    'Screen recording access is denied.'
  );
  await service.sendText('what am I looking at');

  assert.match(
    fakeSession.clientContents.at(-1).turns.parts[0].text,
    /Live display capture is currently unavailable/u
  );
});

test('startMicCapture emits a permission warning when renderer mic startup fails', async () => {
  const micError = Object.assign(new Error('Microphone access is denied.'), {
    code: 'mic_unavailable'
  });
  const { service, events } = createService({
    rendererRequest: async () => {
      throw micError;
    }
  });

  await assert.rejects(service.startMicCapture(), /Microphone access is denied/u);

  assert.equal(service.getState().live.mic_active, false);
  assert.equal(service.getState().live.phase, 'Text only');
  assert.ok(
    events.some(
      (event) =>
        event.type === 'permission.warning' &&
        event.message === 'Microphone access is denied.'
    )
  );
});

test('call_hotkey tool calls the configured hotkey trigger and returns success', async () => {
  const hotkeyReasons = [];
  const { service, fakeSession } = createService({
    hotkeyTrigger: async () => {
      hotkeyReasons.push('triggered');
    }
  });

  await service._handleToolCalls([
    {
      id: 'call-1',
      name: 'call_hotkey',
      args: { reason: 'Open the overlay and rerun analysis' }
    }
  ]);

  assert.equal(hotkeyReasons.length, 1);
  assert.equal(fakeSession.toolResponses.length, 1);
  assert.deepEqual(fakeSession.toolResponses[0].functionResponses[0].response, {
    status: 'ok',
    reason: 'Open the overlay and rerun analysis',
    error: null
  });
});

test('tool call cancellation drops a late screenshot tool response', async () => {
  const { service, fakeSession } = createService({
    screenshotTransport: {
      start: async () => {},
      close: async () => {},
      sendCapture: async () => {
        await new Promise((resolve) => setTimeout(resolve, 5));
        return {
          type: 'screenshot.ack',
          request_id: 'ignored',
          status: 'ok',
          error: null
        };
      }
    }
  });

  const toolPromise = service._handleToolCalls([
    {
      id: 'call-1',
      name: 'take_screenshot',
      args: { reason: 'Screen changed' }
    }
  ]);
  service._handleToolCallCancellation(['call-1']);
  await toolPromise;

  assert.equal(fakeSession.toolResponses.length, 0);
});

test('session resumption updates trim consumed replayable messages and preserve the latest handle', async () => {
  const { service, fakeSession } = createService({
    runtimeConfig: {
      ...createRuntimeConfig(),
      transparentSessionResumption: true
    }
  });
  service._recordRecoverableMessage('client', {
    turns: { role: 'user', parts: [{ text: 'first' }] },
    turnComplete: true
  });
  service._recordRecoverableMessage('tool', {
    functionResponses: [{ id: 'call-1', name: 'take_screenshot', response: { status: 'ok' } }]
  });

  service._updateSessionResumption({
    newHandle: 'resume-2',
    lastConsumedClientMessageIndex: '0'
  });

  assert.equal(service._sessionResumptionHandle, 'resume-2');
  assert.equal(service._recoverableMessages.length, 1);
  await service._replayRecoverableMessages();
  assert.equal(fakeSession.toolResponses.length, 1);
});
