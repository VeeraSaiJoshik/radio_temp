"""
Training script for PneumoniaViT.

Expected dataset layout (ImageFolder format):
    data/
      train/
        NORMAL/    *.jpg ...
        PNEUMONIA/ *.jpg ...
      val/
        NORMAL/
        PNEUMONIA/

Usage:
    python train.py --data_dir ./data --output_dir ./saved_model --epochs 20 --freeze_epochs 5
"""

import argparse
import os

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

from model import PneumoniaViT, save_model, LABELS
from preprocessing import get_train_transforms, get_val_transforms


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    train_ds = ImageFolder(os.path.join(args.data_dir, "train"), transform=get_train_transforms())
    val_ds   = ImageFolder(os.path.join(args.data_dir, "val"),   transform=get_val_transforms())

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,  num_workers=4, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size, shuffle=False, num_workers=4, pin_memory=True)

    print(f"Train: {len(train_ds)} samples | Val: {len(val_ds)} samples")
    print(f"Classes: {train_ds.classes}")

    model = PneumoniaViT().to(device)

    # Phase 1: freeze backbone, train head only
    if args.freeze_epochs > 0:
        model.freeze_backbone()
        print(f"Backbone frozen for first {args.freeze_epochs} epochs")

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=args.lr, weight_decay=1e-4
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_val_acc = 0.0

    for epoch in range(1, args.epochs + 1):
        # Unfreeze backbone after freeze_epochs
        if epoch == args.freeze_epochs + 1:
            model.unfreeze_backbone()
            optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr * 0.1, weight_decay=1e-4)
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs - epoch)
            print("Backbone unfrozen — full fine-tuning")

        # ── Train ──────────────────────────────────────────────────────────────
        model.train()
        train_loss, train_correct = 0.0, 0
        for pixel_values, labels in train_loader:
            pixel_values, labels = pixel_values.to(device), labels.to(device)
            optimizer.zero_grad()
            logits = model(pixel_values)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(labels)
            train_correct += (logits.argmax(1) == labels).sum().item()

        # ── Validate ───────────────────────────────────────────────────────────
        model.eval()
        val_loss, val_correct = 0.0, 0
        with torch.no_grad():
            for pixel_values, labels in val_loader:
                pixel_values, labels = pixel_values.to(device), labels.to(device)
                logits = model(pixel_values)
                val_loss += criterion(logits, labels).item() * len(labels)
                val_correct += (logits.argmax(1) == labels).sum().item()

        scheduler.step()

        train_acc = train_correct / len(train_ds)
        val_acc   = val_correct   / len(val_ds)
        print(
            f"Epoch {epoch:3d}/{args.epochs} | "
            f"train loss {train_loss/len(train_ds):.4f} acc {train_acc:.4f} | "
            f"val loss {val_loss/len(val_ds):.4f} acc {val_acc:.4f}"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            save_model(model, args.output_dir)
            print(f"  ✓ Saved best model (val_acc={val_acc:.4f})")

    print(f"\nTraining complete. Best val accuracy: {best_val_acc:.4f}")
    print(f"Model saved to: {args.output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir",      default="./data")
    parser.add_argument("--output_dir",    default="./saved_model")
    parser.add_argument("--epochs",        type=int,   default=20)
    parser.add_argument("--batch_size",    type=int,   default=32)
    parser.add_argument("--lr",            type=float, default=1e-4)
    parser.add_argument("--freeze_epochs", type=int,   default=5,
                        help="Epochs to freeze ViT backbone before full fine-tuning")
    train(parser.parse_args())
