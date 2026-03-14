import os, io
from flask import Flask, request, jsonify
from PIL import Image
import torch
from transformers import AutoImageProcessor, AutoModelForImageClassification

app = Flask(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "model")

processor = AutoImageProcessor.from_pretrained(MODEL_DIR)
model = AutoModelForImageClassification.from_pretrained(MODEL_DIR)
model.eval()

@app.get("/health")
def health():
    return "ok", 200

@app.post("/predict")
def predict():
    if "file" not in request.files:
        return jsonify({"error": "Upload an image using multipart form-data with key 'file'"}), 400

    img_bytes = request.files["file"].read()
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    # This handles resizing/normalization according to preprocessor_config.json
    inputs = processor(images=img, return_tensors="pt")

    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=1)[0]

    probs_list = probs.cpu().numpy().tolist()

    # Uses label names from config.json if present
    id2label = getattr(model.config, "id2label", None) or {i: f"class_{i}" for i in range(len(probs_list))}
    scores = {id2label[i]: float(probs_list[i]) for i in range(len(probs_list))}

    best_idx = int(torch.argmax(probs).item())
    return jsonify({
        "prediction": id2label[best_idx],
        "scores": scores
    })