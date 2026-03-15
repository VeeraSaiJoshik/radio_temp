"""
Gemini VLM agent calls for the orchestrator_manager pipeline.

Three agents:
  1. triage_agent   — identifies imaging modality from the raw image
  2. synthesis_agent — synthesizes all tool results into clinical findings + assessment

All agents return plain dicts and are resilient to API failures (return fallback dicts).
"""

import base64
import json
import os
import traceback
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

from config import GEMINI_MODEL, MODALITY_ANATOMY

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

# ── Helpers ────────────────────────────────────────────────────────────────────

def _image_part(image_b64: str) -> dict:
    """Decode base64 image into a Gemini content part."""
    return {"mime_type": "image/jpeg", "data": base64.b64decode(image_b64)}


def _call_gemini(parts: list, response_schema_hint: str) -> dict:
    """
    Call Gemini with the given content parts.
    Expects JSON response. Returns parsed dict or empty dict on failure.
    """
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            parts,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
            ),
        )
        return json.loads(response.text)
    except Exception:
        traceback.print_exc()
        return {}


# ── Agent 1: Triage ────────────────────────────────────────────────────────────

TRIAGE_PROMPT = """You are a radiology AI triage agent. Analyze this medical image carefully.

Identify the imaging modality and body region. Choose the closest match:
- "chest_xray"  (chest X-ray, CXR, PA or AP view, chest radiograph)
- "knee_xray"   (knee radiograph, knee X-ray, lower extremity)
- "brain_mri"   (brain MRI, head MRI, CT head, cranial imaging)
- "other"       (anything else: abdominal, spine, ultrasound, etc.)

Additional PACS metadata (may be empty or inaccurate — trust the image first):
{context}

Respond with valid JSON only:
{{
  "modality": "chest_xray",
  "description": "PA chest radiograph showing bilateral lung fields with clear cardiac silhouette",
  "confidence": "high"
}}"""


def triage_agent(image_b64: str, image_location: str = "", image_type: str = "") -> dict:
    """
    Identify the imaging modality from the image.

    Returns: {"modality": str, "description": str, "confidence": str}
    Falls back to metadata hints if Gemini fails.
    """
    context = f"image_location={image_location!r}, image_type={image_type!r}"
    prompt  = TRIAGE_PROMPT.format(context=context)

    result = _call_gemini([_image_part(image_b64), prompt], "triage")

    # Validate modality field
    valid_modalities = {"chest_xray", "knee_xray", "brain_mri", "other"}
    if result.get("modality") not in valid_modalities:
        # Fallback: infer from PACS metadata
        result["modality"] = _infer_modality_from_metadata(image_location, image_type)
        result.setdefault("description", f"Modality inferred from metadata: {result['modality']}")
        result["confidence"] = "low"

    return result


def _infer_modality_from_metadata(image_location: str, image_type: str) -> str:
    loc  = (image_location or "").lower()
    kind = (image_type or "").lower()
    if any(w in loc for w in ("chest", "lung", "thorax", "pulmonary")):
        return "chest_xray"
    if "knee" in loc:
        return "knee_xray"
    if any(w in loc for w in ("brain", "head", "cranial")) or "mri" in kind:
        return "brain_mri"
    return "chest_xray"  # Most common in this system — safe default


# ── Agent 2: Synthesis ─────────────────────────────────────────────────────────

SYNTHESIS_PROMPT = """You are a radiologist AI assistant performing clinical synthesis.

Imaging modality: {modality}

ML model predictions from specialist classifiers:
{tool_results}

Analyze the image together with these predictions and provide:
1. Specific findings with their anatomical locations
2. A comprehensive clinical assessment

Valid anatomical regions for this modality (use ONLY these region keys):
{valid_regions}

Confidence levels: "high" (>80% model confidence + visible finding), "medium" (50-80%), "low" (<50%)

If no significant pathology is found, return an empty findings array.

Respond with valid JSON only:
{{
  "findings": [
    {{
      "name": "Finding name (short, clinical)",
      "description": "Detailed clinical description of the finding",
      "confidence": "high",
      "region": "right_upper_lobe"
    }}
  ],
  "overall_assessment": "Comprehensive clinical assessment integrating all model predictions and visual findings. Include relevant recommendations."
}}"""


def synthesis_agent(
    image_b64: str,
    modality: str,
    tool_results: list[dict[str, Any]],
) -> dict:
    """
    Synthesize all tool results + the image into clinical findings and an overall assessment.

    tool_results format: [{"name": "tb", "result": {"prediction": "Tuberculosis", "scores": {...}, "confidence": 0.9}}, ...]

    Returns: {"findings": list, "overall_assessment": str}
    Falls back to a plain-text summary if Gemini fails.
    """
    # Format tool results for the prompt
    tool_lines = []
    for tr in tool_results:
        r = tr["result"]
        pred       = r.get("prediction", "unknown")
        confidence = r.get("confidence", 0.0)
        scores     = r.get("scores", {})
        scores_str = ", ".join(f"{k}: {v:.2%}" for k, v in scores.items())
        tool_lines.append(f"  - {tr['name'].upper()}: {pred} (confidence {confidence:.2%}) | scores: {scores_str}")

    tool_results_str = "\n".join(tool_lines) if tool_lines else "  No tool predictions available."
    valid_regions    = list(MODALITY_ANATOMY.get(modality, {}).keys())

    prompt = SYNTHESIS_PROMPT.format(
        modality=modality,
        tool_results=tool_results_str,
        valid_regions=", ".join(valid_regions) if valid_regions else "none",
    )

    result = _call_gemini([_image_part(image_b64), prompt], "synthesis")

    if not result.get("overall_assessment"):
        result["overall_assessment"] = _fallback_assessment(tool_results)
    result.setdefault("findings", [])

    return result


def _fallback_assessment(tool_results: list[dict]) -> str:
    """Plain-text fallback when Gemini synthesis fails."""
    if not tool_results:
        return "Analysis complete. No specialist model predictions available."
    lines = []
    for tr in tool_results:
        r    = tr["result"]
        pred = r.get("prediction", "unknown")
        conf = r.get("confidence", 0.0)
        lines.append(f"{tr['name'].upper()}: {pred} ({conf:.1%})")
    return "Model predictions: " + " | ".join(lines) + ". Clinical correlation recommended."
