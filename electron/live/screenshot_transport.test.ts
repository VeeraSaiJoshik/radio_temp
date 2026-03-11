import test from 'node:test';
import assert from 'node:assert/strict';

import {
  AckTimeoutError,
  LiveScreenshotTransport
} from './screenshot_transport';

type EventType = 'open' | 'error' | 'close' | 'message';

class FakeWebSocket {
  listeners: Map<EventType, Array<(payload: unknown) => void>>;
  sent: unknown[];

  constructor() {
    this.listeners = new Map();
    this.sent = [];
  }

  addEventListener(type: EventType, callback: (payload: unknown) => void): void {
    const callbacks = this.listeners.get(type) || [];
    callbacks.push(callback);
    this.listeners.set(type, callbacks);
  }

  removeEventListener(type: EventType, callback: (payload: unknown) => void): void {
    const callbacks = this.listeners.get(type) || [];
    this.listeners.set(
      type,
      callbacks.filter((entry) => entry !== callback)
    );
  }

  send(message: string): void {
    this.sent.push(JSON.parse(message));
  }

  close(): void {
    this.emit('close', {});
  }

  emit(type: EventType, payload: unknown): void {
    const callbacks = this.listeners.get(type) || [];
    for (const callback of callbacks) {
      callback(payload);
    }
  }
}

test('sendCapture resolves when the backend sends a matching ack', async () => {
  const socket = new FakeWebSocket();
  const transport = new LiveScreenshotTransport({
    url: 'ws://localhost/live/screenshot',
    ackTimeoutMs: 50,
    retryDelayMs: 5,
    webSocketFactory: () => socket as unknown as WebSocket
  });

  await transport.start();
  socket.emit('open', {});

  const ackPromise = transport.sendCapture({
    type: 'screenshot.capture',
    request_id: 'request-1'
  });
  assert.equal((socket.sent[0] as { request_id: string }).request_id, 'request-1');

  socket.emit('message', {
    data: JSON.stringify({
      type: 'screenshot.ack',
      request_id: 'request-1',
      status: 'ok',
      error: null
    })
  });

  const ack = await ackPromise;
  assert.equal(ack.status, 'ok');
  await transport.close();
});

test('sendCapture rejects with AckTimeoutError when no ack arrives', async () => {
  const socket = new FakeWebSocket();
  const transport = new LiveScreenshotTransport({
    url: 'ws://localhost/live/screenshot',
    ackTimeoutMs: 10,
    retryDelayMs: 5,
    webSocketFactory: () => socket as unknown as WebSocket
  });

  await transport.start();
  socket.emit('open', {});

  await assert.rejects(
    transport.sendCapture({
      type: 'screenshot.capture',
      request_id: 'request-2'
    }),
    AckTimeoutError
  );
  await transport.close();
});
