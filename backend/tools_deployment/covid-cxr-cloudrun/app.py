import os, io
import numpy as np
from flask import Flask, request, jsonify
from PIL import Image
import tensorflow as tf

app = Flask(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "model")
MODEL_FILE = os.environ.get("MODEL_FILE", "inceptionV3_covid.keras")
MODEL_PATH = os.path.join(MODEL_DIR, MODEL_FILE)

# Class order as described in the model card dataset labels
LABELS = ["COVID", "Normal", "Lung-Opacity", "Viral Pneumonia"]

model = tf.keras.models.load_model(MODEL_PATH, compile=False)

@app.get("/health")
def health():
    return "ok", 200

def preprocess_image_bytes(img_bytes: bytes) -> np.ndarray:
    # Model expects 299x299 RGB, pixels normalized to [-1, 1]
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = img.resize((299, 299))
    arr = np.array(img, dtype=np.float32)

    # Scale 0..255 -> -1..1  (exactly matches "normalized to [-1,1]")
    arr = (arr / 127.5) - 1.0

    # Add batch dimension: (1, 299, 299, 3)
    return np.expand_dims(arr, axis=0)

@app.post("/predict")
def predict():
    if "file" not in request.files:
        return jsonify({"error": "Upload an image using multipart form-data with key 'file'"}), 400

    img_bytes = request.files["file"].read()
    x = preprocess_image_bytes(img_bytes)

    preds = model.predict(x, verbose=0)  # shape (1,4)
    probs = preds[0].astype(float)

    # Ensure probabilities sum to 1 (some models already output softmax)
    s = float(np.sum(probs))
    if s > 0:
        probs = probs / s

    scores = {LABELS[i]: float(probs[i]) for i in range(len(LABELS))}
    pred_idx = int(np.argmax(probs))

    return jsonify({
        "prediction": LABELS[pred_idx],
        "scores": scores
    })