import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading
import time

from fastapi import FastAPI
import uvicorn

from models import (
    DiagnosisState, ModelNode, MedicalModel, Annotation,
    Rectangle, OrchestratorInput
)
from services.database import FirebaseDatabase

app = FastAPI()

_call_counter = 0
_counter_lock = threading.Lock()


# ── Shared model builders ──────────────────────────────────────────────────────

def _orch():
    return MedicalModel(
        name="Orchestrator",
        provider="RadCoPilot",
        description="Routes scan to specialist diagnostic models based on modality"
    )

def _triage():
    return MedicalModel(
        name="Chest X-Ray Triage",
        provider="Stanford AI Lab",
        description="Confirms modality and identifies the region of interest"
    )

def _tb():
    return MedicalModel(
        name="TB Detector (TBViT)",
        provider="RadCoPilot",
        description="Vision Transformer detecting tuberculosis infiltrate patterns"
    )

def _pneumonia():
    return MedicalModel(
        name="Pneumonia Classifier",
        provider="HuggingFace / RadCoPilot",
        description="Differentiates bacterial and viral pneumonia from clear lungs"
    )


# ── Patient 1: Ahmad Karimi — TB Positive ─────────────────────────────────────
#
#  Stage timeline (delays between stages):
#    t=0s   Orchestrator in-progress, no children yet
#    t=1.5s Chest Triage added, in-progress
#    t=3s   Triage → positive, TB Detector added, in-progress
#    t=4.5s TB Detector → positive, Pneumonia Classifier added, in-progress
#    t=6s   Pneumonia → negative, full annotations + context, 100% done

TB_STAGES = [
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="in-progress", model=_orch(), children=[]
        ),
        percent_completion=0.0,
        annotations=[],
        overall_diagnosis_context=""
    ),
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="in-progress", model=_orch(),
            children=[
                ModelNode(status="in-progress", model=_triage(), children=[])
            ]
        ),
        percent_completion=0.2,
        annotations=[],
        overall_diagnosis_context=""
    ),
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="in-progress", model=_orch(),
            children=[
                ModelNode(
                    status="positive", model=_triage(),
                    children=[
                        ModelNode(status="in-progress", model=_tb(), children=[])
                    ]
                )
            ]
        ),
        percent_completion=0.45,
        annotations=[],
        overall_diagnosis_context=""
    ),
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="in-progress", model=_orch(),
            children=[
                ModelNode(
                    status="positive", model=_triage(),
                    children=[
                        ModelNode(status="positive", model=_tb(), children=[]),
                        ModelNode(status="in-progress", model=_pneumonia(), children=[])
                    ]
                )
            ]
        ),
        percent_completion=0.7,
        annotations=[],
        overall_diagnosis_context=""
    ),
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="positive", model=_orch(),
            children=[
                ModelNode(
                    status="positive", model=_triage(),
                    children=[
                        ModelNode(status="positive", model=_tb(), children=[]),
                        ModelNode(status="negative", model=_pneumonia(), children=[])
                    ]
                )
            ]
        ),
        percent_completion=1.0,
        annotations=[
            Annotation(
                name="Right upper lobe infiltrate",
                description="Dense consolidation with cavitation — active TB pattern",
                number=1,
                annotations=[Rectangle(x=180, y=80, width=110, height=90, color="#ef4444")],
                confidence="high"
            ),
            Annotation(
                name="Left upper lobe haziness",
                description="Patchy bilateral opacity suggesting TB spread",
                number=2,
                annotations=[Rectangle(x=60, y=90, width=100, height=80, color="#f97316")],
                confidence="medium"
            )
        ],
        overall_diagnosis_context=(
            "HIGH CONFIDENCE TB POSITIVE (94.2%): TBViT detected bilateral upper-lobe "
            "infiltrates with right apical cavitation. Pneumonia excluded. Recommend "
            "immediate respiratory isolation, sputum AFB smear x3, GeneXpert MTB/RIF, "
            "and infectious disease consultation. Initiate RIPE therapy pending culture results."
        )
    ),
]


