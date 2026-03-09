import unittest
from unittest import mock

from PIL import Image

from capture import screenshot


class CaptureScreenTests(unittest.TestCase):
    @mock.patch("capture.screenshot._grab_monitor_image")
    def test_preview_capture_is_smaller_than_full_capture(self, mock_grab_monitor_image):
        mock_grab_monitor_image.return_value = Image.effect_noise((2000, 1200), 100).convert("RGB")

        preview_bytes, preview_hash = screenshot.capture_screen_preview(
            monitor_index=1,
            max_width=400,
            jpeg_quality=40,
        )
        full_bytes, full_hash = screenshot.capture_screen_full(
            monitor_index=1,
            jpeg_quality=85,
        )

        self.assertLess(len(preview_bytes), len(full_bytes))
        self.assertTrue(preview_hash)
        self.assertTrue(full_hash)
