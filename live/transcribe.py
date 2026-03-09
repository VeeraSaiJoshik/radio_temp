"""Dedicated speech-to-text helper for reliable spoken-command transcription."""

from __future__ import annotations

import io
import re
import wave

import config
from live.sdk import require_google_genai


TRANSCRIBE_PROMPT = (
    "Transcribe the user's speech exactly as spoken. "
    "Return only the transcript text. "
    "Preserve the original language and script exactly. "
    "Do not translate, transliterate, summarize, explain, or identify the language. "
    "If the audio is only noise or unintelligible, return an empty string."
)


class SpeechTranscriber:
    """Runs short-utterance transcription with a dedicated backend and Gemini fallback."""

    def __init__(
        self,
        *,
        api_key: str = config.GEMINI_API_KEY,
        model: str = config.GEMINI_TRANSCRIBE_MODEL,
        backend: str = config.LIVE_TRANSCRIBE_BACKEND,
        language_codes: tuple[str, ...] = config.LIVE_TRANSCRIBE_LANGUAGE_CODES,
        prompt: str = TRANSCRIBE_PROMPT,
    ):
        self.api_key = api_key
        self.model = model
        self.backend = (backend or "auto").strip().lower()
        self.language_codes = tuple(code.strip() for code in language_codes if code.strip())
        self.prompt = prompt
        self._gemini_backend = _GeminiSpeechTranscriber(
            api_key=api_key,
            model=model,
            prompt=prompt,
            language_codes=self.language_codes,
        )
        self._backend_impl = self._select_backend()

    @property
    def backend_label(self) -> str:
        return self._backend_impl.label

    def transcribe_pcm(self, pcm_bytes: bytes, *, sample_rate: int, channels: int = 1) -> str:
        if not pcm_bytes.strip(b"\x00"):
            return ""
        try:
            return self._backend_impl.transcribe_pcm(
                pcm_bytes,
                sample_rate=sample_rate,
                channels=channels,
            )
        except Exception:
            if self.backend != "auto" or self._backend_impl is self._gemini_backend:
                raise
            self._backend_impl = self._gemini_backend
            return self._backend_impl.transcribe_pcm(
                pcm_bytes,
                sample_rate=sample_rate,
                channels=channels,
            )

    def _select_backend(self):
        if self.backend == "gemini":
            return self._gemini_backend
        if self.backend in {"auto", "google_cloud_speech"}:
            cloud_backend = _maybe_google_cloud_speech_backend(language_codes=self.language_codes)
            if cloud_backend is not None:
                return cloud_backend
            if self.backend == "google_cloud_speech":
                raise RuntimeError(
                    "google-cloud-speech is unavailable. Install it and configure Google Cloud credentials, or use LIVE_TRANSCRIBE_BACKEND=gemini."
                )
        return self._gemini_backend


class _GeminiSpeechTranscriber:
    label = "gemini"

    def __init__(self, *, api_key: str, model: str, prompt: str, language_codes: tuple[str, ...]):
        self.api_key = api_key
        self.model = model
        self.prompt = prompt
        self.language_codes = language_codes

    def transcribe_pcm(self, pcm_bytes: bytes, *, sample_rate: int, channels: int = 1) -> str:
        genai, types = require_google_genai()
        client = genai.Client(api_key=self.api_key)
        prompt = self.prompt
        if self.language_codes:
            prompt = (
                f"{prompt} Likely languages include: {', '.join(self.language_codes)}. "
                "Still preserve whichever language was actually spoken."
            )

        response = client.models.generate_content(
            model=self.model,
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=_pcm_to_wav_bytes(
                        pcm_bytes,
                        sample_rate=sample_rate,
                        channels=channels,
                    ),
                    mime_type="audio/wav",
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="text/plain",
            ),
        )
        return _clean_transcript(getattr(response, "text", None) or "")


class _GoogleCloudSpeechTranscriber:
    label = "google_cloud_speech"

    def __init__(self, *, language_codes: tuple[str, ...]):
        from google.cloud import speech

        self._speech = speech
        self.language_codes = language_codes or ("en-US",)
        self.model = config.GOOGLE_CLOUD_SPEECH_MODEL
        self._client = speech.SpeechClient()

    def transcribe_pcm(self, pcm_bytes: bytes, *, sample_rate: int, channels: int = 1) -> str:
        speech = self._speech
        recognition_config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            audio_channel_count=channels,
            language_code=self.language_codes[0],
            alternative_language_codes=list(self.language_codes[1:]),
            model=self.model,
        )
        response = self._client.recognize(
            config=recognition_config,
            audio=speech.RecognitionAudio(content=pcm_bytes),
        )

        transcripts = []
        for result in getattr(response, "results", []) or []:
            alternatives = getattr(result, "alternatives", []) or []
            if alternatives:
                transcripts.append(alternatives[0].transcript)
        return _clean_transcript(" ".join(transcripts))


def _maybe_google_cloud_speech_backend(*, language_codes: tuple[str, ...]):
    try:
        from google.cloud import speech  # noqa: F401
    except Exception:
        return None

    try:
        return _GoogleCloudSpeechTranscriber(language_codes=language_codes)
    except Exception:
        return None


def _clean_transcript(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"^```(?:text)?\s*|\s*```$", "", cleaned).strip()
    cleaned = cleaned.strip().strip("\"'").strip()
    lowered = cleaned.lower()
    if lowered in {"[noise]", "(noise)", "[silence]", "(silence)", "noise", "silence", "none", "null"}:
        return ""
    return cleaned


def _pcm_to_wav_bytes(pcm_bytes: bytes, *, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()
