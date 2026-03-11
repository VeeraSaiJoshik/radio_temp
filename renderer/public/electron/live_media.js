(function initLiveMedia(root) {
  const utils = root.LiveMediaUtils;

  function createMediaError(code, message) {
    const error = new Error(message);
    error.code = code;
    return error;
  }

  function blobToBytes(blob) {
    return blob.arrayBuffer().then((buffer) => new Uint8Array(buffer));
  }

  function canvasToJpegBytes(canvas, quality) {
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

  class AudioOutputPlayer {
    constructor(audioContext) {
      this.audioContext = audioContext;
      this.nextStartTime = 0;
      this.activeSources = new Set();
    }

    async playBase64Pcm(base64) {
      const bytes = utils.base64ToBytes(base64);
      if (!bytes.length) {
        return;
      }

      await this.audioContext.resume();

      const samples = utils.pcm16ToFloat32(bytes);
      const buffer = this.audioContext.createBuffer(1, samples.length, 24000);
      buffer.copyToChannel(samples, 0);

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

    clear() {
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

  class LiveMediaController {
    constructor(options) {
      const settings = options || {};
      this.desktop = settings.desktop;
      this.previewFps = settings.previewFps || 2;
      this.previewMaxWidth = settings.previewMaxWidth || 960;
      this.previewJpegQuality = settings.previewJpegQuality || 45;
      this.screenshotJpegQuality = settings.screenshotJpegQuality || 0.85;
      this.micSampleRate = settings.micSampleRate || 16000;

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

    async bootstrap() {
      await this.desktop.markLiveRendererReady();
    }

    async handleCommand(command) {
      try {
        let payload = { ok: true };
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
        this.desktop.respondLiveCommand(command.requestId, null, {
          code: error.code || 'renderer_error',
          message: error.message || String(error)
        });
      }
    }

    async handleLiveEvent(event) {
      switch (event.type) {
        case 'live.connection':
          this._connected = Boolean(event.connected);
          if (this._connected) {
            this.startPreviewLoop();
          } else {
            this.stopPreviewLoop();
            await this.stopMic({ suppressStreamEnd: true });
          }
          break;
        case 'live.audio':
          await this._ensureAudioOutput();
          await this._audioOutput.playBase64Pcm(event.data || '');
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

    async startPreviewLoop() {
      if (this._previewTimer || !this._connected) {
        return;
      }

      try {
        await this.ensureDisplayStream();
      } catch (error) {
        this._reportError(error.code || 'screen_unavailable', error.message);
        return;
      }

      const intervalMs = Math.max(250, Math.round(1000 / this.previewFps));
      this._previewTimer = window.setInterval(() => {
        void this.capturePreviewFrame();
      }, intervalMs);
      await this.capturePreviewFrame();
    }

    stopPreviewLoop() {
      if (this._previewTimer) {
        window.clearInterval(this._previewTimer);
        this._previewTimer = null;
      }
    }

    async capturePreviewFrame() {
      if (!this._connected || this._previewInFlight) {
        return;
      }

      this._previewInFlight = true;
      try {
        const bytes = await this._captureFrame({
          maxWidth: this.previewMaxWidth,
          jpegQuality: this.previewJpegQuality / 100
        });
        const imageHash = await utils.hashBytes(bytes);
        this.desktop.sendLivePreviewFrame({
          bytes,
          mimeType: 'image/jpeg',
          imageHash
        });
      } catch (error) {
        this._reportError(error.code || 'capture_failed', error.message);
      } finally {
        this._previewInFlight = false;
      }
    }

    async captureFullScreenshot() {
      const bytes = await this._captureFrame({
        maxWidth: 0,
        jpegQuality: this.screenshotJpegQuality
      });
      const imageHash = await utils.hashBytes(bytes);
      return {
        image_b64: utils.bytesToBase64(bytes),
        image_hash: imageHash,
        mime_type: 'image/jpeg'
      };
    }

    async startMic() {
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
        let message = `Microphone capture failed: ${error.message || error}`;
        if (error && error.name === 'NotAllowedError') {
          try {
            const access = await this.desktop.getLiveMediaAccessStatus('microphone');
            if (access && access.message) {
              message = access.message;
              if (access.status === 'denied' || access.status === 'restricted') {
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

      this._micProcessor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        const pcm16 = utils.downsampleFloat32ToPcm16(
          input,
          audioContext.sampleRate,
          this.micSampleRate
        );
        const bytes = utils.pcm16ToBytes(pcm16);
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

    async stopMic(options = {}) {
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

    async ensureDisplayStream() {
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
        let message = `Display capture failed: ${error.message || error}`;
        if (error && error.name === 'NotAllowedError') {
          try {
            const access = await this.desktop.getLiveMediaAccessStatus('screen');
            if (access && access.message) {
              message = access.message;
              if (access.status === 'denied' || access.status === 'restricted') {
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

    async _captureFrame(options) {
      await this.ensureDisplayStream();
      if (!this._displayVideo) {
        throw createMediaError('capture_failed', 'Display capture is not ready.');
      }

      if (this._displayVideo.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
        await new Promise((resolve) => {
          this._displayVideo.onloadeddata = () => resolve();
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
      context.drawImage(this._displayVideo, 0, 0, targetWidth, targetHeight);
      return canvasToJpegBytes(this._displayCanvas, options.jpegQuality);
    }

    async _ensureAudioContext() {
      if (!this._audioContext) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        this._audioContext = new AudioContextClass();
      }
      return this._audioContext;
    }

    async _ensureAudioOutput() {
      const audioContext = await this._ensureAudioContext();
      if (!this._audioOutput) {
        this._audioOutput = new AudioOutputPlayer(audioContext);
      }
      return this._audioOutput;
    }

    async _openMediaSettings(mediaType) {
      try {
        await this.desktop.openLiveMediaSettings(mediaType);
      } catch (error) {
        // Opening System Settings is best-effort only.
      }
    }

    _reportError(code, message) {
      this.desktop.reportLiveMediaError(code, message);
    }
  }

  root.LiveMediaController = LiveMediaController;
})(window);
