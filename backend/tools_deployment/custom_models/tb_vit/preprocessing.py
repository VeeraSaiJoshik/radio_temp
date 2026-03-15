"""
Preprocessing for TBViTCustom.

Mirrors the existing TBViT model preprocessing pipeline:
  1. CLAHE (contrast-limited adaptive histogram equalization) — enhances subtle lung markings
  2. Gaussian blur — reduces noise
  3. Resize to 224x224
  4. Convert back to RGB for ViT (3-channel input expected)
  5. Normalize per-instance (mean/std of the image itself)

This is applied to ALL splits (train/val/test) as base preprocessing.
Spatial augmentations are added on top for training only.
"""

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms


def _clahe_gaussian(pil_image: Image.Image, img_size: int = 224) -> np.ndarray:
    """Apply CLAHE + Gaussian blur, return (3, H, W) float32 numpy array."""
    image = np.array(pil_image.convert("RGB"))
    gray  = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)
    gray  = cv2.GaussianBlur(gray, (5, 5), 0)
    gray  = cv2.resize(gray, (img_size, img_size), interpolation=cv2.INTER_LINEAR)

    rgb   = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)           # (H, W, 3)
    chw   = np.moveaxis(rgb, -1, 0).astype(np.float32)       # (3, H, W)
    chw   = (chw - chw.mean()) / (chw.std() + 1e-8)          # per-instance normalization
    return chw


class CLAHETransform:
    """Torchvision-compatible transform wrapper for CLAHE preprocessing."""
    def __init__(self, img_size: int = 224):
        self.img_size = img_size

    def __call__(self, pil_image: Image.Image) -> torch.Tensor:
        arr = _clahe_gaussian(pil_image, self.img_size)
        return torch.from_numpy(arr)


def get_train_transforms() -> transforms.Compose:
    return transforms.Compose([
        CLAHETransform(224),
        # Spatial augmentations (applied after CLAHE to the tensor)
        transforms.RandomHorizontalFlip(),
        transforms.RandomAffine(degrees=10, translate=(0.05, 0.05)),
    ])


def get_val_transforms() -> transforms.Compose:
    return transforms.Compose([
        CLAHETransform(224),
    ])


def preprocess_pil(pil_image: Image.Image) -> torch.Tensor:
    """Preprocess a single PIL image for inference. Returns (1, 3, 224, 224)."""
    arr = _clahe_gaussian(pil_image, 224)
    return torch.from_numpy(arr).unsqueeze(0)
