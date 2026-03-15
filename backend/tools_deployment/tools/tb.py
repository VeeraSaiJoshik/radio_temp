"""
TB tool — dual-model ensemble.

Calls:
  1. Hosted TBViT model (tb-cloudrun, custom transformer trained in-house)
  2. Custom ViT+MLP model (tb_vit, google/vit-base-patch16-224 backbone)
Averages softmax scores → final prediction.

Classes: Normal, Tuberculosis

Environment variables:
  TB_HOSTED_URL  — URL of the tb-cloudrun service
  TB_CUSTOM_URL  — URL of the tb_vit custom model service
"""

import os
from .base import BaseDiseaseTool

LABELS = ["Normal", "Tuberculosis"]


class TBTool(BaseDiseaseTool):
    HOSTED_URL = os.getenv(
        "TB_HOSTED_URL",
        "https://tb-xray-classifier-1021943706658.us-central1.run.app"
    )
    CUSTOM_URL = os.getenv(
        "TB_CUSTOM_URL",
        "https://tb-vit-classifier-1021943706658.us-central1.run.app"
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