# ── Patient 2: Maria Santos — Pneumonia Positive ──────────────────────────────
#
#  Stage timeline:
#    t=0s   Orchestrator in-progress, no children yet
#    t=1.5s Chest Triage added, in-progress
#    t=3s   Triage → positive, Pneumonia Classifier added, in-progress
#    t=4.5s Pneumonia → positive, TB Detector added, in-progress
#    t=6s   TB Detector → negative, full annotations + context, 100% done

PNEUMONIA_STAGES = [
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="in-progress", model=_orch(), children=[]
        ),
        percent_completion=0.0,
        annotations=[],
        overall_diagnosis_context=""
    ),
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="in-progress", model=_orch(),
            children=[
                ModelNode(status="in-progress", model=_triage(), children=[])
            ]
        ),
        percent_completion=0.2,
        annotations=[],
        overall_diagnosis_context=""
    ),
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="in-progress", model=_orch(),
            children=[
                ModelNode(
                    status="positive", model=_triage(),
                    children=[
                        ModelNode(status="in-progress", model=_pneumonia(), children=[])
                    ]
                )
            ]
        ),
        percent_completion=0.4,
        annotations=[],
        overall_diagnosis_context=""
    ),
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="in-progress", model=_orch(),
            children=[
                ModelNode(
                    status="positive", model=_triage(),
                    children=[
                        ModelNode(status="positive", model=_pneumonia(), children=[]),
                        ModelNode(status="in-progress", model=_tb(), children=[])
                    ]
                )
            ]
        ),
        percent_completion=0.7,
        annotations=[],
        overall_diagnosis_context=""
    ),
    lambda id: DiagnosisState(
        id=id, image_id=id,
        progress_tree=ModelNode(
            status="positive", model=_orch(),
            children=[
                ModelNode(
                    status="positive", model=_triage(),
                    children=[
                        ModelNode(status="positive", model=_pneumonia(), children=[]),
                        ModelNode(status="negative", model=_tb(), children=[])
                    ]
                )
            ]
        ),
        percent_completion=1.0,
        annotations=[
            Annotation(
                name="Left lower lobe consolidation",
                description="Homogeneous opacity with air bronchograms — bacterial pneumonia pattern",
                number=1,
                annotations=[Rectangle(x=55, y=220, width=120, height=100, color="#ef4444")],
                confidence="high"
            ),
            Annotation(
                name="Right perihilar haziness",
                description="Peribronchial thickening consistent with early pneumonic spread",
                number=2,
                annotations=[Rectangle(x=195, y=180, width=90, height=80, color="#f97316")],
                confidence="medium"
            )
        ],
        overall_diagnosis_context=(
            "HIGH CONFIDENCE PNEUMONIA POSITIVE (91.7%): Pneumonia Classifier detected "
            "left lower lobe consolidation with air bronchograms consistent with bacterial "
            "pneumonia. TB excluded (TBViT 2.8%). Recommend chest CT for extent assessment, "
            "sputum culture, CBC with differential, and empiric antibiotic therapy. "
            "Follow-up X-ray in 6 weeks to confirm resolution."
        )
    ),
]

# Seconds to wait before writing each stage (index matches stage index)
STAGE_DELAYS = [0, 1.5, 1.5, 1.5, 1.5]


# ── Background pipeline runner ─────────────────────────────────────────────────

def _run_pipeline(image_id: str, patient_index: int) -> None:
    db = FirebaseDatabase()
    stages = TB_STAGES if patient_index == 0 else PNEUMONIA_STAGES

    for stage_fn, delay in zip(stages, STAGE_DELAYS):
        time.sleep(delay)
        db.set_rl_data("diagnosis", stage_fn(image_id))


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/register")
def register(input: OrchestratorInput):
    global _call_counter
    with _counter_lock:
        patient_index = _call_counter % 2
        _call_counter += 1

    image_id = input.db_information.id

    threading.Thread(
        target=_run_pipeline,
        args=(image_id, patient_index),
        daemon=True
    ).start()

    return {"status": "accepted", "image_id": image_id}


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)
