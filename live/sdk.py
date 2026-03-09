"""Small compatibility helpers around the optional google-genai dependency."""

from __future__ import annotations

from typing import Any

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - exercised when dependency is absent locally
    genai = None
    types = None


def require_google_genai():
    """Return imported SDK modules or raise a clear runtime error."""
    if genai is None or types is None:
        raise RuntimeError(
            "google-genai is not installed. Run `pip install -r requirements.txt` before starting the Live scaffold."
        )
    return genai, types


def make_blob(data: bytes, mime_type: str) -> Any:
    """Build a blob for realtime media input."""
    if types is None:
        return {"data": data, "mimeType": mime_type}
    return types.Blob(data=data, mimeType=mime_type)


def make_function_response(function_call_id: str, name: str, response: dict[str, Any]) -> Any:
    """Build a function response payload accepted by the SDK."""
    if types is None:
        return {"id": function_call_id, "name": name, "response": response}
    return types.FunctionResponse(id=function_call_id, name=name, response=response)
