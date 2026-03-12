from pydantic import BaseModel
import numpy as np

class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int

class ImageEmbedding(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    image_id: str
    image_embedding: np.ndarray | None
    kp: int

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ImageEmbedding):
            return False
        if self.image_id != other.image_id or self.kp != other.kp:
            return False
        if self.image_embedding is None and other.image_embedding is None:
            return True
        if self.image_embedding is None or other.image_embedding is None:
            return False
        return np.array_equal(self.image_embedding, other.image_embedding)