"""
Base class for all disease tools.
Handles HTTP calls to Cloud Run endpoints and probability averaging.
"""

import requests


class BaseDiseaseTool:
    HOSTED_URL: str = ""  # Override in subclass

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _call_endpoint(self, url: str, image_bytes: bytes) -> dict | None:
        """POST image bytes to {url}/predict. Returns parsed JSON or None on failure."""
        try:
            resp = requests.post(
                f"{url}/predict",
                files={"file": ("image.jpg", image_bytes, "image/jpeg")},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Warning: call to {url} failed: {e}")
            return None

    # ── Score utilities ───────────────────────────────────────────────────────

    def _average_scores(self, a: dict, b: dict) -> dict:
        """
        Average two score dicts by label name (case-insensitive matching).
        Uses label names from `a` as canonical keys.
        """
        b_lower = {k.lower(): v for k, v in b.items()}
        return {label: (val + b_lower.get(label.lower(), 0.0)) / 2 for label, val in a.items()}

    def _normalize_scores(self, scores: dict) -> dict:
        total = sum(scores.values())
        if total == 0:
            return scores
        return {k: round(v / total, 4) for k, v in scores.items()}

    def _build_result(self, scores: dict) -> dict:
        scores = self._normalize_scores(scores)
        best = max(scores, key=scores.get)
        return {
            "prediction": best,
            "scores": scores,
            "confidence": scores[best],
        }

    # ── Public interface ──────────────────────────────────────────────────────

    def predict(self, image_bytes: bytes) -> dict:
        """
        Run prediction on raw image bytes.
        Returns: {"prediction": str, "scores": dict[str, float], "confidence": float}
        """
        result = self._call_endpoint(self.HOSTED_URL, image_bytes)
        if result is None:
            return {"prediction": "error", "scores": {}, "confidence": 0.0}
        return self._build_result(result["scores"])
