import numpy as np
import cv2
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from backend.services.image_processor import are_images_similar


def make_image(seed: int, noise: float = 0.0) -> np.ndarray:
    """Create a reproducible grayscale test image with optional noise."""
    rng = np.random.default_rng(seed)
    img = np.zeros((200, 200), dtype=np.uint8)
    # Draw some distinct features so ORB has keypoints to work with
    for _ in range(20):
        x, y = rng.integers(10, 190, size=2)
        cv2.circle(img, (int(x), int(y)), 8, 255, -1)
    for _ in range(10):
        x1, y1 = rng.integers(10, 190, size=2)
        x2, y2 = rng.integers(10, 190, size=2)
        cv2.line(img, (int(x1), int(y1)), (int(x2), int(y2)), 200, 2)
    if noise > 0:
        noise_arr = (rng.random((200, 200)) * noise * 255).astype(np.uint8)
        img = cv2.add(img, noise_arr)
    return img


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def image_a():
    return make_image(seed=42)

@pytest.fixture
def image_a_noisy():
    """Same content as image_a but with slight noise — should still be similar."""
    return make_image(seed=42, noise=0.05)

@pytest.fixture
def image_b():
    """Completely different image."""
    return make_image(seed=99)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_identical_images_are_similar(image_a):
    similar = are_images_similar(image_a, image_a.copy())
    assert similar, "Identical images should be similar"


def test_near_identical_images_are_similar(image_a, image_a_noisy):
    similar = are_images_similar(image_a, image_a_noisy, threshold=0.10)
    assert similar, "Images with minor noise should still be similar"


def test_different_images_are_not_similar(image_a, image_b):
    similar = are_images_similar(image_a, image_b)
    assert not similar, "Completely different images should not be similar"


def test_higher_threshold_is_stricter(image_a, image_a_noisy):
    """A very high threshold should reject even near-identical images."""
    similar = are_images_similar(image_a, image_a_noisy, threshold=0.99)
    assert not similar, "threshold=0.99 should be too strict for noisy images"


def test_returns_bool(image_a, image_b):
    result = are_images_similar(image_a, image_b)
    assert isinstance(result, bool)
