class LocalWebSocketUnavailable extends Error {}

class AckTimeoutError extends Error {}

class LiveScreenshotTransport {
  constructor(options) {
    const settings = options || {};
    this.url = settings.url;
    this.ackTimeoutMs = settings.ackTimeoutMs ?? 5000;
    this.retryDelayMs = settings.retryDelayMs ?? 1500;
    this.onStatus = settings.onStatus || function noop() {};
    this.webSocketFactory =
      settings.webSocketFactory || ((url) => new WebSocket(url));

    this._socket = null;
    this._connected = false;
    this._closing = false;
    this._connectLoopPromise = null;
    this._pendingAcks = new Map();
  }

  async start() {
    if (!this.url || this._connectLoopPromise) {
      return;
    }

    this._closing = false;
    this._connectLoopPromise = this._connectionLoop();
    await Promise.resolve();
  }

  async close() {
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

  async sendCapture(message) {
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

    let timeoutId;
    const ackPromise = new Promise((resolve, reject) => {
      timeoutId = setTimeout(() => {
        this._pendingAcks.delete(requestId);
        reject(new AckTimeoutError(`Timed out waiting for screenshot ack: ${requestId}`));
      }, this.ackTimeoutMs);

      this._pendingAcks.set(requestId, {
        resolve,
        reject,
        timeoutId
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

  async _connectionLoop() {
    while (!this._closing) {
      try {
        await this._openSocket();
      } catch (error) {
        if (this._closing) {
          break;
        }
        this._connected = false;
        this._socket = null;
        this._failPending(new LocalWebSocketUnavailable(String(error && error.message ? error.message : error)));
        this.onStatus(`[live] Screenshot websocket unavailable: ${error.message || error}`);
        await new Promise((resolve) => setTimeout(resolve, this.retryDelayMs));
      }
    }
  }

  _openSocket() {
    return new Promise((resolve, reject) => {
      const socket = this.webSocketFactory(this.url);
      let settled = false;

      const cleanup = () => {
        socket.removeEventListener('open', handleOpen);
        socket.removeEventListener('error', handleError);
        socket.removeEventListener('close', handleClose);
        socket.removeEventListener('message', handleMessage);
      };

      const fail = (error) => {
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
          new Promise((innerResolve) => {
            this._closeCurrentSocket = innerResolve;
          })
        );
      };

      const handleError = (event) => {
        const message =
          event && event.error && event.error.message
            ? event.error.message
            : event && event.message
              ? event.message
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

      const handleMessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
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
      socket.addEventListener('message', handleMessage);
    }).then((closePromise) => closePromise);
  }

  _clearPending(requestId) {
    const pending = this._pendingAcks.get(requestId);
    if (!pending) {
      return;
    }
    clearTimeout(pending.timeoutId);
    this._pendingAcks.delete(requestId);
  }

  _failPending(error) {
    for (const [requestId, pending] of this._pendingAcks.entries()) {
      clearTimeout(pending.timeoutId);
      pending.reject(error);
      this._pendingAcks.delete(requestId);
    }
  }
}

module.exports = {
  AckTimeoutError,
  LiveScreenshotTransport,
  LocalWebSocketUnavailable
};
