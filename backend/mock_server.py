"""
Radiology Copilot — Mock FastAPI Server
Simulates what the real MCP server will do.
Returns realistic rotating radiology responses so the UI is fully testable end-to-end.

Run standalone:  python -m backend.mock_server
"""

import random
import time
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import config

app = FastAPI(title="Radiology Copilot Mock MCP Server")


# ── JSON Schemas (contract for your MCP team) ───────────────────────────────

class AnalyzeRequest(BaseModel):
    """What the copilot sends to the backend."""
    image_b64: str              # base64-encoded JPEG screenshot
    patient_context: str = ""   # optional free-text context from the radiologist
    timestamp: str = ""         # ISO-8601 timestamp of capture
    session_id: str = ""        # UUID generated once at app launch


class AnalyzeResponse(BaseModel):
    """What the backend returns to the copilot."""
    findings: str               # human-readable finding summary
    confidence: str             # "low", "medium", or "high"
    specialist_flags: list[str] # which specialist sub-models flagged something
    recommended_action: str     # what the system recommends


class FlagRequest(BaseModel):
    """What the copilot sends when the radiologist disagrees."""
    ai_finding: str             # the AI's original finding
    radiologist_override: str   # what the radiologist thinks instead
    image_hash: str             # hash of the screenshot for traceability
    timestamp: str = ""
    session_id: str = ""


class FlagResponse(BaseModel):
    """Acknowledgment of a disagreement flag."""
    status: str
    flag_id: str


# ── Mock Data ────────────────────────────────────────────────────────────────

MOCK_FINDINGS = [
    {
        "findings": "Possible nodule in right upper lobe — recommend comparison with prior",
        "confidence": "medium",
        "specialist_flags": ["pulmonary_nodule_v2", "lung_screening_v1"],
        "recommended_action": "Compare with prior chest CT if available; consider follow-up in 3 months",
    },
    {
        "findings": "No acute findings detected",
        "confidence": "high",
        "specialist_flags": [],
        "recommended_action": "Routine follow-up per clinical indication",
    },
    {
        "findings": "Hyperdense region in basal ganglia — consider hemorrhage",
        "confidence": "high",
        "specialist_flags": ["neuro_hemorrhage_v3", "stroke_detection_v1"],
        "recommended_action": "URGENT: Notify referring physician immediately; recommend CTA",
    },
    {
        "findings": "Mass effect noted left hemisphere — urgent review recommended",
        "confidence": "high",
        "specialist_flags": ["neuro_mass_v2", "midline_shift_v1"],
        "recommended_action": "URGENT: Neurosurgery consult recommended; compare with prior if available",
    },
    {
        "findings": "Pleural effusion present bilaterally — correlate clinically",
        "confidence": "medium",
        "specialist_flags": ["pleural_effusion_v1", "cardiac_assessment_v2"],
        "recommended_action": "Correlate with clinical symptoms; consider thoracentesis if symptomatic",
    },
    {
        "findings": "Stable 1.2cm hepatic cyst — unchanged from prior",
        "confidence": "low",
        "specialist_flags": ["liver_lesion_v2"],
        "recommended_action": "No further workup needed; routine surveillance",
    },
    {
        "findings": "2.8cm enhancing renal mass right kidney — suspicious for RCC",
        "confidence": "high",
        "specialist_flags": ["renal_mass_v1", "contrast_enhancement_v2"],
        "recommended_action": "Urology referral recommended; consider biopsy or MRI characterization",
    },
    {
        "findings": "Compression fracture T12 — acute vs chronic indeterminate",
        "confidence": "medium",
        "specialist_flags": ["spine_fracture_v1", "osteoporosis_screen_v1"],
        "recommended_action": "MRI with STIR recommended to assess acuity; DEXA scan if not recent",
    },
]


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """
    Simulate AI analysis of a radiology screenshot.
    In production, this is where the MCP orchestrator routes to specialist models.
    """
    # Simulate processing latency (0.5–2s)
    time.sleep(random.uniform(0.5, 2.0))

    finding = random.choice(MOCK_FINDINGS)
    return AnalyzeResponse(**finding)


@app.post("/flag", response_model=FlagResponse)
async def flag(req: FlagRequest):
    """
    Receive a disagreement flag from the radiologist.
    In production, this triggers the heavy-model escalation pipeline.
    """
    flag_id = str(uuid.uuid4())[:8]
    print(f"[FLAGGED] {flag_id}: AI said '{req.ai_finding}' | Radiologist says '{req.radiologist_override}'")
    return FlagResponse(status="received", flag_id=flag_id)


@app.get("/health")
async def health():
    return {"status": "ok", "mock": True}


@app.websocket("/live/screenshot")
async def live_screenshot_socket(websocket: WebSocket):
    """
    Temporary localhost websocket used by the Gemini Live scaffold.
    Accepts discrete screenshot payloads and immediately acks them.
    """
    await websocket.accept()

    try:
        while True:
            message = await websocket.receive_json()
            request_id = message.get("request_id", "")
            image_hash = message.get("image_hash", "")
            reason = message.get("reason", "")
            payload_type = message.get("type")

            if payload_type != "screenshot.capture" or not request_id:
                await websocket.send_json(
                    {
                        "type": "screenshot.ack",
                        "request_id": request_id,
                        "status": "error",
                        "backend_event_id": "",
                        "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "error": "Invalid screenshot payload",
                    }
                )
                continue

            backend_event_id = str(uuid.uuid4())
            print(
                f"[LIVE SCREENSHOT] {backend_event_id[:8]} | request={request_id[:8]} "
                f"| hash={image_hash} | reason={reason}"
            )
            await websocket.send_json(
                {
                    "type": "screenshot.ack",
                    "request_id": request_id,
                    "status": "ok",
                    "backend_event_id": backend_event_id,
                    "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "error": None,
                }
            )
    except WebSocketDisconnect:
        return


# ── Standalone runner ────────────────────────────────────────────────────────

def run_mock_server():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=config.MOCK_SERVER_PORT, log_level="info")


if __name__ == "__main__":
    run_mock_server()
