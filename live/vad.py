"""Lightweight local voice activity detection for spoken command segmentation."""

from __future__ import annotations

import audioop
from collections import deque
from dataclasses import dataclass
from typing import Literal

import config


@dataclass(frozen=True)
class VoiceActivityEvent:
    kind: Literal["speech_start", "utterance"]
    audio: bytes | None = None


class VoiceActivitySegmenter:
    """Segments short utterances from a mono PCM stream using adaptive RMS thresholds."""

    def __init__(
        self,
        *,
        sample_rate: int = config.LIVE_MIC_SAMPLE_RATE,
        chunk_ms: int = config.LIVE_MIC_CHUNK_MS,
        min_rms: int = config.LIVE_VAD_MIN_RMS,
        start_multiplier: float = config.LIVE_VAD_START_MULTIPLIER,
        end_multiplier: float = config.LIVE_VAD_END_MULTIPLIER,
        start_chunks: int = config.LIVE_VAD_START_CHUNKS,
        preroll_ms: int = config.LIVE_VAD_PREROLL_MS,
        min_speech_ms: int = config.LIVE_VAD_MIN_SPEECH_MS,
        silence_ms: int = config.LIVE_VAD_SILENCE_MS,
        max_speech_ms: int = config.LIVE_VAD_MAX_SPEECH_MS,
    ):
        if sample_rate <= 0 or chunk_ms <= 0:
            raise ValueError("sample_rate and chunk_ms must be positive")

        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms
        self.min_rms = max(1, min_rms)
        self.start_multiplier = max(1.0, start_multiplier)
        self.end_multiplier = max(1.0, end_multiplier)
        self.start_chunks = max(1, start_chunks)
        self.preroll_chunks = max(1, preroll_ms // chunk_ms)
        self.min_speech_chunks = max(1, min_speech_ms // chunk_ms)
        self.silence_chunks = max(1, silence_ms // chunk_ms)
        self.max_speech_chunks = max(self.min_speech_chunks, max_speech_ms // chunk_ms)
        self._noise_floor = float(self.min_rms)
        self._preroll: deque[bytes] = deque(maxlen=self.preroll_chunks)
        self._speech_run = 0
        self._silence_run = 0
        self._voiced_chunks = 0
        self._in_speech = False
        self._utterance_chunks: list[bytes] = []

    def feed_chunk(self, pcm_bytes: bytes) -> list[VoiceActivityEvent]:
        if not pcm_bytes:
            return []

        rms = audioop.rms(pcm_bytes, 2)
        start_threshold = max(self.min_rms, int(self._noise_floor * self.start_multiplier))
        end_threshold = max(self.min_rms, int(self._noise_floor * self.end_multiplier))
        events: list[VoiceActivityEvent] = []

        if not self._in_speech:
            if rms < start_threshold:
                self._update_noise_floor(rms)
            self._preroll.append(pcm_bytes)
            if rms >= start_threshold:
                self._speech_run += 1
            else:
                self._speech_run = 0
            if self._speech_run >= self.start_chunks:
                self._in_speech = True
                self._silence_run = 0
                self._utterance_chunks = list(self._preroll)
                self._voiced_chunks = self._speech_run
                self._preroll.clear()
                events.append(VoiceActivityEvent("speech_start"))
            return events

        self._utterance_chunks.append(pcm_bytes)
        if rms >= end_threshold:
            self._silence_run = 0
            self._voiced_chunks += 1
        else:
            self._silence_run += 1

        if len(self._utterance_chunks) >= self.max_speech_chunks or self._silence_run >= self.silence_chunks:
            utterance = self._finalize_utterance()
            if utterance:
                events.append(VoiceActivityEvent("utterance", utterance))

        return events

    def flush(self) -> bytes:
        if not self._in_speech:
            self._speech_run = 0
            self._preroll.clear()
            return b""
        return self._finalize_utterance()

    def _finalize_utterance(self) -> bytes:
        trailing_silence = max(0, self._silence_run - 1)
        trimmed_chunks = self._utterance_chunks[:-trailing_silence] if trailing_silence else self._utterance_chunks
        utterance = b"".join(trimmed_chunks)
        voiced_chunks = self._voiced_chunks
        self._reset_speech_state()
        if voiced_chunks < self.min_speech_chunks:
            return b""
        return utterance

    def _reset_speech_state(self):
        self._in_speech = False
        self._speech_run = 0
        self._silence_run = 0
        self._voiced_chunks = 0
        self._utterance_chunks = []

    def _update_noise_floor(self, rms: int):
        capped_rms = min(rms, self.min_rms * 6)
        self._noise_floor = max(
            float(self.min_rms),
            (self._noise_floor * 0.92) + (float(capped_rms) * 0.08),
        )


def extract_primary_utterance(
    pcm_bytes: bytes,
    *,
    sample_rate: int = config.LIVE_MIC_SAMPLE_RATE,
    chunk_ms: int = config.LIVE_MIC_CHUNK_MS,
) -> bytes:
    """Trim a held push-to-talk clip down to the strongest detected utterance."""

    if not pcm_bytes:
        return b""

    bytes_per_chunk = max(2, int(sample_rate * (chunk_ms / 1000.0)) * 2)
    segmenter = VoiceActivitySegmenter(sample_rate=sample_rate, chunk_ms=chunk_ms)
    utterances: list[bytes] = []

    for start in range(0, len(pcm_bytes), bytes_per_chunk):
        chunk = pcm_bytes[start:start + bytes_per_chunk]
        if not chunk:
            continue
        for event in segmenter.feed_chunk(chunk):
            if event.kind == "utterance" and event.audio:
                utterances.append(event.audio)

    flushed = segmenter.flush()
    if flushed:
        utterances.append(flushed)
    if not utterances:
        return b""
    return max(utterances, key=len)
