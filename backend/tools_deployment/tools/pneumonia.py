"""
Pneumonia tool — dual-model ensemble.

Calls:
  1. Hosted ViT model (pneumonia-cloudrun, HuggingFace ViT fine-tuned)
  2. Custom ViT+MLP model (pneumonia_vit, trained in-house)
Averages softmax scores → final prediction.

Classes: NORMAL, PNEUMONIA

Environment variables:
  PNEUMONIA_HOSTED_URL  — URL of the pneumonia-cloudrun service
  PNEUMONIA_CUSTOM_URL  — URL of the pneumonia_vit custom model service
"""

import os
from .base import BaseDiseaseTool

LABELS = ["NORMAL", "PNEUMONIA"]


class PneumoniaTool(BaseDiseaseTool):
    HOSTED_URL = os.getenv(
        "PNEUMONIA_HOSTED_URL",
        "https://pneumonia-classifier-1021943706658.us-central1.run.app"
    )
    CUSTOM_URL = os.getenv(
        "PNEUMONIA_CUSTOM_URL",
        "https://pneumonia-vit-classifier-1021943706658.us-central1.run.app"
    )

    def predict(self, image_bytes: bytes) -> dict:
        hosted = self._call_endpoint(self.HOSTED_URL, image_bytes)
        custom = self._call_endpoint(self.CUSTOM_URL, image_bytes)

        if hosted and custom:
            scores = self._average_scores(hosted["scores"], custom["scores"])
        elif hosted:
            scores = hosted["scores"]
        elif custom:
            scores = custom["scores"]
        else:
            return {"prediction": "error", "scores": {}, "confidence": 0.0}

        return self._build_result(scores)
