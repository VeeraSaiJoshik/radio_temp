// Browser-only renderer script loaded as a plain <script> tag.
// Global type declarations are in renderer.d.ts.
// window.LiveMediaUtils is exposed by electron/live/media_utils.ts.

// --------------------------------------------------------------------------
// Local helpers
// --------------------------------------------------------------------------

interface AppMediaError extends Error {
  code?: string;
}

function createMediaError(code: string, message: string): AppMediaError {
  const error: AppMediaError = new Error(message);
  error.code = code;
  return error;
}

function blobToBytes(blob: Blob): Promise<Uint8Array> {
  return blob.arrayBuffer().then((buffer) => new Uint8Array(buffer));
}

function canvasToJpegBytes(canvas: HTMLCanvasElement, quality: number): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      async (blob) => {
        if (!blob) {
          reject(createMediaError('capture_failed', 'Canvas capture returned no image data.'));
          return;
        }
        try {
          resolve(await blobToBytes(blob));
        } catch (error) {
          reject(error);
        }
      },
      'image/jpeg',
      quality
    );
  });
}

// --------------------------------------------------------------------------
// AudioOutputPlayer
// --------------------------------------------------------------------------

class AudioOutputPlayer {
  audioContext: AudioContext;
  nextStartTime: number;
  activeSources: Set<AudioBufferSourceNode>;

  constructor(audioContext: AudioContext) {
    this.audioContext = audioContext;
    this.nextStartTime = 0;
    this.activeSources = new Set();
  }

  async playBase64Pcm(base64: string): Promise<void> {
    const bytes = window.LiveMediaUtils.base64ToBytes(base64);
    if (!bytes.length) {
      return;
    }

    await this.audioContext.resume();

    const samples = window.LiveMediaUtils.pcm16ToFloat32(bytes);
    const buffer = this.audioContext.createBuffer(1, samples.length, 24000);
    buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0);

    const source = this.audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(this.audioContext.destination);

    const startTime = Math.max(this.audioContext.currentTime, this.nextStartTime);
    this.nextStartTime = startTime + buffer.duration;
    this.activeSources.add(source);

    source.onended = () => {
      this.activeSources.delete(source);
    };
    source.start(startTime);
  }

  clear(): void {
    for (const source of this.activeSources) {
      try {
        source.stop();
      } catch (error) {
        // Ignore sources that have already completed.
      }
    }
    this.activeSources.clear();
    this.nextStartTime = this.audioContext.currentTime;
  }
}

// --------------------------------------------------------------------------
// LiveMediaController
// --------------------------------------------------------------------------

interface LiveMediaControllerConstructorOptions {
  desktop: CopilotDesktopApi;
  previewFps?: number;
  previewMaxWidth?: number;
  previewJpegQuality?: number;
  screenshotJpegQuality?: number;
  micSampleRate?: number;
}

class LiveMediaController {
  desktop: CopilotDesktopApi;
  previewFps: number;
  previewMaxWidth: number;
  previewJpegQuality: number;
  screenshotJpegQuality: number;
  micSampleRate: number;

  private _audioContext: AudioContext | null;
  private _audioOutput: AudioOutputPlayer | null;
  private _displayStream: MediaStream | null;
  private _displayVideo: HTMLVideoElement | null;
  private _displayCanvas: HTMLCanvasElement;
  private _previewTimer: number | null;
  private _previewInFlight: boolean;
  private _connected: boolean;

  private _micStream: MediaStream | null;
  private _micSource: MediaStreamAudioSourceNode | null;
  private _micProcessor: ScriptProcessorNode | null;
  private _micSink: GainNode | null;

  constructor(options: LiveMediaControllerConstructorOptions) {
    const settings = options || ({} as LiveMediaControllerConstructorOptions);
    this.desktop = settings.desktop;
    this.previewFps = settings.previewFps ?? 2;
    this.previewMaxWidth = settings.previewMaxWidth ?? 960;
    this.previewJpegQuality = settings.previewJpegQuality ?? 45;
    this.screenshotJpegQuality = settings.screenshotJpegQuality ?? 0.85;
    this.micSampleRate = settings.micSampleRate ?? 16000;

    this._audioContext = null;
    this._audioOutput = null;
    this._displayStream = null;
    this._displayVideo = null;
    this._displayCanvas = document.createElement('canvas');
    this._previewTimer = null;
    this._previewInFlight = false;
    this._connected = false;

    this._micStream = null;
    this._micSource = null;
    this._micProcessor = null;
    this._micSink = null;
  }

  async bootstrap(): Promise<void> {
    await this.desktop.markLiveRendererReady();
  }

  async handleCommand(command: RendererLiveCommand): Promise<void> {
    try {
      let payload: unknown = { ok: true };
      switch (command.type) {
        case 'live.start_mic':
          payload = await this.startMic();
          break;
        case 'live.stop_mic':
          payload = await this.stopMic();
          break;
        case 'live.capture_screenshot':
          payload = await this.captureFullScreenshot();
          break;
        case 'live.refresh_preview':
          await this.capturePreviewFrame();
          break;
        default:
          throw createMediaError('unsupported_command', `Unsupported live command: ${command.type}`);
      }
      this.desktop.respondLiveCommand(command.requestId, payload, null);
    } catch (error) {
      const err = error as AppMediaError;
      this.desktop.respondLiveCommand(command.requestId, null, {
        code: err.code || 'renderer_error',
        message: err.message || String(err)
      });
    }
  }

