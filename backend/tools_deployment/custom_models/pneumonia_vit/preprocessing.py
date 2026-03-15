"""
Preprocessing for PneumoniaViT.
Matches google/vit-base-patch16-224 expected input:
  - Resize to 224x224
  - Normalize with ImageNet mean/std
Augmentations applied during training only.
"""

from torchvision import transforms
from transformers import ViTImageProcessor

# Standard ViT normalization (matches backbone pretraining)
VIT_MEAN = [0.5, 0.5, 0.5]
VIT_STD  = [0.5, 0.5, 0.5]

# Use HuggingFace processor for consistent preprocessing with the backbone
processor = ViTImageProcessor.from_pretrained("google/vit-base-patch16-224")


def get_train_transforms() -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.2, contrast=0.2),
        transforms.ToTensor(),
        transforms.Normalize(mean=VIT_MEAN, std=VIT_STD),
    ])


def get_val_transforms() -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=VIT_MEAN, std=VIT_STD),
    ])


def preprocess_pil(pil_image):
    """
    Preprocess a single PIL image for inference.
    Returns a (1, 3, 224, 224) float tensor.
    """
    import torch
    transform = get_val_transforms()
    img = pil_image.convert("RGB")
    return transform(img).unsqueeze(0)
