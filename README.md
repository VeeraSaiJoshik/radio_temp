# Radiology Copilot

A **Cluely-style floating overlay desktop application** for radiologists — a background AI co-pilot that watches their screen while they read scans, surfaces real-time analysis, flags potential disagreements, and logs everything for end-of-day diff review.

Built with **Electron** for the desktop shell and Gemini Live integration, plus **Python** for capture, backend orchestration, and storage on **macOS**.

---

## Quick Start (macOS)

**Copy-paste this into your terminal and you're running in 60 seconds:**

```bash
# 1. Clone the repo
git clone https://github.com/kwamebb/radiologyproject.git
cd radiologyproject

# 2. Install Python dependencies
python3 -m pip install -r requirements.txt

# 3. Install the Electron shell
npm install

# 4. Run it
npm start
```

That starts the Electron overlay and its local Python bridge. `python3 main.py` now proxies into the Electron flow when the desktop dependencies are installed.

On macOS dev runs, `npm start` launches the locally installed wrapper app `~/Applications/ReVU.app` instead of the transient stock `Electron.app`. If you need to refresh that wrapper without launching it, run `npm run prepare:dev-app`.

**Press `Cmd+Shift+R`** to capture your screen and open the overlay.

### First-time macOS permissions

You'll need to grant permissions the first time. macOS will prompt you, or you can do it manually:

1. **System Settings → Privacy & Security → Screen Recording** → add the **Electron app** you are running (local dev builds may still appear under Terminal/iTerm2)
2. **System Settings → Privacy & Security → Microphone** → add the same **Electron app** if you want Gemini Live voice capture

For the current dev wrapper, the app name is **ReVU**.

Restart the app after granting permissions.

### Using the overlay

1. Press **Cmd+Shift+R** → overlay appears, captures your screen
2. **Type your diagnosis first** (Step 1) — the AI won't show its analysis until you commit yours
3. Click **"Reveal AI Analysis"** → see what the AI thinks (Step 2)
4. **Agree** → dismiss | **Disagree** → flag it with a note → logged for end-of-day diff
5. Press **Esc** or **Cmd+Shift+R** again to close

### End-of-day diff report

```bash
python3 main.py --diff
```

Shows every disagreement between you and the AI today — like a `git diff` for diagnoses.

---

## Table of Contents

