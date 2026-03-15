"""
TB ViT Classifier
Pipeline: Image → CLAHE+Gaussian → ViT encoder (google/vit-base-patch16-224) → CLS token (768) → MLP head → 2 classes
Classes: Normal (0), Tuberculosis (1)

Preprocessing mirrors the existing TBViT model (CLAHE + Gaussian blur) for consistency.
"""

import torch
import torch.nn as nn
from transformers import ViTModel

LABELS = ["Normal", "Tuberculosis"]
NUM_CLASSES = 2
VIT_BACKBONE = "google/vit-base-patch16-224"


class TBViTCustom(nn.Module):
    def __init__(self, num_classes: int = NUM_CLASSES, mlp_hidden: int = 256, dropout: float = 0.3):
        super().__init__()
        self.vit = ViTModel.from_pretrained(VIT_BACKBONE)
        self.mlp = nn.Sequential(
            nn.LayerNorm(768),
            nn.Linear(768, mlp_hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(mlp_hidden, num_classes),
        )

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        outputs = self.vit(pixel_values=pixel_values)
        cls_embedding = outputs.last_hidden_state[:, 0]  # CLS token: (B, 768)
        return self.mlp(cls_embedding)

    def freeze_backbone(self):
        for param in self.vit.parameters():
            param.requires_grad = False

    def unfreeze_backbone(self):
        for param in self.vit.parameters():
            param.requires_grad = True


def save_model(model: TBViTCustom, output_dir: str):
    import os, json
    os.makedirs(output_dir, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(output_dir, "pytorch_model.bin"))
    config = {
        "model_type": "vit_mlp",
        "backbone": VIT_BACKBONE,
        "num_classes": NUM_CLASSES,
        "labels": LABELS,
        "mlp_hidden": 256,
    }
    with open(os.path.join(output_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)


def load_model(model_dir: str) -> TBViTCustom:
    import os, json
    with open(os.path.join(model_dir, "config.json")) as f:
        config = json.load(f)
    model = TBViTCustom(num_classes=config["num_classes"], mlp_hidden=config.get("mlp_hidden", 256))
    state = torch.load(os.path.join(model_dir, "pytorch_model.bin"), map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()
    return model
