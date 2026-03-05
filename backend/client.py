"""
Radiology Copilot — Backend HTTP Client
Async client that sends screenshots to the backend and receives AI analysis.
When your MCP server is ready, just change BACKEND_URL in config.py — this code stays the same.
"""

import httpx
from datetime import datetime

import config


class BackendClient:
    """Async HTTP client for communicating with the analysis backend."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._client = httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT)

    async def analyze(self, image_b64: str, patient_context: str = "") -> dict:
        """
        Send a screenshot to the backend for AI analysis.

        Args:
            image_b64: Base64-encoded JPEG screenshot.
            patient_context: Optional free-text context from the radiologist.

        Returns:
            Dict with keys: findings, confidence, specialist_flags, recommended_action.
            On error, returns a dict with findings="Analysis unavailable" and confidence="low".
        """
        payload = {
            "image_b64": image_b64,
            "patient_context": patient_context,
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
        }

        try:
            resp = await self._client.post(config.ANALYZE_ENDPOINT, json=payload)
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError) as e:
            return {
                "findings": f"Analysis unavailable — {type(e).__name__}",
                "confidence": "low",
                "specialist_flags": [],
                "recommended_action": "Retry or check backend connection",
            }

    async def flag(self, ai_finding: str, radiologist_override: str, image_hash: str) -> dict:
        """
        Send a disagreement flag to the backend.

        Args:
            ai_finding: The AI's original finding text.
            radiologist_override: What the radiologist thinks instead.
            image_hash: Hash of the screenshot for traceability.

        Returns:
            Dict with status and flag_id, or error info.
        """
        payload = {
            "ai_finding": ai_finding,
            "radiologist_override": radiologist_override,
            "image_hash": image_hash,
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
        }

        try:
            resp = await self._client.post(config.FLAG_ENDPOINT, json=payload)
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError):
            return {"status": "error", "flag_id": ""}

    async def close(self):
        await self._client.aclose()
