import sys
import os
import traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.testing_utils import image_path_to_base64
from routes.image_processor import get_image_id, GetImageIDInput
from services.database import FirebaseDatabase
from models import (
    Annotation, Circle, DiagnosisState, MedicalModel, ModelNode, Rectangle
)

IMAGE_PATH = "./images/medical_image_2.png"

# ── Step 1: Process the image through get_image_id ───────────────────────────
print("Processing medical_image_2.png through get_image_id...")
image_b64 = image_path_to_base64(IMAGE_PATH)
try:
    result = get_image_id(GetImageIDInput(image_base64=image_b64))
    print("get_image_id result:", result)
except Exception as e:
    # Orchestrator (localhost:8080) may not be running during seeding — that's expected.
    # Firebase writes for images/diagnosis/raw_image complete before the orchestrator call.
    traceback.print_exc()
    print(f"Warning: get_image_id raised an exception (likely orchestrator offline): {e}")

# ── Step 2: Seed a DiagnosisState with static dummy data ─────────────────────
print("\nSeeding dummy DiagnosisState...")

db = FirebaseDatabase()

SEED_ID = "seed-ct-chest-001"

dummy_diagnosis = DiagnosisState(
    id=SEED_ID,
    image_id=SEED_ID,
    percent_completion=100.0,
    overall_diagnosis_context=(
        "CT chest with contrast performed for evaluation of chest pain and shortness of breath. "
        "Findings are consistent with a moderate right-sided pulmonary embolism in the right lower "
        "lobe pulmonary artery. Mild cardiomegaly noted. No pneumothorax. No pleural effusion. "
        "Lung parenchyma otherwise unremarkable. Recommend anticoagulation therapy and follow-up."
    ),
    progress_tree=ModelNode(
        status="positive",
        model=MedicalModel(
            name="Orchestrator",
            provider="Stanford AI Lab",
            description="Routes the scan to appropriate specialist models based on modality and anatomy."
        ),
        children=[
            ModelNode(
                status="positive",
                model=MedicalModel(
                    name="PE Detector",
                    provider="NVIDIA BioMedical AI",
                    description="Detects pulmonary embolism from CT pulmonary angiography scans."
                ),
                children=[]
            ),
            ModelNode(
                status="negative",
                model=MedicalModel(
                    name="Lung Nodule Detector",
                    provider="Google Health AI",
                    description="Identifies and characterises pulmonary nodules, flagging malignancy risk."
                ),
                children=[]
            ),
            ModelNode(
                status="positive",
                model=MedicalModel(
                    name="Cardiomegaly Classifier",
                    provider="Stanford AI Lab",
                    description="Measures cardiothoracic ratio and classifies degree of cardiomegaly."
                ),
                children=[]
            ),
            ModelNode(
                status="negative",
                model=MedicalModel(
                    name="Pleural Effusion Detector",
                    provider="Rad AI",
                    description="Segments and quantifies pleural effusions from chest CT."
                ),
                children=[]
            )
        ]
    ),
    annotations=[
        Annotation(
            name="Pulmonary Embolism",
            description=(
                "Filling defect identified in the right lower lobe pulmonary artery. "
                "Consistent with moderate acute pulmonary embolism."
            ),
            number=1,
            confidence="high",
            annotations=[
                Rectangle(x=312.0, y=278.0, width=48.0, height=36.0, color="#FF4444")
            ]
        ),
        Annotation(
            name="Cardiomegaly",
            description=(
                "Cardiothoracic ratio measured at 0.58. Mildly enlarged cardiac silhouette. "
                "No pericardial effusion identified."
            ),
            number=2,
            confidence="medium",
            annotations=[
                Rectangle(x=198.0, y=210.0, width=224.0, height=180.0, color="#FFB344"),
                Circle(x=310.0, y=300.0, radius=112.0, color="#FFB34466")
            ]
        )
    ]
)

try:
    db.set_rl_data("diagnosis", dummy_diagnosis)
    print(f"Dummy DiagnosisState written to diagnosis/{SEED_ID}")
except Exception as e:
    traceback.print_exc()
    print(f"Error: Firebase write to diagnosis/{SEED_ID} failed: {e}")
    print("Note: The Firebase service account certificate may need to be regenerated in the Firebase/Google Cloud Console.")
print("\nSeeding complete.")
