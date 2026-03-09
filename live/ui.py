"""Legacy compatibility entrypoint for the old standalone live UI."""

from __future__ import annotations

import subprocess
from pathlib import Path


def launch_live_window(*, start_server: bool):
    """Launch the Electron desktop instead of the retired PyQt window."""
    _ = start_server
    repo_root = Path(__file__).resolve().parents[1]
    subprocess.run(["npm", "start"], cwd=repo_root, check=True)
