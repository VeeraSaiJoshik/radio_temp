"""Audio capture and playback for Gemini Live."""

from __future__ import annotations

import queue
import threading
from typing import Callable

import config

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised when dependency is absent locally
    np = None

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - exercised when dependency is absent locally
    sd = None

_SENTINEL = object()


def _default_input_samplerate() -> int | None:
    if sd is None:
        return None
    try:
        device = sd.query_devices(kind="input")
    except Exception:
        return None

    samplerate = device.get("default_samplerate")
    if not samplerate:
        return None
    return int(round(float(samplerate)))


def _resample_pcm16_mono(pcm_bytes: bytes, *, src_rate: int, dst_rate: int) -> bytes:
    if src_rate <= 0 or dst_rate <= 0:
        raise ValueError("Sample rates must be positive")
    if src_rate == dst_rate or not pcm_bytes:
        return pcm_bytes
    if np is None:
        raise RuntimeError("Resampling microphone audio requires `numpy`.")

    source = np.frombuffer(pcm_bytes, dtype=np.int16)
    if source.size == 0:
        return b""

    target_size = max(1, int(round(source.size * (dst_rate / src_rate))))
    source_positions = np.arange(source.size, dtype=np.float32)
    target_positions = np.linspace(0, source.size - 1, num=target_size, dtype=np.float32)
    resampled = np.interp(target_positions, source_positions, source.astype(np.float32))
    clipped = np.clip(np.rint(resampled), -32768, 32767).astype(np.int16)
    return clipped.tobytes()


class AudioPlayer:
    """Plays 24 kHz mono int16 PCM audio from Gemini Live responses.

    All blocking sounddevice writes happen on a dedicated thread so
    the caller (typically an async event loop) is never blocked.
    """

    def __init__(
        self,
        *,
        samplerate: int = 24_000,
        channels: int = 1,
        dtype: str = "int16",
        blocksize: int = 2400,
        status_sink=None,
    ):
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.blocksize = blocksize
        self.status_sink = status_sink or (lambda message: None)
        self._stream = None
        self._queue: queue.Queue[bytes | object] = queue.Queue()
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self):
        """Open the output audio stream and start the writer thread."""
        if self.active:
            return
        if sd is None:
            raise RuntimeError(
                "Audio playback requires `sounddevice`. Install the project requirements first."
            )
        self._stream = sd.OutputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.blocksize,
        )
        self._stream.start()
        self._thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._thread.start()

    def play(self, pcm_bytes: bytes):
        """Queue raw PCM bytes for playback (non-blocking)."""
        if self._stream is None:
            return
        self._queue.put_nowait(pcm_bytes)

    def stop(self):
        """Stop the writer thread and close the output stream."""
        if self._stream is None:
            return
        self._queue.put_nowait(_SENTINEL)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._stream.stop()
        self._stream.close()
        self._stream = None

    def clear(self):
        """Drop queued audio when the model is interrupted by a new turn."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is _SENTINEL:
                self._queue.put_nowait(_SENTINEL)
                return

    def _writer_loop(self):
        """Drain the queue and write to sounddevice (runs on its own thread)."""
        while True:
            try:
                chunk = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._stream is None:
                    return
                continue
            if chunk is _SENTINEL:
                return
            if np is None or self._stream is None:
                continue
            try:
                audio = np.frombuffer(chunk, dtype=np.int16)
                self._stream.write(audio)
            except Exception:
                pass


class PushToTalkMicrophone:
    """Captures 16 kHz mono PCM audio while the mic button is held."""

    def __init__(
        self,
        *,
        samplerate: int = config.LIVE_MIC_SAMPLE_RATE,
        capture_samplerate: int = config.LIVE_MIC_CAPTURE_SAMPLE_RATE,
        channels: int = 1,
        dtype: str = "int16",
        blocksize: int | None = None,
        chunk_ms: int = config.LIVE_MIC_CHUNK_MS,
        status_sink=None,
    ):
        self.samplerate = samplerate
        self.capture_samplerate = capture_samplerate
        self.channels = channels
        self.dtype = dtype
        self.blocksize = blocksize
        self.chunk_ms = chunk_ms
        self.status_sink = status_sink or (lambda message: None)
        self._stream = None
        self._chunk_sink: Callable[[bytes], None] | None = None
        self._stream_samplerate = self.samplerate

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self, chunk_sink: Callable[[bytes], None]):
        """Begin microphone capture."""
        if self.active:
            return
        if sd is None or np is None:
            raise RuntimeError(
                "Microphone capture requires `sounddevice` and `numpy`. Install the project requirements first."
            )

        self._chunk_sink = chunk_sink
        requested_samplerate = self.capture_samplerate or _default_input_samplerate() or self.samplerate
        self._open_stream(requested_samplerate)
        self.status_sink(
            f"[mic] Capturing at {self._stream_samplerate} Hz -> {self.samplerate} Hz"
        )

    def stop(self):
        """Stop microphone capture and release the input stream."""
        if self._stream is None:
            return

        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._chunk_sink = None

    def _callback(self, indata, frames, time_info, status):
        if status:
            self.status_sink(f"[mic] {status}")

        if self._chunk_sink is None:
            return

        pcm_bytes = np.asarray(indata).copy().astype(np.int16, copy=False).tobytes()
        if self._stream_samplerate != self.samplerate:
            pcm_bytes = _resample_pcm16_mono(
                pcm_bytes,
                src_rate=self._stream_samplerate,
                dst_rate=self.samplerate,
            )
        if pcm_bytes:
            self._chunk_sink(pcm_bytes)

    def _open_stream(self, samplerate: int):
        blocksize = self.blocksize or max(1, int(samplerate * (self.chunk_ms / 1000.0)))
        try:
            stream = sd.InputStream(
                samplerate=samplerate,
                channels=self.channels,
                dtype=self.dtype,
                blocksize=blocksize,
                latency="low",
                callback=self._callback,
            )
            stream.start()
        except Exception:
            if samplerate == self.samplerate:
                raise
            fallback_blocksize = self.blocksize or max(1, int(self.samplerate * (self.chunk_ms / 1000.0)))
            stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                dtype=self.dtype,
                blocksize=fallback_blocksize,
                latency="low",
                callback=self._callback,
            )
            stream.start()
            self._stream_samplerate = self.samplerate
            self._stream = stream
            return

        self._stream_samplerate = samplerate
        self._stream = stream
