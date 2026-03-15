"""
Preprocessing for CovidViT.
Standard ViT preprocessing (resize 224x224, normalize with ViT mean/std).
Training adds standard CXR augmentations.
"""

import torch
from PIL import Image
from torchvision import transforms

VIT_MEAN = [0.5, 0.5, 0.5]
VIT_STD  = [0.5, 0.5, 0.5]


def get_train_transforms() -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.15, contrast=0.15),
        transforms.ToTensor(),
        transforms.Normalize(mean=VIT_MEAN, std=VIT_STD),
    ])


def get_val_transforms() -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=VIT_MEAN, std=VIT_STD),
    ])


def preprocess_pil(pil_image: Image.Image) -> torch.Tensor:
    """Preprocess a single PIL image for inference. Returns (1, 3, 224, 224)."""
    transform = get_val_transforms()
    return transform(pil_image.convert("RGB")).unsqueeze(0)