- [The Vision](#the-vision)
- [Architecture Overview](#architecture-overview)
- [How It Works](#how-it-works)
- [File Structure](#file-structure)
- [Setup & Installation](#setup--installation)
- [Running the App](#running-the-app)
- [The Overlay](#the-overlay)
- [The Diff Report](#the-diff-report)
- [JSON Schemas (MCP Integration Contract)](#json-schemas-mcp-integration-contract)
- [Swapping the Mock for Your Real MCP Server](#swapping-the-mock-for-your-real-mcp-server)
- [Configuration Reference](#configuration-reference)
- [Building to Executable](#building-to-executable)
- [macOS Permissions](#macos-permissions)
- [Full System Vision](#full-system-vision)

---

## The Vision

Radiologists spend **~85-90%** of their time on documentation, measurement, comparison, and communication — not on the actual diagnostic reasoning they trained a decade for. This copilot is designed to augment, never replace, the radiologist by:

1. **Never showing AI analysis before the radiologist diagnoses** — avoids confirmation bias
2. **Running specialist models in the background** via MCP orchestration after the read
3. **Flagging disagreements** between AI and human in a structured, reviewable format
4. **Producing an end-of-day diff** — like a GitHub PR for medical diagnoses — that gives 100% QA coverage vs the ~5% random sampling that exists today

The core philosophy: **AI doesn't diagnose. The radiologist does. AI confirms, flags, and documents.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RADIOLOGIST'S WORKSTATION                   │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │  PACS Viewer  │    │  Copilot Overlay  │    │   Hotkey / Timer │  │
│  │  (their scan) │    │ (Electron overlay)│◄───│   Cmd+Shift+R   │  │
│  └──────────────┘    └────────┬─────────┘    └──────────────────┘  │
│                               │                                     │
│                    ┌──────────▼──────────┐                         │
│                    │  Screenshot Capture  │                         │
│                    │  (mss → base64 JPEG) │                         │
│                    └──────────┬──────────┘                         │
│                               │                                     │
│              ┌────────────────▼────────────────┐                   │
│              │         Backend Client          │                   │
│              │  POST /analyze  •  POST /flag   │                   │
│              └────────────────┬────────────────┘                   │
│                               │                                     │
│              ┌────────────────▼────────────────┐                   │
│              │       SQLite Logger (local)      │                   │
│              │  Every read, action, override    │                   │
│              └─────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ HTTP (JSON)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BACKEND (MCP SERVER)                             │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   LLM Orchestrator                           │   │
│  │  • Ingests image + patient context                          │   │
│  │  • Routes to specialist sub-models in parallel              │   │
│  │  • Synthesizes results with clinical reasoning              │   │
│  └──────────┬──────────────┬──────────────┬────────────────────┘   │
│             │              │              │                         │
│    ┌────────▼───┐  ┌───────▼────┐  ┌─────▼──────┐                 │
│    │ Lung Model │  │ Neuro Model│  │ Liver Model │  ...            │
│    │ (MCP Tool) │  │ (MCP Tool) │  │ (MCP Tool)  │                 │
│    └────────────┘  └────────────┘  └─────────────┘                 │
│                                                                     │
│  On Disagreement:                                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Heavy Model Escalation                          │   │
│  │  GPT-5.2 Pro / Gemini 3 Deep Think / etc.                  │   │
│  │  • Re-evaluate independently                                │   │
│  │  • Annotate and comment on specific features                │   │
│  │  • If consistent with doctor → diff resolves silently       │   │
│  │  • If still disagrees → escalate to second radiologist      │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**This MVP implements the left side (workstation).** The backend is stubbed with a mock FastAPI server that returns realistic responses. Your MCP team builds the right side and swaps in via a single URL change.

---

## How It Works

### 1. Capture
The radiologist presses **Cmd+Shift+R** (or auto-capture fires on a timer). The app grabs a screenshot of their screen using `mss`, encodes it as a base64 JPEG, and sends it to the backend.

### 2. Analyze
The backend (mock or real MCP server) receives the image and returns:
- A **finding summary** (human-readable text)
- A **confidence level** (low / medium / high)
- **Specialist flags** (which sub-models flagged something)
- A **recommended action**

### 3. Display
The overlay appears in the bottom-right corner showing the AI's assessment. The radiologist can:
- **Dismiss** — accepts or ignores the finding (logged as "accepted")
- **Disagree / Flag** — opens a text input to type what they think instead (logged as "flagged" with their note)

### 4. Log
Every interaction is stored in a local SQLite database:
- Timestamp, session ID, image hash
- AI finding, confidence, specialist flags
- Radiologist action (accepted / flagged / pending)
- Override note (if flagged)

### 5. Diff
At end of day, run `python main.py --diff` to see a clean report of all disagreements — the medical equivalent of a `git diff`.

---

## File Structure

```
radiology-copilot/
├── main.py                   # CLI entry point — launches Electron or runs the local bridge/diff
├── config.py                 # All settings in one place (backend URL, hotkey, timing)
├── electron/
│   ├── main.js               # Electron main process, window lifecycle, global hotkey
│   ├── preload.js            # Safe renderer bridge
│   └── renderer/             # HTML/CSS/JS overlay UI
├── desktop_bridge/
│   ├── service.py            # Python app service for capture, analysis, logging, live events
│   └── server.py             # FastAPI bridge consumed by Electron
├── capture/
│   ├── __init__.py
│   └── screenshot.py         # Screen capture (mss) → base64 JPEG + hash
├── backend/
│   ├── __init__.py
│   ├── client.py             # Async HTTP client (httpx) — sends to backend
│   └── mock_server.py        # FastAPI stub with realistic rotating responses
├── storage/
│   ├── __init__.py
│   └── db.py                 # SQLite logging + CLI diff printer
├── requirements.txt          # Python dependencies for the bridge/runtime
├── package.json              # Electron desktop shell dependencies/scripts
├── build.sh                  # Installs deps and validates the migrated desktop sources
└── README.md                 # This file
```

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- macOS (primary target)

### Install

```bash
# Clone
git clone https://github.com/kwamebb/radiologyproject.git
cd radiologyproject

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Electron dependencies
npm install
```

### Grant macOS Permissions

Before running, you may need to grant permissions in **System Settings → Privacy & Security**:

1. **Screen Recording** — required for screen capture and Gemini Live preview frames
2. **Microphone** — optional, only needed for Gemini Live voice capture

Add the Electron app you launch during local development. Depending on how macOS attributes the request, Terminal/iTerm2 may still need to be allowed for local runs.

---

## Running the App

### Launch the Copilot

```bash
npm start
```

This will:
1. Start the mock FastAPI server on `http://127.0.0.1:8100`
2. Start the local Python bridge on `http://127.0.0.1:38100`
3. Launch the Electron desktop overlay
4. Register the **Cmd+Shift+R** hotkey
5. Keep the disagreement diff available via `python main.py --diff`

### Launch the Frontend Only Demo

If you just want to see the UI without macOS permissions, screen capture, or the backend:

```bash
npm run start:demo
```

This opens the overlay immediately with sample data.

### Launch Without Mock Server

If your real MCP server is running:

```bash
# Point to your server
export RADCOPILOT_BACKEND_URL="https://your-mcp-server.com"

# Launch without starting the mock
RADCOPILOT_NO_SERVER=1 npm start
```

### View Today's Diff Report

```bash
python main.py --diff
```

Output looks like:

```
============================================================
  RADIOLOGY COPILOT — DAILY DIFF REPORT
  2026-03-04
============================================================

  Total reads:    47
  Accepted:       42
  Flagged:        5
  Pending:        0

────────────────────────────────────────────────────────────
  DISAGREEMENTS (5)
────────────────────────────────────────────────────────────

  [1]  09:14:32  |  Confidence: HIGH
       AI said:      Hyperdense region in basal ganglia — consider hemorrhage
       Doctor said:  Calcification, not hemorrhage — patient has known basal ganglia calcifications
       Image hash:   a3f2b8c91d4e7f01

  [2]  11:42:18  |  Confidence: MEDIUM
       AI said:      Possible nodule in right upper lobe — recommend comparison with prior
       Doctor said:  Nipple shadow artifact
       Image hash:   7e2c9f4a1b3d8e56

  ...

────────────────────────────────────────────────────────────
  FULL LOG (47 reads)
────────────────────────────────────────────────────────────

  ✓  08:02:11  [  HIGH]  No acute findings detected
  ✓  08:15:44  [MEDIUM]  Pleural effusion present bilaterally — correlate cl...
  ✗  09:14:32  [  HIGH]  Hyperdense region in basal ganglia — consider hemor...
  ✓  09:31:07  [   LOW]  Stable 1.2cm hepatic cyst — unchanged from prior
  ...

============================================================
```

---

## The Overlay

The overlay is a dark, semi-transparent floating window that appears in the bottom-right corner of the screen.

### Features
- **Always on top** — stays visible over PACS viewer
- **Draggable** — click and drag to reposition
- **Auto-dismisses** after 15 seconds (configurable)
- **Press Escape** to dismiss immediately
- **Excluded from screenshots** on macOS (won't appear in your own screen captures)

### UI Elements
- **Title bar** — "Radiology Copilot" + confidence badge (color-coded)
- **Finding text** — the AI's assessment
- **Timestamp** — when the analysis was performed
- **Dismiss button** — accept/ignore the finding
- **Disagree / Flag button** — opens text input for the radiologist's override

### Confidence Colors
| Level | Color | Meaning |
|-------|-------|---------|
| HIGH | Red | Finding needs attention — urgent or significant |
| MEDIUM | Yellow | Possible finding — recommend follow-up |
| LOW | Green | Routine / no significant findings |

---

## JSON Schemas (MCP Integration Contract)

These are the exact JSON shapes the copilot sends and expects. Your MCP server team should implement endpoints that accept and return these formats.

### `POST /analyze` — Request

```json
{
    "image_b64": "string — base64-encoded JPEG screenshot",
    "patient_context": "string — optional free-text from the radiologist",
    "timestamp": "string — ISO-8601 timestamp of capture",
    "session_id": "string — UUID generated once at app launch"
}
```

### `POST /analyze` — Response

```json
{
    "findings": "string — human-readable finding summary",
    "confidence": "string — 'low', 'medium', or 'high'",
    "specialist_flags": ["string — which sub-models flagged something"],
    "recommended_action": "string — what the system recommends"
}
```

### `POST /flag` — Request (Disagreement)

```json
{
    "ai_finding": "string — the AI's original finding",
    "radiologist_override": "string — what the radiologist thinks instead",
    "image_hash": "string — SHA256 hash prefix for traceability",
    "timestamp": "string — ISO-8601",
    "session_id": "string — UUID"
}
```

### `POST /flag` — Response

```json
{
    "status": "string — 'received' or 'error'",
    "flag_id": "string — unique ID for this flag"
}
```

### `GET /health`

```json
{
    "status": "ok",
    "mock": true
}
```

---

## Swapping the Mock for Your Real MCP Server

The mock server is a **drop-in placeholder**. To swap it for your real MCP server:

### Option A: Environment Variable

```bash
export RADCOPILOT_BACKEND_URL="https://your-mcp-server.com"
RADCOPILOT_NO_SERVER=1 npm start
```

### Option B: Edit config.py

Change one line in `config.py`:

```python
# Before (mock)
BACKEND_URL = os.getenv("RADCOPILOT_BACKEND_URL", "http://127.0.0.1:8100")

# After (real)
BACKEND_URL = os.getenv("RADCOPILOT_BACKEND_URL", "https://your-mcp-server.com")
```

**Nothing else changes.** The client (`backend/client.py`) sends the same JSON payloads and expects the same response shapes regardless of where the backend lives.

### What Your MCP Server Needs to Implement

1. `POST /analyze` — Accept `AnalyzeRequest`, return `AnalyzeResponse` (see schemas above)
2. `POST /flag` — Accept `FlagRequest`, return `FlagResponse`
3. `GET /health` — Return `{"status": "ok"}`

That's it. The copilot doesn't care what happens inside your server — whether you route to 30 specialist models via MCP tools or run a single monolithic model. The interface is the same.

---

## Configuration Reference

All settings live in `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `BACKEND_URL` | `http://127.0.0.1:8100` | Backend server URL (env: `RADCOPILOT_BACKEND_URL`) |
| `DESKTOP_BRIDGE_PORT` | `38100` | Local FastAPI bridge port used by Electron |
| `DESKTOP_HOTKEY` | `CommandOrControl+Shift+R` | Electron accelerator for the global capture shortcut |
| `REQUEST_TIMEOUT` | `8` | Seconds before backend call times out |
| `AUTO_DISMISS_SECONDS` | `15` | Auto-hide overlay after N seconds (0 = never) |
| `OVERLAY_MARGIN_RIGHT` | `30` | Pixels from right screen edge |
| `OVERLAY_MARGIN_BOTTOM` | `60` | Pixels from bottom screen edge |
| `TIMER_INTERVAL_SECONDS` | `0` | Auto-capture interval (0 = disabled) |
| `SCREENSHOT_JPEG_QUALITY` | `85` | JPEG compression quality |
| `DB_PATH` | `./radcopilot.db` | SQLite database file path (env: `RADCOPILOT_DB`) |
| `MOCK_SERVER_PORT` | `8100` | Port for the mock FastAPI server |

---

## Building to Executable

```bash
./build.sh
```

This installs the Python and Electron dependencies, then validates the desktop sources.

### macOS Distribution Notes

| Requirement | Details |
|-------------|---------|
| **Screen Recording** | Required on macOS 10.15+. `mss` will fail silently without it. |
| **Microphone** | Required only if you enable Gemini Live voice capture. |
| **Code Signing** | Required for shipping a packaged Electron app outside local development. |
| **Gatekeeper** | Unsigned Electron builds are blocked by default on macOS. |
| **Notarization** | Still required for external distribution. |

---

## macOS Permissions

### Screen Recording
1. Open **System Settings → Privacy & Security → Screen Recording**
2. Click **+** and add the Electron app you launch for local development (or Terminal/iTerm2 if macOS attributes the permission there)
3. Restart the app

If permission is missing, the Electron overlay surfaces an in-app warning from the Python bridge.

### Microphone (for Gemini Live voice capture)
1. Open **System Settings → Privacy & Security → Microphone**
2. Click **+** and add the Electron app or the terminal app used to launch it locally
3. You may need to restart the app

---

## Full System Vision

This MVP is the **workstation client** — the left side of the architecture. The full system (being built by your MCP team) includes:

### Tiered Compute Architecture

```
Layer 1: LIGHTWEIGHT (every scan)
├── LLM pre-screens incoming worklist
├── Soft triage — nudges potentially serious cases up ~10-15% in queue
└── Cost: minimal — fast inference on everything

Layer 2: SPECIALIST MODELS (during the read)
├── LLM orchestrator routes to parallel specialist sub-models via MCP tools
├── Each worker has narrow context + narrow toolset (liver, lung, neuro, etc.)
├── Patient history auto-generated from EHR
├── Results synthesized and compared against radiologist's read
└── Cost: moderate — multiple focused inferences

Layer 3: HEAVY ESCALATION (only on disagreements)
├── Triggered when AI and radiologist disagree
├── GPT-5.2 Pro / Gemini 3 Deep Think / frontier reasoning models
├── Independent re-evaluation with annotation and commentary
├── If consistent with doctor → diff resolves silently (no alert fatigue)
├── If still disagrees → escalated to second radiologist with full context
└── Cost: expensive — but only ~2-5% of reads reach this layer
```

### Why This Matters

| Current QA | With Copilot |
|------------|-------------|
| ~5% random peer review sampling | 100% coverage — every read compared |
| Retrospective (days/weeks later) | Near real-time |
| No pattern detection on radiologists | "Dr. Smith under-calls lung nodules" over time |
| Manual worklist ordering | Soft AI triage — critical findings surface sooner |
| Disagreements lost | Every diff logged, annotated, reviewable, shareable |

### The Data Flywheel

Every resolved diff — whether in favor of AI or doctor — is high-value training data. Over time:
- Specialist models improve
- Diffs decrease
- Escalations decrease
- System gets cheaper and more accurate simultaneously

### Regulatory Positioning

The AI **assists**, never **diagnoses**. This keeps the system in FDA Class II territory (decision support) rather than Class III (autonomous diagnosis) — a fundamentally different and much simpler regulatory path. The radiologist remains the decision-maker at every step.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `Electron` | Desktop overlay shell and global shortcut |
| `mss` | Fast cross-platform screenshot capture |
| `Pillow` | Image processing (JPEG encoding) |
| `httpx` | Async HTTP client for backend communication |
| `FastAPI` | Mock backend server |
| `uvicorn` | ASGI server for FastAPI |
| `pydantic` | Request/response validation |
| `@google/genai` | Gemini Live integration in Electron |

---

## License

Proprietary — All rights reserved.
