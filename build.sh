#!/usr/bin/env bash

set -euo pipefail

echo "==> Installing Python dependencies..."
python3 -m pip install -r requirements.txt

echo "==> Installing Electron dependencies..."
npm install

echo "==> Validating desktop sources..."
npm run lint:desktop
python3 -m compileall main.py desktop_bridge live

echo ""
echo "Electron development environment is ready."
echo "Run \`npm start\` to launch the desktop shell."
echo "Run \`python3 main.py --diff\` for the daily disagreement report."
