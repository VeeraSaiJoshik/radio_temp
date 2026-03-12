import numpy as np
import cv2
import pytest

from services.image_processor import are_images_similar, get_orb_descriptor, make_image




@pytest.fixture
def image_a():
    return make_image(seed=42)

@pytest.fixture
def image_a_noisy():
    return make_image(seed=42, noise=0.05)

@pytest.fixture
def image_b():
    return make_image(seed=99)


def test_identical_images_are_similar(image_a):
    assert are_images_similar(image_a, image_a.copy())

def test_near_identical_images_are_similar(image_a, image_a_noisy):
    assert are_images_similar(image_a, image_a_noisy, threshold=0.10)

def test_different_images_are_not_similar(image_a, image_b):
    assert not are_images_similar(image_a, image_b)

def test_higher_threshold_is_stricter(image_a, image_a_noisy):
    assert not are_images_similar(image_a, image_a_noisy, threshold=0.99)

def test_returns_bool(image_a, image_b):
    assert isinstance(are_images_similar(image_a, image_b), bool)