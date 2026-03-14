import os, io, json
from flask import Flask, request, jsonify
from PIL import Image
import torch
import torch.nn as nn
import cv2
import numpy as np

app = Flask(__name__)

MODEL_PATH = os.path.join("model", "pytorch_model.bin")
CONFIG_PATH = os.path.join("model", "config.json")

with open(CONFIG_PATH) as f:
    config = json.load(f)

class_names = config.get("class_names", ["Normal", "Tuberculosis"])
img_size = config.get("input_size", 224)
device = torch.device("cpu")


class TransformerBlock(nn.Module):
    def __init__(self, dim=512, num_heads=8, mlp_dim=2048):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.norm2 = nn.LayerNorm(dim)
        self.attention = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.mlp = nn.Sequential(
            nn.Linear(dim, mlp_dim),  # index 0
            nn.GELU(),                 # index 1
            nn.Dropout(0.1),           # index 2
            nn.Linear(mlp_dim, dim),  # index 3
        )

    def forward(self, x):
        normed = self.norm1(x)
        attn_out, _ = self.attention(normed, normed, normed)
        x = x + attn_out
        x = x + self.mlp(self.norm2(x))
        return x


class TBViT(nn.Module):
    def __init__(self):
        super().__init__()
        self.linear = nn.Linear(768, 512)   # patch projection: 16*16*3=768 -> 512
        self.embedding = nn.Parameter(torch.zeros(196, 512))  # positional embedding
        self.blocks = nn.ModuleList([TransformerBlock() for _ in range(6)])
        self.ln_out = nn.LayerNorm(512)
        self.classifier = nn.Sequential(
            nn.Dropout(0.5),       # index 0
            nn.Linear(512, 256),   # index 1
            nn.ReLU(),             # index 2
            nn.Dropout(0.3),       # index 3
            nn.Linear(256, 1),     # index 4
        )

    def forward(self, x):
        B, C, H, W = x.shape
        p = 16
        x = x.unfold(2, p, p).unfold(3, p, p)           # B, C, 14, 14, 16, 16
        x = x.contiguous().view(B, C, -1, p * p)         # B, C, 196, 256
        x = x.permute(0, 2, 1, 3).contiguous().view(B, 196, C * p * p)  # B, 196, 768
        x = self.linear(x)                               # B, 196, 512
        x = x + self.embedding                           # B, 196, 512
        for block in self.blocks:
            x = block(x)
        x = self.ln_out(x)
        x = x.mean(dim=1)                                # B, 512
        x = self.classifier(x)
        return x


model = TBViT()
state_dict = torch.load(MODEL_PATH, map_location=device, weights_only=True)
model.load_state_dict(state_dict)
model.eval()


def preprocess(pil_image):
    image = np.array(pil_image.convert("RGB"))
    image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    image = clahe.apply(image)
    image = cv2.GaussianBlur(image, (5, 5), 0)
    image = cv2.resize(image, (img_size, img_size), interpolation=cv2.INTER_LINEAR)
    image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    image = np.moveaxis(image, -1, 0).astype(np.float32)
    image = (image - image.mean()) / (image.std() + 1e-8)
    return torch.tensor(image).unsqueeze(0).to(device)


@app.post("/predict")
def predict():
    if "file" not in request.files:
        return jsonify({"error": "Send an image as multipart form-data with key 'file'"}), 400

    img_bytes = request.files["file"].read()
    pil_image = Image.open(io.BytesIO(img_bytes))
    tensor = preprocess(pil_image)

    with torch.no_grad():
        output = model(tensor)
        if len(output.shape) > 1:
            output = output.squeeze(-1)
        prob = torch.sigmoid(output).item()

    class_id = 1 if prob > 0.5 else 0
    confidence = prob if class_id == 1 else 1 - prob

    return jsonify({
        "prediction": class_names[class_id],
        "confidence": round(float(confidence), 4),
        "scores": {
            class_names[0]: round(float(1 - prob), 4),
            class_names[1]: round(float(prob), 4)
        }
    })


@app.get("/health")
def health():
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
