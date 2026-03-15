"""
Full orchestration pipeline.

Flow:
  Stage 0  → initial state (root in-progress, 0%)
  Stage 1  → triage complete (modality identified, 20%)
  Stage 2…N → one stage per tool: add child in-progress → run → mark complete
  Stage N+1 → synthesis: Gemini produces findings + assessment
  Final    → root complete (positive/negative), 100%, annotations + context written
"""

import base64
import sys
import os
import traceback

# Allow imports from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    DiagnosisState, ModelNode, MedicalModel, Annotation, Rectangle,
    ImageDataDB,
)
from services.database import FirebaseDatabase

from config import (
    MODALITY_TOOLS, TOOL_MODELS, TRIAGE_MODEL, SYNTHESIS_MODEL,
    NORMAL_LABELS, MODALITY_ANATOMY, CONFIDENCE_COLOR,
)
from agents import triage_agent, synthesis_agent

# Import all tools
from tools_deployment.tools import (
    PneumoniaTool, TBTool, CovidTool, AlzheimersTool, KneeOATool,
)

# ── Tool registry ──────────────────────────────────────────────────────────────

_TOOL_CLASSES = {
    "pneumonia": PneumoniaTool,
    "tb":        TBTool,
    "covid":     CovidTool,
    "alzheimers": AlzheimersTool,
    "knee_oa":   KneeOATool,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write(db: FirebaseDatabase, image_id: str, tree: ModelNode, pct: float,
           annotations: list, context: str) -> None:
    db.set_rl_data("diagnosis", DiagnosisState(
        id=image_id,
        image_id=image_id,
        progress_tree=tree,
        percent_completion=round(pct, 3),
        annotations=annotations,
        overall_diagnosis_context=context,
    ))


def _orch_root(status: str, children: list[ModelNode]) -> ModelNode:
    return ModelNode(
        status=status,
        model=MedicalModel(
            name="Orchestrator",
            provider="RadCoPilot",
            description="Routes scan to specialist diagnostic models based on modality",
        ),
        children=children,
    )


def _make_triage_node(status: str, description: str, children: list[ModelNode]) -> ModelNode:
    return ModelNode(
        status=status,
        model=MedicalModel(
            name=TRIAGE_MODEL.name,
            provider=TRIAGE_MODEL.provider,
            description=description or TRIAGE_MODEL.description,
        ),
        children=children,
    )


def _make_tool_node(tool_name: str, status: str) -> ModelNode:
    model_meta = TOOL_MODELS.get(tool_name, MedicalModel(
        name=tool_name.title(), provider="RadCoPilot", description=""
    ))
    return ModelNode(status=status, model=model_meta, children=[])


def _tool_to_status(result: dict) -> str:
    pred = result.get("prediction", "").lower().replace("_", " ").replace("-", " ")
    return "negative" if pred in NORMAL_LABELS else "positive"


def _build_annotations(findings: list[dict], modality: str) -> list[Annotation]:
    """Convert Gemini synthesis findings into Annotation objects with bounding boxes."""
    anatomy = MODALITY_ANATOMY.get(modality, {})
    annotations = []
    for i, f in enumerate(findings, start=1):
        region     = f.get("region", "")
        confidence = f.get("confidence", "medium")
        color      = CONFIDENCE_COLOR.get(confidence, "#f97316")

        # Use anatomy coords if region is known, otherwise a generic centre box
        rect = anatomy.get(region)
        if rect is None:
            rect = Rectangle(x=80, y=80, width=140, height=140, color=color)
        else:
            # Override color to match confidence level
            rect = Rectangle(x=rect.x, y=rect.y, width=rect.width, height=rect.height, color=color)

        annotations.append(Annotation(
            name=f.get("name", f"Finding {i}"),
            description=f.get("description", ""),
            number=i,
            annotations=[rect],
            confidence=confidence,
        ))
    return annotations


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_pipeline(image_id: str, image_b64: str, db_info: ImageDataDB) -> None:
    """
    Full pipeline. Runs in a background thread.
    Writes progressive DiagnosisState updates to Firebase.
    """
    db           = FirebaseDatabase()
    image_bytes  = base64.b64decode(image_b64)

    # ── Stage 0: Initial ──────────────────────────────────────────────────────
    _write(db, image_id, _orch_root("in-progress", []), 0.0, [], "")

    # ── Triage ────────────────────────────────────────────────────────────────
    triage_result = triage_agent(
        image_b64,
        image_location=getattr(db_info, "image_location", ""),
        image_type=getattr(db_info, "image_type", ""),
    )
    modality        = triage_result.get("modality", "chest_xray")
    triage_desc     = triage_result.get("description", TRIAGE_MODEL.description)
    triage_confidence = triage_result.get("confidence", "medium")
    triage_status   = "positive" if triage_confidence != "low" else "negative"

    # ── Stage 1: Triage written ───────────────────────────────────────────────
    triage_node_empty = _make_triage_node(triage_status, triage_desc, [])
    _write(db, image_id, _orch_root("in-progress", [triage_node_empty]), 0.2, [], "")

    # ── Tool stages ───────────────────────────────────────────────────────────
    tool_names   = MODALITY_TOOLS.get(modality, [])
    n_tools      = max(len(tool_names), 1)
    tool_results = []           # [{name, result}]
    done_children: list[ModelNode] = []  # completed tool nodes

    for i, tool_name in enumerate(tool_names):
        # Show this tool as in-progress
        in_progress_node = _make_tool_node(tool_name, "in-progress")
        current_triage   = _make_triage_node(
            triage_status, triage_desc, done_children + [in_progress_node]
        )
        pct = 0.2 + 0.6 * (i / n_tools)
        _write(db, image_id, _orch_root("in-progress", [current_triage]), pct, [], "")

        # Run the tool
        try:
            tool   = _TOOL_CLASSES[tool_name]()
            result = tool.predict(image_bytes)
        except Exception:
            traceback.print_exc()
            result = {"prediction": "error", "scores": {}, "confidence": 0.0}

        tool_results.append({"name": tool_name, "result": result})
        status = _tool_to_status(result)
        done_children.append(_make_tool_node(tool_name, status))

    # All tools finished (80%)
    final_triage = _make_triage_node(triage_status, triage_desc, done_children)
    _write(db, image_id, _orch_root("in-progress", [final_triage]), 0.8, [], "")

    # ── Synthesis ─────────────────────────────────────────────────────────────
    try:
        synthesis = synthesis_agent(image_b64, modality, tool_results)
    except Exception:
        traceback.print_exc()
        synthesis = {"findings": [], "overall_assessment": ""}

    annotations     = _build_annotations(synthesis.get("findings", []), modality)
    overall_context = synthesis.get("overall_assessment", "")

    # Add synthesis as a final child node under triage
    synthesis_node = ModelNode(
        status="positive" if annotations else "negative",
        model=SYNTHESIS_MODEL,
        children=[],
    )
    final_triage_with_synthesis = _make_triage_node(
        triage_status, triage_desc, done_children + [synthesis_node]
    )

    # ── Final stage ───────────────────────────────────────────────────────────
    any_positive    = any(c.status == "positive" for c in done_children)
    root_status     = "positive" if any_positive else "negative"

    _write(
        db, image_id,
        _orch_root(root_status, [final_triage_with_synthesis]),
        1.0,
        annotations,
        overall_context,
    )
