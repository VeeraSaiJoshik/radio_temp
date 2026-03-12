import random
import string
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2
import base64

from models import BoundingBox, ImageEmbedding

def are_images_similar(
    des1: ImageEmbedding, 
    des2: ImageEmbedding,
  ) -> tuple[bool, float]:
      if des1.image_embedding is None or des2.image_embedding is None:
          return False

      matcher = cv2.BFMatcher(cv2.NORM_L2)
      raw_matches = matcher.knnMatch(des1.image_embedding, des2.image_embedding, k=2)

      # Lowe's ratio test — keep only unambiguous matches
      good_matches = [m for m, n in raw_matches if m.distance < 0.75 * n.distance]

      score = len(good_matches) / min(des1.kp, des2.kp)
      return score >= 0.15

def get_orb_descriptor(
    image: np.ndarray | str,
    nfeatures: int = 1000,
    id: str = ""
) -> ImageEmbedding:
    if isinstance(image, str):
        gray = cv2.imread(image, cv2.IMREAD_GRAYSCALE)
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()

    if gray is None:
        raise ValueError("Could not load image.")

    orb = cv2.ORB_create(nfeatures=nfeatures)
    kp, descriptors = orb.detectAndCompute(gray, None)

    if descriptors is None or len(descriptors) == 0:
        return None

    random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=2))

    return ImageEmbedding(
        image_id=random_string if id == "" else id,
        image_embedding=descriptors.astype(np.float32),
        kp=len(kp)
    )

def crop_image(img: cv2.Mat, bounding_box: BoundingBox) -> cv2.Mat:
    return img[bounding_box.y:bounding_box.y + bounding_box.height, bounding_box.x:bounding_box.x + bounding_box.width]

def base64_to_image(base64_string: str):
    # decode base64 string to bytes
    image_bytes = base64.b64decode(base64_string)

    # convert bytes to numpy array
    np_arr = np.frombuffer(image_bytes, np.uint8)

    # decode image
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    return img

def make_image(seed: int, noise: float = 0.0) -> np.ndarray:
    """Create a reproducible grayscale test image with optional noise."""
    rng = np.random.default_rng(seed)
    img = np.zeros((200, 200), dtype=np.uint8)
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


if __name__ == "__main__":
    test_images = [
        get_orb_descriptor(cv2.imread("images/" + img, cv2.IMREAD_GRAYSCALE), id=img)
        for img in os.listdir("./images/")
    ]

    for i in test_images: 
        for j in test_images: 
            print(f"img {i.image_id} + img {j.image_id} : {are_images_similar(i, j) == (j.image_id == i.image_id)}")