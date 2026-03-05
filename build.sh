#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Radiology Copilot — Build Script
# Compiles the app to a single macOS executable using PyInstaller.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

APP_NAME="radiology-copilot"
ENTRY="main.py"

echo "==> Installing dependencies..."
pip install -r requirements.txt
pip install pyinstaller

echo "==> Building ${APP_NAME}..."
pyinstaller \
    --onefile \
    --windowed \
    --name "${APP_NAME}" \
    --add-data "config.py:." \
    --hidden-import "pynput.keyboard._darwin" \
    --hidden-import "pynput.mouse._darwin" \
    --hidden-import "uvicorn.logging" \
    --hidden-import "uvicorn.protocols.http" \
    --hidden-import "uvicorn.protocols.http.auto" \
    --hidden-import "uvicorn.protocols.websockets" \
    --hidden-import "uvicorn.protocols.websockets.auto" \
    --hidden-import "uvicorn.lifespan" \
    --hidden-import "uvicorn.lifespan.on" \
    "${ENTRY}"

echo ""
echo "==> Build complete!"
echo "    Executable: dist/${APP_NAME}"
echo ""
echo "==> macOS Notes:"
echo "    - Screen Recording permission required (System Settings → Privacy & Security)"
echo "    - Accessibility permission required for global hotkeys"
echo "    - For distribution, code sign with: codesign --force --deep --sign - dist/${APP_NAME}"
echo "    - To bypass Gatekeeper during dev: xattr -rd com.apple.quarantine dist/${APP_NAME}"