  async handleLiveEvent(event: RendererAppEvent): Promise<void> {
    switch (event.type) {
      case 'live.connection':
        this._connected = Boolean(event.connected);
        if (this._connected) {
          void this.startPreviewLoop();
        } else {
          this.stopPreviewLoop();
          await this.stopMic({ suppressStreamEnd: true });
        }
        break;
      case 'live.audio':
        await this._ensureAudioOutput();
        await this._audioOutput!.playBase64Pcm(event.data || '');
        break;
      case 'live.audio_clear':
        if (this._audioOutput) {
          this._audioOutput.clear();
        }
        break;
      default:
        break;
    }
  }

  async startPreviewLoop(): Promise<void> {
    if (this._previewTimer || !this._connected) {
      return;
    }

    try {
      await this.ensureDisplayStream();
    } catch (error) {
      const err = error as AppMediaError;
      this._reportError(err.code || 'screen_unavailable', err.message);
      return;
    }

    const intervalMs = Math.max(250, Math.round(1000 / this.previewFps));
    this._previewTimer = window.setInterval(() => {
      void this.capturePreviewFrame();
    }, intervalMs);
    await this.capturePreviewFrame();
  }

  stopPreviewLoop(): void {
    if (this._previewTimer) {
      window.clearInterval(this._previewTimer);
      this._previewTimer = null;
    }
  }

  async capturePreviewFrame(): Promise<void> {
    if (!this._connected || this._previewInFlight) {
      return;
    }

    this._previewInFlight = true;
    try {
      const bytes = await this._captureFrame({
        maxWidth: this.previewMaxWidth,
        jpegQuality: this.previewJpegQuality / 100
      });
      const imageHash = await window.LiveMediaUtils.hashBytes(bytes);
      this.desktop.sendLivePreviewFrame({
        bytes,
        mimeType: 'image/jpeg',
        imageHash
      });
    } catch (error) {
      const err = error as AppMediaError;
      this._reportError(err.code || 'capture_failed', err.message);
    } finally {
      this._previewInFlight = false;
    }
  }

  async captureFullScreenshot(): Promise<{ image_b64: string; image_hash: string; mime_type: string }> {
    const bytes = await this._captureFrame({
      maxWidth: 0,
      jpegQuality: this.screenshotJpegQuality
    });
    const imageHash = await window.LiveMediaUtils.hashBytes(bytes);
    return {
      image_b64: window.LiveMediaUtils.bytesToBase64(bytes),
      image_hash: imageHash,
      mime_type: 'image/jpeg'
    };
  }

