"""
Alzheimers tool — single hosted model.

Calls the alzheimers-cloudrun service (HuggingFace ViT fine-tuned).
No custom model for this condition (not a chest X-ray).

Classes: Mild_Demented, Moderate_Demented, Non_Demented, Very_Mild_Demented

Environment variables:
  ALZHEIMERS_HOSTED_URL — URL of the alzheimers-cloudrun service
"""

import os
from .base import BaseDiseaseTool

LABELS = ["Mild_Demented", "Moderate_Demented", "Non_Demented", "Very_Mild_Demented"]


class AlzheimersTool(BaseDiseaseTool):
    HOSTED_URL = os.getenv(
        "ALZHEIMERS_HOSTED_URL",
        "https://alzheimers-classifier-1021943706658.us-central1.run.app"
    )
