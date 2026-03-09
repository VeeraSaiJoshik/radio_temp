#!/usr/bin/env python3
"""Start the local mock backend that exposes the Gemini Live screenshot websocket."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.mock_server import run_mock_server


if __name__ == "__main__":
    run_mock_server()
