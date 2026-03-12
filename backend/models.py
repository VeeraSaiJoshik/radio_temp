from pydantic import BaseModel
from typing import Optional
import numpy as np

class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int

class ImageInfo(BaseModel):
    patient_name: Optional[str] = None
    mrn: Optional[str] = None
    date_of_birth: Optional[str] = None
    scan_type: Optional[str] = None
    scan_date: Optional[str] = None
    body_part: Optional[str] = None
    accession_number: Optional[str] = None
    additional_info: Optional[str] = None

class CropResult(BaseModel):
    bounding_box: BoundingBox
    image_info: ImageInfo

class ImageEmbedding(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    image_id: str
    image_embedding: np.ndarray | None
    kp: int