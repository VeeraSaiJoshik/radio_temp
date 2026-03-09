"""Radiology Copilot CLI entrypoint for the Electron migration."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import config
from desktop_bridge.server import run_bridge_server
from storage.db import print_diff


def _launch_electron(*, demo_mode: bool) -> int:
    repo_root = Path(__file__).resolve().parent
    electron_package = repo_root / "node_modules" / "electron"
    if not electron_package.exists():
        print("Electron dependencies are not installed yet.")
        print("Run `npm install` once, then launch the desktop app with `npm start`.")
        print("Use `python main.py --bridge` to run the Python bridge only.")
        return 1

    command = ["npm", "run", "start:demo" if demo_mode else "start"]
    completed = subprocess.run(command, cwd=repo_root)
    return completed.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Radiology Copilot")
    parser.add_argument("--diff", action="store_true", help="Print today's disagreement diff report")
    parser.add_argument("--bridge", action="store_true", help="Run the local Electron bridge server only")
    parser.add_argument("--no-server", action="store_true", help="Don't start the mock backend server")
    parser.add_argument("--demo", action="store_true", help="Launch the demo workflow")
    parser.add_argument(
        "--bridge-host",
        default=config.DESKTOP_BRIDGE_HOST,
        help="Bridge host to bind when running --bridge",
    )
    parser.add_argument(
        "--bridge-port",
        type=int,
        default=config.DESKTOP_BRIDGE_PORT,
        help="Bridge port to bind when running --bridge",
    )
    args = parser.parse_args()

    if args.diff:
        print_diff()
        return

    if args.bridge:
        run_bridge_server(
            host=args.bridge_host,
            port=args.bridge_port,
            start_backend_server=not args.no_server and not args.demo,
            demo_mode=args.demo,
        )
        return

    raise SystemExit(_launch_electron(demo_mode=args.demo))


if __name__ == "__main__":
    main()
