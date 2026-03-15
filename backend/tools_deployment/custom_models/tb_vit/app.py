"""
Cloud Run serving app for TBViTCustom model.
"""

import io, os
from flask import Flask, request, jsonify
from PIL import Image
import torch

from model import load_model, LABELS
from preprocessing import preprocess_pil

app = Flask(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "saved_model")
device = torch.device("cpu")

model = load_model(MODEL_DIR).to(device)
model.eval()


@app.get("/health")
def health():
    return "ok", 200


@app.post("/predict")
def predict():
    if "file" not in request.files:
        return jsonify({"error": "Send image as multipart form-data with key 'file'"}), 400

    img_bytes = request.files["file"].read()
    pil_image = Image.open(io.BytesIO(img_bytes))

    pixel_values = preprocess_pil(pil_image).to(device)

    with torch.no_grad():
        logits = model(pixel_values)
        probs = torch.softmax(logits, dim=1)[0].cpu().tolist()

    scores = {LABELS[i]: round(probs[i], 4) for i in range(len(LABELS))}
    best_idx = int(torch.tensor(probs).argmax().item())

    return jsonify({
        "prediction": LABELS[best_idx],
        "scores": scores,
        "confidence": round(probs[best_idx], 4),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
