export class LocalWebSocketUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'LocalWebSocketUnavailable';
  }
}

export class AckTimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AckTimeoutError';
  }
}

export interface ScreenshotCapturePayload {
  type: string;
  request_id: string;
  session_id?: string;
  timestamp?: string;
  reason?: string;
  mime_type?: string;
  image_b64?: string;
  image_hash?: string;
  source?: string;
}

export interface ScreenshotAckPayload {
  type: string;
  request_id: string;
  status: string;
  error: string | null;
}

interface PendingAck {
  resolve: (value: ScreenshotAckPayload) => void;
  reject: (reason: Error) => void;
  timeoutId: ReturnType<typeof setTimeout>;
}

export interface LiveScreenshotTransportOptions {
  url: string;
  ackTimeoutMs?: number;
  retryDelayMs?: number;
  onStatus?: (message: string) => void;
  webSocketFactory?: (url: string) => WebSocket;
}

export class LiveScreenshotTransport {
  url: string;
  ackTimeoutMs: number;
  retryDelayMs: number;
  onStatus: (message: string) => void;
  webSocketFactory: (url: string) => WebSocket;

  private _socket: WebSocket | null;
  private _connected: boolean;
  private _closing: boolean;
  private _connectLoopPromise: Promise<void> | null;
  private _pendingAcks: Map<string, PendingAck>;
  private _closeCurrentSocket: (() => void) | null;

  constructor(options: LiveScreenshotTransportOptions) {
    const settings = options || ({} as LiveScreenshotTransportOptions);
    this.url = settings.url;
    this.ackTimeoutMs = settings.ackTimeoutMs ?? 5000;
    this.retryDelayMs = settings.retryDelayMs ?? 1500;
    this.onStatus = settings.onStatus || function noop() {};
    this.webSocketFactory =
      settings.webSocketFactory || ((url: string) => new WebSocket(url));

    this._socket = null;
    this._connected = false;
    this._closing = false;
    this._connectLoopPromise = null;
    this._pendingAcks = new Map();
    this._closeCurrentSocket = null;
  }

  async start(): Promise<void> {
    if (!this.url || this._connectLoopPromise) {
      return;
    }

    this._closing = false;
    this._connectLoopPromise = this._connectionLoop();
    await Promise.resolve();
  }

  async close(): Promise<void> {
    this._closing = true;
    this._connected = false;

    if (this._socket) {
      try {
        this._socket.close();
      } catch (error) {
        // Ignore close failures during shutdown.
      }
    }

    if (this._connectLoopPromise) {
      await this._connectLoopPromise.catch(function ignore() {});
      this._connectLoopPromise = null;
    }

    this._failPending(new LocalWebSocketUnavailable('Screenshot websocket closed'));
  }

  async sendCapture(message: ScreenshotCapturePayload): Promise<ScreenshotAckPayload> {
    const requestId = String(message && message.request_id ? message.request_id : '').trim();
    if (!requestId) {
      throw new Error('Screenshot websocket payload must include request_id');
    }

    if (!this._connectLoopPromise) {
      await this.start();
    }
    if (!this._connected || !this._socket) {
      throw new LocalWebSocketUnavailable(
        `Screenshot websocket is not connected: ${this.url}`
      );
    }

    let timeoutId: ReturnType<typeof setTimeout>;
    const ackPromise = new Promise<ScreenshotAckPayload>((resolve, reject) => {
      timeoutId = setTimeout(() => {
        this._pendingAcks.delete(requestId);
        reject(new AckTimeoutError(`Timed out waiting for screenshot ack: ${requestId}`));
      }, this.ackTimeoutMs);

      this._pendingAcks.set(requestId, {
        resolve,
        reject,
        timeoutId: timeoutId!
      });
    });

    try {
      this._socket.send(JSON.stringify(message));
      return await ackPromise;
    } catch (error) {
      this._clearPending(requestId);
      throw error;
    }
  }

  private async _connectionLoop(): Promise<void> {
    while (!this._closing) {
      try {
        await this._openSocket();
      } catch (error) {
        if (this._closing) {
          break;
        }
        this._connected = false;
        this._socket = null;
        const err = error as Error;
        this._failPending(new LocalWebSocketUnavailable(String(err && err.message ? err.message : err)));
        this.onStatus(`[live] Screenshot websocket unavailable: ${err.message || err}`);
        await new Promise<void>((resolve) => setTimeout(resolve, this.retryDelayMs));
      }
    }
  }

  private _openSocket(): Promise<void> {
    return new Promise<Promise<void>>((resolve, reject) => {
      const socket = this.webSocketFactory(this.url);
      let settled = false;

      const cleanup = () => {
        socket.removeEventListener('open', handleOpen);
        socket.removeEventListener('error', handleError);
        socket.removeEventListener('close', handleClose);
        socket.removeEventListener('message', handleMessage);
      };

      const fail = (error: unknown) => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        reject(error instanceof Error ? error : new Error(String(error)));
      };

      const handleOpen = () => {
        this._socket = socket;
        this._connected = true;
        this.onStatus(`[live] Screenshot websocket connected: ${this.url}`);
        if (settled) {
          return;
        }
        settled = true;
        resolve(
          new Promise<void>((innerResolve) => {
            this._closeCurrentSocket = innerResolve;
          })
        );
      };

      const handleError = (event: Event) => {
        const ev = event as ErrorEvent & { error?: { message?: string }; message?: string };
        const message =
          ev && ev.error && ev.error.message
            ? ev.error.message
            : ev && ev.message
              ? ev.message
              : 'Screenshot websocket error';
        fail(new Error(message));
      };

      const handleClose = () => {
        const closeResolver = this._closeCurrentSocket;
        this._closeCurrentSocket = null;
        this._connected = false;
        this._socket = null;
        this._failPending(
          new LocalWebSocketUnavailable(`Screenshot websocket is not connected: ${this.url}`)
        );
        cleanup();
        if (!settled) {
          settled = true;
          reject(new Error('Screenshot websocket closed before opening'));
          return;
        }
        if (closeResolver) {
          closeResolver();
        }
      };

      const handleMessage = (event: MessageEvent) => {
        try {
          const payload = JSON.parse(event.data as string) as ScreenshotAckPayload;
          if (payload.type !== 'screenshot.ack' || !payload.request_id) {
            return;
          }

          const pending = this._pendingAcks.get(payload.request_id);
          if (!pending) {
            return;
          }

          clearTimeout(pending.timeoutId);
          this._pendingAcks.delete(payload.request_id);
          pending.resolve(payload);
        } catch (error) {
          // Ignore malformed websocket payloads from the local backend.
        }
      };

      socket.addEventListener('open', handleOpen);
      socket.addEventListener('error', handleError);
      socket.addEventListener('close', handleClose);
      socket.addEventListener('message', handleMessage as EventListener);
    }).then((closePromise) => closePromise);
  }

  private _clearPending(requestId: string): void {
    const pending = this._pendingAcks.get(requestId);
    if (!pending) {
      return;
    }
    clearTimeout(pending.timeoutId);
    this._pendingAcks.delete(requestId);
  }

  private _failPending(error: Error): void {
    for (const [requestId, pending] of this._pendingAcks.entries()) {
      clearTimeout(pending.timeoutId);
      pending.reject(error);
      this._pendingAcks.delete(requestId);
    }
  }
}
