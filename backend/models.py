from datetime import datetime

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Literal
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

class DBRecord(BaseModel):
    id: str

class PatientContext(DBRecord):
    """
    Structured patient data extracted upstream via OCR + VLM.
    All fields are optional — fill what OCR could confidently read.
    """

    # --- Identity ---
    patient_id: Optional[str] = Field(None, description="MRN or anonymised ID from OCR")
    age: Optional[int] = Field(None, ge=0, le=130)
    sex: Optional[Literal["M", "F", "Other"]] = None
    weight_kg: Optional[float] = Field(None, gt=0)
    height_cm: Optional[float] = Field(None, gt=0)

    # --- Scan metadata ---
    scan_date: Optional[str] = None
    ordering_physician: Optional[str] = None
    modality_hint: Optional[str] = Field(
        None,
        description=(
            "Modality read from label/OCR, e.g. 'CT', 'MRI', 'X-Ray'. "
            "Triage agent confirms from the image itself."
        ),
    )
    scan_reason: Optional[str] = Field(
        None,
        description="Free-text reason for the scan, e.g. 'chest pain, rule out PE'",
    )

    # --- Symptoms ---
    chief_complaint: Optional[str] = None
    symptoms: Optional[List[str]] = Field(
        None, description="e.g. ['dyspnea', 'fever', 'tachycardia']"
    )
    symptom_duration_days: Optional[int] = Field(None, ge=0)

    # --- Medical history ---
    relevant_history: Optional[List[str]] = Field(
        None, description="e.g. ['T2DM', 'hypertension', 'recent knee surgery']"
    )
    smoking_status: Optional[Literal["never", "former", "current"]] = None
    family_history: Optional[List[str]] = Field(
        None, description="e.g. ['lung cancer', 'coronary artery disease']"
    )
    current_medications: Optional[List[str]] = None
    allergies: Optional[List[str]] = None

    # --- Prior imaging / labs ---
    prior_imaging_summary: Optional[str] = Field(
        None,
        description=(
            "Free-text summary or excerpt from a prior radiology report. "
            "RadGraph-XL can pre-process this upstream."
        ),
    )
    relevant_labs: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Key lab values as a flat dict, "
            "e.g. {'D-dimer': 2.4, 'CRP': 45, 'HbA1c': 7.2}"
        ),
    )

    # --- Urgency / flags ---
    is_emergency: bool = Field(
        False,
        description="Set True if upstream triage flagged this as STAT/emergency.",
    )
    raw_ocr_text: Optional[str] = Field(
        None,
        description=(
            "Full raw OCR dump from the radiology screen as a fallback. "
            "Agents can mine this if structured fields are sparse."
        ),
    )

class ImageDataDB(DBRecord):
    image_id: str
    user_id: str
    image_location: str
    image_type: str
    image_date: datetime
    metadata: Optional[Dict[str, Any]] = None

    image_features: str

class Image(BaseModel):
    image: int