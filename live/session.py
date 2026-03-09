"""Gemini Live session orchestration for continuous preview and multimodal turns."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, Iterable, Literal

import config
from live.audio import AudioPlayer
from live.prompts import BOOTSTRAP_PROMPT, SYSTEM_PROMPT
from live.sdk import make_blob, make_function_response, require_google_genai
from live.screen_feed import ScreenFeedPublisher
from live.tool_bridge import ScreenshotToolBridge, TAKE_SCREENSHOT_DECLARATION

MAX_RECONNECTS = 50
RECONNECT_DELAY = 1.5
MIC_MODE_PUSH_TO_TALK = "push_to_talk"
MIC_MODE_CONTINUOUS = "continuous"


@dataclass(frozen=True)
class _RealtimeEvent:
    kind: Literal["activity_start", "audio", "activity_end", "audio_stream_end"]
    payload: bytes | None = None


class _ReconnectRequested(RuntimeError):
    """Signal that the current socket should be torn down and reconnected."""


class LiveSessionManager:
    """Runs one Gemini Live session plus the preview stream and screenshot tool bridge."""

    def __init__(
        self,
        *,
        session_id: str,
        screenshot_transport,
        model: str = config.GEMINI_LIVE_MODEL,
        api_key: str = config.GEMINI_API_KEY,
        status_sink=None,
        assistant_sink=None,
        user_transcript_sink=None,
        connection_sink=None,
        system_instruction: str = SYSTEM_PROMPT,
        bootstrap_prompt: str = BOOTSTRAP_PROMPT,
        screen_feed_publisher: ScreenFeedPublisher | None = None,
        screenshot_tool_bridge: ScreenshotToolBridge | None = None,
        audio_player: AudioPlayer | None = None,
        mic_mode: str = config.LIVE_MIC_MODE,
    ):
        self.session_id = session_id
        self.screenshot_transport = screenshot_transport
        self.model = model
        self.api_key = api_key
        self.status_sink = status_sink or print
        self.assistant_sink = assistant_sink or (lambda text: self.status_sink(f"[gemini] {text}"))
        self.user_transcript_sink = user_transcript_sink or (lambda text, is_final: None)
        self.connection_sink = connection_sink or (lambda connected, message: None)
        self.system_instruction = system_instruction
        self.bootstrap_prompt = bootstrap_prompt
        self.screen_feed_publisher = screen_feed_publisher
        self.screenshot_tool_bridge = screenshot_tool_bridge or ScreenshotToolBridge(
            session_id=session_id,
            transport=screenshot_transport,
        )
        self.audio_player = audio_player
        self.mic_mode = self._normalize_mic_mode(mic_mode)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._outbound_queue: asyncio.Queue[str] | None = None
        self._realtime_queue: asyncio.Queue[_RealtimeEvent] | None = None
        self._assistant_output_buffer = ""
        self._assistant_model_buffer = ""
        self._turn_assistant_emissions: set[str] = set()
        self._active_screen_feed_publisher: ScreenFeedPublisher | None = None

    async def run(self):
        """Open Gemini Live and keep it running, reconnecting when the socket drops."""
        if not self.api_key:
            raise RuntimeError("Set GEMINI_API_KEY before starting the Gemini Live scaffold.")

        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._outbound_queue = asyncio.Queue()
        self._realtime_queue = asyncio.Queue()

        genai, _ = require_google_genai()
        await self.screenshot_transport.start()
        client = genai.Client(api_key=self.api_key)

        try:
            if self.audio_player:
                self.audio_player.start()

            reconnects = 0
            while not self._stop_event.is_set() and reconnects < MAX_RECONNECTS:
                if reconnects > 0:
                    message = f"[live] Reconnecting ({reconnects}/{MAX_RECONNECTS})..."
                    print(message)
                    self.status_sink(message)
                    await asyncio.sleep(RECONNECT_DELAY)

                fatal_error = await self._run_session(client)
                if fatal_error:
                    raise fatal_error
                reconnects += 1

            if reconnects >= MAX_RECONNECTS:
                print(f"[live] Max reconnects ({MAX_RECONNECTS}) reached, stopping.")

        finally:
            if self.audio_player:
                self.audio_player.stop()
            await self.screenshot_transport.close()
            self.connection_sink(False, "Gemini Live disconnected")
            self._outbound_queue = None
            self._realtime_queue = None
            self._stop_event = None
            self._loop = None

    async def _run_session(self, client) -> Exception | None:
        """Run one Gemini Live socket. Returns None to reconnect on recoverable drops."""
        try:
            async with client.aio.live.connect(
                model=self.model,
                config=self._build_live_config(),
            ) as session:
                self.status_sink(f"[live] Connected to Gemini Live model: {self.model}")
                self.connection_sink(True, f"Gemini Live connected: {self.model}")

                publisher = self.screen_feed_publisher or ScreenFeedPublisher(session)
                self._active_screen_feed_publisher = publisher

                receiver_task = asyncio.create_task(
                    self._receive_loop(session),
                    name="live-receive-loop",
                )
                publisher_task = asyncio.create_task(
                    publisher.run(self._stop_event),
                    name="live-screen-feed",
                )
                outbound_task = asyncio.create_task(
                    self._outbound_loop(session),
                    name="live-outbound-loop",
                )
                realtime_task = asyncio.create_task(
                    self._realtime_outbound_loop(session),
                    name="live-realtime-outbound-loop",
                )
                stop_task = asyncio.create_task(
                    self._stop_event.wait(),
                    name="live-stop-waiter",
                )

                done, pending = await asyncio.wait(
                    {receiver_task, publisher_task, outbound_task, realtime_task, stop_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()
                for task in pending:
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

                if self._stop_event.is_set():
                    self._active_screen_feed_publisher = None
                    return None

                for task in done:
                    if task is stop_task or task.cancelled():
                        continue
                    exc = task.exception()
                    if exc is None:
                        continue
                    if isinstance(exc, _ReconnectRequested):
                        self._active_screen_feed_publisher = None
                        self.status_sink(f"[live] {exc}")
                        self.connection_sink(False, str(exc))
                        return None
                    self._active_screen_feed_publisher = None
                    return exc

                self._active_screen_feed_publisher = None
                return None

        except Exception as exc:
            self._active_screen_feed_publisher = None
            print(f"[live] Session exception: {exc}")
            self.status_sink(f"[live] Session exception: {exc}")
            self.connection_sink(False, str(exc))
            return None

    def submit_user_message(self, text: str):
        """Queue a typed user message to the active Live session from any thread."""
        cleaned = text.strip()
        if not cleaned:
            return

        if self._loop is None or self._outbound_queue is None:
            raise RuntimeError("Gemini Live session is not running")

        if self.audio_player is not None:
            self.audio_player.clear()
        self.request_screen_refresh()
        self._loop.call_soon_threadsafe(self._outbound_queue.put_nowait, cleaned)

    def begin_user_activity(self):
        """Interrupt the current response and mark that the user started speaking."""
        if self.audio_player is not None:
            self.audio_player.clear()
        self.request_screen_refresh()
        self._enqueue_realtime_event(_RealtimeEvent("activity_start"))

    def end_user_activity(self):
        """Mark that the user's locally detected speech has ended."""
        self._enqueue_realtime_event(_RealtimeEvent("activity_end"))

    def start_audio_turn(self):
        """Mark the start of an explicit push-to-talk utterance."""
        if self.mic_mode != MIC_MODE_PUSH_TO_TALK:
            return
        self.begin_user_activity()

    def push_audio_chunk(self, pcm_bytes: bytes):
        """Queue one microphone PCM chunk for the active Live session."""
        if not pcm_bytes:
            return
        self._enqueue_realtime_event(_RealtimeEvent("audio", bytes(pcm_bytes)))

    def finish_audio_turn(self):
        """Signal that the current utterance or listening stream has ended."""
        event_kind = "activity_end" if self.mic_mode == MIC_MODE_PUSH_TO_TALK else "audio_stream_end"
        self._enqueue_realtime_event(_RealtimeEvent(event_kind))

    def request_stop(self):
        """Signal the live session to stop."""
        if self._loop is None or self._stop_event is None:
            return
        self._loop.call_soon_threadsafe(self._stop_event.set)

    def request_screen_refresh(self):
        """Ask the preview publisher to send a fresh frame immediately."""
        if self._loop is None or self._active_screen_feed_publisher is None:
            return
        self._loop.call_soon_threadsafe(self._active_screen_feed_publisher.request_refresh)

    def _enqueue_realtime_event(self, event: _RealtimeEvent):
        if self._loop is None or self._realtime_queue is None:
            raise RuntimeError("Gemini Live session is not running")
        self._loop.call_soon_threadsafe(self._realtime_queue.put_nowait, event)

    def _build_live_config(self) -> Any:
        _, types = require_google_genai()
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=self._build_realtime_input_config(types),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=config.LIVE_VOICE_NAME,
                    )
                )
            ),
            system_instruction=self._compose_system_instruction(),
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=TAKE_SCREENSHOT_DECLARATION["name"],
                            description=TAKE_SCREENSHOT_DECLARATION["description"],
                            parameters_json_schema=TAKE_SCREENSHOT_DECLARATION["parameters"],
                        )
                    ]
                )
            ],
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=config.LIVE_CONTEXT_TRIGGER_TOKENS,
                sliding_window=types.SlidingWindow(
                    target_tokens=config.LIVE_CONTEXT_TARGET_TOKENS,
                ),
            ),
            session_resumption=types.SessionResumptionConfig(),
        )

    def _build_realtime_input_config(self, types):
        if self.mic_mode == MIC_MODE_CONTINUOUS:
            auto_detection = types.AutomaticActivityDetection(
                disabled=False,
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=100,
                silence_duration_ms=700,
            )
        else:
            auto_detection = types.AutomaticActivityDetection(disabled=True)

        return types.RealtimeInputConfig(
            automatic_activity_detection=auto_detection,
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        )

    def _compose_system_instruction(self) -> str:
        if not self.bootstrap_prompt:
            return self.system_instruction
        return f"{self.system_instruction}\n\nSession bootstrap:\n{self.bootstrap_prompt}"

    async def _receive_loop(self, session):
        while self._stop_event is not None and not self._stop_event.is_set():
            self._begin_turn()
            saw_message = False
            try:
                async for message in session.receive():
                    saw_message = True
                    await self._handle_session_message(session, message)
            except Exception as exc:
                print(f"[live] receive loop exception: {exc}")
                raise

            if not saw_message:
                raise _ReconnectRequested("Gemini Live receive loop ended unexpectedly")

            self._finish_turn()

    async def _handle_session_message(self, session, message):
        go_away = self._get_attr(message, "go_away", "goAway")
        if go_away:
            reason = self._get_attr(go_away, "reason") or "Gemini Live requested shutdown"
            raise _ReconnectRequested(f"Gemini Live session ended: {reason}")

        server_content = self._get_attr(message, "server_content", "serverContent")
        if server_content:
            self._handle_server_content(server_content)

        tool_call = self._get_attr(message, "tool_call", "toolCall")
        function_calls = self._get_attr(tool_call, "function_calls", "functionCalls") if tool_call else None
        if function_calls:
            await self._handle_tool_calls(session, function_calls)

    def _handle_server_content(self, server_content):
        if self._get_attr(server_content, "interrupted"):
            if self.audio_player is not None:
                self.audio_player.clear()
            if self.mic_mode == MIC_MODE_CONTINUOUS:
                self.status_sink("[state] Listening continuously")
            else:
                self.status_sink("[state] Listening")

        model_turn = self._get_attr(server_content, "model_turn", "modelTurn")
        parts = self._get_attr(model_turn, "parts") if model_turn else None
        text_parts: list[str] = []

        for part in parts or []:
            inline_data = self._get_attr(part, "inline_data", "inlineData")
            if inline_data and self.audio_player is not None:
                mime_type = self._get_attr(inline_data, "mime_type", "mimeType") or ""
                data = self._get_attr(inline_data, "data")
                if data and str(mime_type).startswith("audio/"):
                    self.audio_player.play(data)

            text = self._get_attr(part, "text")
            if text:
                text_parts.append(str(text))

        if text_parts:
            self._assistant_model_buffer = "\n".join(text_parts).strip()

        input_transcription = self._get_attr(server_content, "input_transcription", "inputTranscription")
        if input_transcription:
            input_text = self._get_attr(input_transcription, "text")
            is_finished = bool(self._get_attr(input_transcription, "finished"))
            if input_text:
                print(f"[live] User said: {input_text}")
                self.user_transcript_sink(str(input_text).strip(), is_finished)

        output_transcription = self._get_attr(server_content, "output_transcription", "outputTranscription")
        if output_transcription:
            output_text = self._get_attr(output_transcription, "text")
            finished = bool(self._get_attr(output_transcription, "finished"))
            if output_text:
                self._assistant_output_buffer = str(output_text).strip()
                if finished:
                    self._emit_assistant_text(self._assistant_output_buffer)

        if self._get_attr(server_content, "turn_complete", "turnComplete") or self._get_attr(
            server_content,
            "generation_complete",
            "generationComplete",
        ):
            self.status_sink("[state] Waiting for input")
            fallback_text = self._assistant_output_buffer or self._assistant_model_buffer
            if fallback_text:
                self._emit_assistant_text(fallback_text)
        elif self._get_attr(server_content, "waiting_for_input", "waitingForInput"):
            self.status_sink("[state] Waiting for input")

    async def _outbound_loop(self, session):
        while self._stop_event is not None and not self._stop_event.is_set():
            if self._outbound_queue is None:
                return

            try:
                text = await asyncio.wait_for(self._outbound_queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue

            await session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]},
                turn_complete=True,
            )

    async def _realtime_outbound_loop(self, session):
        chunks_sent = 0
        while self._stop_event is not None and not self._stop_event.is_set():
            if self._realtime_queue is None:
                return

            try:
                event = await asyncio.wait_for(self._realtime_queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue

            if event.kind == "activity_start":
                _, types = require_google_genai()
                await session.send_realtime_input(activity_start=types.ActivityStart())
                continue

            if event.kind == "activity_end":
                _, types = require_google_genai()
                await session.send_realtime_input(activity_end=types.ActivityEnd())
                continue

            if event.kind == "audio_stream_end":
                await session.send_realtime_input(audio_stream_end=True)
                continue

            if event.kind != "audio" or event.payload is None:
                continue

            await session.send_realtime_input(
                audio=make_blob(data=event.payload, mime_type="audio/pcm;rate=16000")
            )
            chunks_sent += 1
            if chunks_sent == 10:
                print(f"[live] Mic audio flowing ({len(event.payload)} bytes/chunk)")
            elif chunks_sent % 500 == 0:
                print(f"[live] Mic audio: {chunks_sent} chunks sent")

    async def _handle_tool_calls(self, session, function_calls: Iterable[Any]):
        responses = []

        for function_call in function_calls:
            function_name = self._get_attr(function_call, "name")
            function_call_id = self._get_attr(function_call, "id")
            args = self._get_attr(function_call, "args") or {}

            if function_name != TAKE_SCREENSHOT_DECLARATION["name"]:
                result = {
                    "status": "error",
                    "request_id": None,
                    "image_hash": None,
                    "sent_at": None,
                    "backend_status": "unsupported_tool",
                    "error": f"Unsupported tool: {function_name}",
                }
            else:
                result = await self.screenshot_tool_bridge.handle_tool_call(args)

            responses.append(
                make_function_response(
                    function_call_id=function_call_id,
                    name=function_name,
                    response=result,
                )
            )

        await session.send_tool_response(function_responses=responses)

    def _begin_turn(self):
        self._assistant_output_buffer = ""
        self._assistant_model_buffer = ""
        self._turn_assistant_emissions.clear()

    def _finish_turn(self):
        fallback_text = self._assistant_output_buffer or self._assistant_model_buffer
        if fallback_text:
            self._emit_assistant_text(fallback_text)

    def _emit_assistant_text(self, text: str):
        cleaned = text.strip()
        if not cleaned or cleaned in self._turn_assistant_emissions:
            return
        self._turn_assistant_emissions.add(cleaned)
        self.assistant_sink(cleaned)

    @staticmethod
    def _normalize_mic_mode(value: str) -> str:
        cleaned = (value or "").strip().lower()
        if cleaned in {MIC_MODE_PUSH_TO_TALK, MIC_MODE_CONTINUOUS}:
            return cleaned
        return MIC_MODE_PUSH_TO_TALK

    @staticmethod
    def _get_attr(obj: Any, *names: str):
        if obj is None:
            return None
        if isinstance(obj, dict):
            for name in names:
                if name in obj:
                    return obj.get(name)
            return None
        for name in names:
            value = getattr(obj, name, None)
            if value is not None:
                return value
        return None
