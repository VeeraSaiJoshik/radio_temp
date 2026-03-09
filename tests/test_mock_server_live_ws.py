import unittest

from fastapi.testclient import TestClient

from backend.mock_server import app


class MockServerLiveWebSocketTests(unittest.TestCase):
    def test_websocket_acknowledges_screenshot_capture(self):
        client = TestClient(app)

        with client.websocket_connect("/live/screenshot") as websocket:
            websocket.send_json(
                {
                    "type": "screenshot.capture",
                    "request_id": "request-123",
                    "session_id": "session-123",
                    "timestamp": "2026-03-07T00:00:00Z",
                    "reason": "The page changed",
                    "mime_type": "image/jpeg",
                    "image_b64": "aGVsbG8=",
                    "image_hash": "hash-123",
                    "source": "gemini_live_tool",
                }
            )
            ack = websocket.receive_json()

        self.assertEqual(ack["type"], "screenshot.ack")
        self.assertEqual(ack["request_id"], "request-123")
        self.assertEqual(ack["status"], "ok")
        self.assertIsNone(ack["error"])
