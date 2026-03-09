import unittest

from live.vad import VoiceActivitySegmenter, extract_primary_utterance


def _chunk(level: int, samples: int = 320) -> bytes:
    return int(level).to_bytes(2, byteorder="little", signed=True) * samples


class LiveVadTests(unittest.TestCase):
    def test_segmenter_emits_utterance_after_silence(self):
        segmenter = VoiceActivitySegmenter(
            sample_rate=16_000,
            chunk_ms=20,
            min_rms=120,
            start_multiplier=2.0,
            end_multiplier=1.4,
            start_chunks=2,
            preroll_ms=40,
            min_speech_ms=80,
            silence_ms=120,
            max_speech_ms=2_000,
        )

        events = []
        for _ in range(3):
            events.extend(segmenter.feed_chunk(_chunk(10)))
        for _ in range(6):
            events.extend(segmenter.feed_chunk(_chunk(700)))
        for _ in range(8):
            events.extend(segmenter.feed_chunk(_chunk(10)))

        self.assertEqual(events[0].kind, "speech_start")
        self.assertEqual(events[-1].kind, "utterance")
        self.assertTrue(events[-1].audio)

    def test_segmenter_ignores_noise_floor_only_audio(self):
        segmenter = VoiceActivitySegmenter(
            sample_rate=16_000,
            chunk_ms=20,
            min_rms=150,
            start_multiplier=2.2,
            end_multiplier=1.6,
            start_chunks=3,
            preroll_ms=60,
            min_speech_ms=120,
            silence_ms=160,
            max_speech_ms=2_000,
        )

        events = []
        for _ in range(20):
            events.extend(segmenter.feed_chunk(_chunk(30)))

        self.assertEqual(events, [])
        self.assertEqual(segmenter.flush(), b"")

    def test_extract_primary_utterance_returns_longest_segment(self):
        audio = b"".join(
            [
                _chunk(10),
                _chunk(10),
                _chunk(650),
                _chunk(700),
                _chunk(680),
                _chunk(690),
                _chunk(660),
                _chunk(640),
                _chunk(10),
                _chunk(10),
                _chunk(10),
                _chunk(720),
                _chunk(740),
                _chunk(710),
                _chunk(700),
                _chunk(730),
                _chunk(690),
                _chunk(710),
                _chunk(10),
                _chunk(10),
                _chunk(10),
            ]
        )

        utterance = extract_primary_utterance(audio, sample_rate=16_000, chunk_ms=20)

        self.assertGreater(len(utterance), len(_chunk(650)) * 6)
