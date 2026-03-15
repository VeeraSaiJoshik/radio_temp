"""
Knee OA tool — single hosted model.

Calls the knee-oa-cloudrun service (ONNX model).
No custom model for this condition (not a chest X-ray).

Classes: Normal, Doubtful, Mild, Moderate, Severe

Environment variables:
  KNEE_OA_HOSTED_URL — URL of the knee-oa-cloudrun service
"""

import os
from .base import BaseDiseaseTool

LABELS = ["Normal", "Doubtful", "Mild", "Moderate", "Severe"]


class KneeOATool(BaseDiseaseTool):
    HOSTED_URL = os.getenv(
        "KNEE_OA_HOSTED_URL",
        "https://knee-oa-classifier-1021943706658.us-central1.run.app"
    )
