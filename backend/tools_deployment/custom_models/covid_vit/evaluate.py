"""
Evaluation script for CovidViT.

Usage:
    python evaluate.py --model_dir ./saved_model --data_dir ./data/test
"""

import argparse

import torch
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder
from sklearn.metrics import classification_report, confusion_matrix

from model import load_model
from preprocessing import get_val_transforms


def evaluate(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = load_model(args.model_dir).to(device)
    model.eval()

    test_ds = ImageFolder(args.data_dir, transform=get_val_transforms())
    loader  = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False, num_workers=4)

    print(f"Evaluating on {len(test_ds)} samples | Classes: {test_ds.classes}")

    all_preds, all_labels = [], []
    with torch.no_grad():
        for pixel_values, labels in loader:
            pixel_values = pixel_values.to(device)
            logits = model(pixel_values)
            all_preds.extend(logits.argmax(1).cpu().tolist())
            all_labels.extend(labels.tolist())

    print("\n── Classification Report ─────────────────────────────────────────")
    print(classification_report(all_labels, all_preds, target_names=test_ds.classes))

    cm = confusion_matrix(all_labels, all_preds)
    print("── Confusion Matrix ──────────────────────────────────────────────")
    print(f"{'':20}", "  ".join(f"{c:>15}" for c in test_ds.classes))
    for i, row in enumerate(cm):
        print(f"{test_ds.classes[i]:20}", "  ".join(f"{v:>15}" for v in row))

    acc = sum(p == l for p, l in zip(all_preds, all_labels)) / len(all_labels)
    print(f"\nOverall accuracy: {acc:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir",  default="./saved_model")
    parser.add_argument("--data_dir",   default="./data/test")
    parser.add_argument("--batch_size", type=int, default=32)
    evaluate(parser.parse_args())