  async startMic(): Promise<{ ok: boolean }> {
    if (this._micStream) {
      this.desktop.setLiveMicState(true);
      return { ok: true };
    }

    const access = await this.desktop.prepareLiveMediaAccess('microphone');
    if (access && access.status === 'restricted') {
      throw createMediaError('mic_unavailable', access.message);
    }

    const audioContext = await this._ensureAudioContext();
    await audioContext.resume();

    try {
      this._micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        },
        video: false
      });
    } catch (error) {
      const err = error as AppMediaError & { name?: string };
      let message = `Microphone capture failed: ${err.message || err}`;
      if (err && err.name === 'NotAllowedError') {
        try {
          const accessStatus = await this.desktop.getLiveMediaAccessStatus('microphone');
          if (accessStatus && accessStatus.message) {
            message = accessStatus.message;
            if (accessStatus.status === 'denied' || accessStatus.status === 'restricted') {
              await this._openMediaSettings('microphone');
              message += ' System Settings was opened for you.';
            }
          } else {
            message = 'Microphone access was denied.';
          }
        } catch (statusError) {
          message = 'Microphone access was denied.';
        }
      }
      throw createMediaError('mic_unavailable', message);
    }

    this._micStream.getAudioTracks().forEach((track) => {
      track.onended = () => {
        void this.stopMic({ suppressStreamEnd: true });
      };
    });

    this._micSource = audioContext.createMediaStreamSource(this._micStream);
    this._micProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    this._micSink = audioContext.createGain();
    this._micSink.gain.value = 0;

    this._micProcessor.onaudioprocess = (event: AudioProcessingEvent) => {
      const input = event.inputBuffer.getChannelData(0);
      const pcm16 = window.LiveMediaUtils.downsampleFloat32ToPcm16(
        input,
        audioContext.sampleRate,
        this.micSampleRate
      );
      const bytes = window.LiveMediaUtils.pcm16ToBytes(pcm16);
      if (bytes.byteLength) {
        this.desktop.sendLiveAudioChunk({ bytes });
      }
    };

    this._micSource.connect(this._micProcessor);
    this._micProcessor.connect(this._micSink);
    this._micSink.connect(audioContext.destination);
    this.desktop.setLiveMicState(true);
    return { ok: true };
  }

  async stopMic(options: { suppressStreamEnd?: boolean } = {}): Promise<{ ok: boolean }> {
    const suppressStreamEnd = Boolean(options.suppressStreamEnd);

    if (this._micProcessor) {
      this._micProcessor.disconnect();
      this._micProcessor.onaudioprocess = null;
      this._micProcessor = null;
    }
    if (this._micSource) {
      this._micSource.disconnect();
      this._micSource = null;
    }
    if (this._micSink) {
      this._micSink.disconnect();
      this._micSink = null;
    }
    if (this._micStream) {
      this._micStream.getTracks().forEach((track) => track.stop());
      this._micStream = null;
    }

    if (!suppressStreamEnd) {
      this.desktop.sendLiveAudioStreamEnd();
    }
    this.desktop.setLiveMicState(false);
    return { ok: true };
  }

  async ensureDisplayStream(): Promise<MediaStream> {
    if (
      this._displayStream &&
      this._displayStream.getVideoTracks().some((track) => track.readyState === 'live')
    ) {
      return this._displayStream;
    }

    const access = await this.desktop.prepareLiveMediaAccess('screen');
    if (access && access.status === 'restricted') {
      throw createMediaError('screen_unavailable', access.message);
    }

    try {
      this._displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: {
          frameRate: {
            ideal: Math.max(1, this.previewFps)
          }
        },
        audio: false
      });
    } catch (error) {
      const err = error as AppMediaError & { name?: string };
      let message = `Display capture failed: ${err.message || err}`;
      if (err && err.name === 'NotAllowedError') {
        try {
          const accessStatus = await this.desktop.getLiveMediaAccessStatus('screen');
          if (accessStatus && accessStatus.message) {
            message = accessStatus.message;
            if (accessStatus.status === 'denied' || accessStatus.status === 'restricted') {
              await this._openMediaSettings('screen');
              message += ' System Settings was opened for you.';
            }
          } else {
            message = 'Screen recording access was denied.';
          }
        } catch (statusError) {
          message = 'Screen recording access was denied.';
        }
        throw createMediaError('screen_unavailable', message);
      }
      throw createMediaError('screen_capture_failed', message);
    }

    const videoTrack = this._displayStream.getVideoTracks()[0];
    if (videoTrack) {
      videoTrack.onended = () => {
        this._displayStream = null;
        this.stopPreviewLoop();
        this._reportError(
          'screen_unavailable',
          'Display capture stopped. Restart screen sharing to restore live visual context.'
        );
      };
    }

    this._displayVideo = document.createElement('video');
    this._displayVideo.muted = true;
    this._displayVideo.playsInline = true;
    this._displayVideo.srcObject = this._displayStream;
    await this._displayVideo.play();
    return this._displayStream;
  }

  private async _captureFrame(options: { maxWidth: number; jpegQuality: number }): Promise<Uint8Array> {
    await this.ensureDisplayStream();
    if (!this._displayVideo) {
      throw createMediaError('capture_failed', 'Display capture is not ready.');
    }

    if (this._displayVideo.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      await new Promise<void>((resolve) => {
        this._displayVideo!.onloadeddata = () => resolve();
      });
    }

    const sourceWidth = this._displayVideo.videoWidth;
    const sourceHeight = this._displayVideo.videoHeight;
    if (!sourceWidth || !sourceHeight) {
      throw createMediaError('capture_failed', 'Display capture returned an empty frame.');
    }

    let targetWidth = sourceWidth;
    let targetHeight = sourceHeight;
    if (options.maxWidth && sourceWidth > options.maxWidth) {
      const scale = options.maxWidth / sourceWidth;
      targetWidth = Math.max(1, Math.round(sourceWidth * scale));
      targetHeight = Math.max(1, Math.round(sourceHeight * scale));
    }

    this._displayCanvas.width = targetWidth;
    this._displayCanvas.height = targetHeight;
    const context = this._displayCanvas.getContext('2d', { alpha: false });
    context!.drawImage(this._displayVideo, 0, 0, targetWidth, targetHeight);
    return canvasToJpegBytes(this._displayCanvas, options.jpegQuality);
  }

  private async _ensureAudioContext(): Promise<AudioContext> {
    if (!this._audioContext) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const AudioContextClass: typeof AudioContext = (window as any).AudioContext || (window as any).webkitAudioContext;
      this._audioContext = new AudioContextClass();
    }
    return this._audioContext;
  }

  private async _ensureAudioOutput(): Promise<AudioOutputPlayer> {
    const audioContext = await this._ensureAudioContext();
    if (!this._audioOutput) {
      this._audioOutput = new AudioOutputPlayer(audioContext);
    }
    return this._audioOutput;
  }

  private async _openMediaSettings(mediaType: string): Promise<void> {
    try {
      await this.desktop.openLiveMediaSettings(mediaType);
    } catch (error) {
      // Opening System Settings is best-effort only.
    }
  }

  _reportError(code: string, message: string): void {
    this.desktop.reportLiveMediaError(code, message);
  }
}

// Expose on window for app.ts to access via new window.LiveMediaController(...)
window.LiveMediaController = LiveMediaController;
