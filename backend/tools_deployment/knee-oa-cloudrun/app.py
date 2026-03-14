import os, io
import numpy as np
from flask import Flask, request, jsonify
from PIL import Image
import onnxruntime as ort

app = Flask(__name__)

MODEL_PATH = os.environ.get("MODEL_PATH", "model/knee_osteoarthritis_model.onnx")

# Model outputs these 5 classes (per model card)
LABELS = ["Normal", "Doubtful", "Mild", "Moderate", "Severe"]  # :contentReference[oaicite:6]{index=6}

# Model card says input shape: (162, 300, 1) (H, W, C) :contentReference[oaicite:7]{index=7}
H, W = 162, 300

session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
input_name = session.get_inputs()[0].name
output_name = session.get_outputs()[0].name

@app.get("/health")
def health():
    return "ok", 200

def softmax(x: np.ndarray) -> np.ndarray:
    x = x - np.max(x)
    e = np.exp(x)
    return e / np.sum(e)

@app.post("/predict")
def predict():
    if "file" not in request.files:
        return jsonify({"error": "Upload an image using multipart form-data with key 'file'"}), 400

    img_bytes = request.files["file"].read()

    # Preprocessing per model card:
    # - grayscale
    # - resize to expected input
    # - normalize by 1/255 :contentReference[oaicite:8]{index=8}
    img = Image.open(io.BytesIO(img_bytes)).convert("L")
    # Pillow resize expects (width, height); model expects (H=162, W=300)
    img = img.resize((W, H))

    arr = np.array(img, dtype=np.float32) / 255.0  # normalization :contentReference[oaicite:9]{index=9}

    # Shape to (1, 162, 300, 1) as shown in model card usage :contentReference[oaicite:10]{index=10}
    x = arr.reshape(1, H, W, 1)

    logits = session.run([output_name], {input_name: x})[0]
    logits = np.array(logits).reshape(-1)
    probs = softmax(logits)

    scores = {LABELS[i]: float(probs[i]) for i in range(len(LABELS))}
    pred_idx = int(np.argmax(probs))

    return jsonify({
        "prediction": LABELS[pred_idx],
        "scores": scores
    })