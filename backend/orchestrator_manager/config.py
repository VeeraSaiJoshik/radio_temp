"""
Configuration for the orchestrator_manager pipeline.
"""

import os
from models import Rectangle, MedicalModel

# ── Gemini ─────────────────────────────────────────────────────────────────────

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# ── Modality routing ───────────────────────────────────────────────────────────
# Maps triage output → list of tool names to run (in order)

MODALITY_TOOLS: dict[str, list[str]] = {
    "chest_xray": ["pneumonia", "tb", "covid"],
    "knee_xray":  ["knee_oa"],
    "brain_mri":  ["alzheimers"],
    "other":      [],   # Gemini synthesis only, no tools
}

# Labels that mean "nothing found" → node status "negative"
NORMAL_LABELS = {"normal", "non_demented"}

# ── MedicalModel definitions per tool ─────────────────────────────────────────

TOOL_MODELS: dict[str, MedicalModel] = {
    "pneumonia": MedicalModel(
        name="Pneumonia Classifier",
        provider="HuggingFace / RadCoPilot",
        description="Ensemble ViT model detecting bacterial and viral pneumonia",
    ),
    "tb": MedicalModel(
        name="TB Detector (TBViT)",
        provider="RadCoPilot",
        description="Vision Transformer ensemble detecting tuberculosis infiltrate patterns",
    ),
    "covid": MedicalModel(
        name="COVID-19 CXR Classifier",
        provider="RadCoPilot",
        description="InceptionV3 + ViT ensemble for COVID, Lung Opacity, Viral Pneumonia",
    ),
    "alzheimers": MedicalModel(
        name="Alzheimers Classifier",
        provider="HuggingFace",
        description="ViT model grading dementia severity from brain MRI",
    ),
    "knee_oa": MedicalModel(
        name="Knee OA Grader",
        provider="RadCoPilot",
        description="ONNX model grading knee osteoarthritis severity (KL scale)",
    ),
}

TRIAGE_MODEL = MedicalModel(
    name="Modality Triage",
    provider="Google Gemini VLM",
    description="Identifies imaging modality and routes to specialist models",
)

SYNTHESIS_MODEL = MedicalModel(
    name="Clinical Synthesis",
    provider="Google Gemini VLM",
    description="Synthesizes all model outputs into a clinical assessment",
)

# ── Anatomical region → bounding box ──────────────────────────────────────────
# Coordinates approximate a standard 300x300 display of each image type.

CHEST_ANATOMY: dict[str, Rectangle] = {
    "right_upper_lobe":         Rectangle(x=155, y=45,  width=100, height=90,  color="#ef4444"),
    "left_upper_lobe":          Rectangle(x=45,  y=45,  width=100, height=90,  color="#ef4444"),
    "right_middle_lobe":        Rectangle(x=155, y=135, width=100, height=70,  color="#f97316"),
    "right_lower_lobe":         Rectangle(x=155, y=205, width=100, height=95,  color="#f97316"),
    "left_lower_lobe":          Rectangle(x=45,  y=205, width=100, height=95,  color="#f97316"),
    "right_hilum":              Rectangle(x=170, y=125, width=70,  height=65,  color="#eab308"),
    "left_hilum":               Rectangle(x=70,  y=125, width=70,  height=65,  color="#eab308"),
    "perihilar":                Rectangle(x=90,  y=110, width=120, height=80,  color="#eab308"),
    "bilateral_upper":          Rectangle(x=45,  y=45,  width=210, height=90,  color="#ef4444"),
    "bilateral_lower":          Rectangle(x=45,  y=205, width=210, height=95,  color="#f97316"),
    "cardiomegaly":             Rectangle(x=80,  y=105, width=140, height=150, color="#8b5cf6"),
    "pleural_effusion_right":   Rectangle(x=155, y=270, width=100, height=75,  color="#3b82f6"),
    "pleural_effusion_left":    Rectangle(x=45,  y=270, width=100, height=75,  color="#3b82f6"),
}

KNEE_ANATOMY: dict[str, Rectangle] = {
    "medial_compartment":       Rectangle(x=80,  y=100, width=60,  height=80,  color="#ef4444"),
    "lateral_compartment":      Rectangle(x=160, y=100, width=60,  height=80,  color="#f97316"),
    "joint_space":              Rectangle(x=80,  y=120, width=140, height=40,  color="#eab308"),
    "osteophytes":              Rectangle(x=70,  y=90,  width=160, height=120, color="#f97316"),
    "subchondral_sclerosis":    Rectangle(x=85,  y=105, width=130, height=90,  color="#ef4444"),
}

BRAIN_ANATOMY: dict[str, Rectangle] = {
    "hippocampus":              Rectangle(x=85,  y=120, width=80,  height=60,  color="#ef4444"),
    "temporal_lobe":            Rectangle(x=50,  y=100, width=120, height=80,  color="#f97316"),
    "frontal_lobe":             Rectangle(x=70,  y=40,  width=110, height=80,  color="#eab308"),
    "cortical_atrophy":         Rectangle(x=40,  y=40,  width=180, height=160, color="#8b5cf6"),
    "ventricular_enlargement":  Rectangle(x=95,  y=80,  width=110, height=110, color="#3b82f6"),
}

MODALITY_ANATOMY: dict[str, dict[str, Rectangle]] = {
    "chest_xray": CHEST_ANATOMY,
    "knee_xray":  KNEE_ANATOMY,
    "brain_mri":  BRAIN_ANATOMY,
    "other":      {},
}

CONFIDENCE_COLOR: dict[str, str] = {
    "high":   "#ef4444",
    "medium": "#f97316",
    "low":    "#eab308",
}
