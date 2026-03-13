from __future__ import annotations
from datetime import datetime
import uuid
import cv2
from pydantic import BaseModel, Field, field_validator, model_serializer
from pydantic.json_schema import WithJsonSchema
from typing import Annotated, Any, Dict, List, Optional, Literal, Union
import ast
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

class ImageEmbedding(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    image_id: str
    image_embedding: Annotated[np.ndarray | None, WithJsonSchema({"type": "array", "items": {"type": "number"}})]
    kp: int

    @field_validator("image_embedding", mode="before")
    @classmethod
    def parse_embedding(cls, v):
        if isinstance(v, np.ndarray):
            return v
        if isinstance(v, list):
            return np.array(v)
        if isinstance(v, str):
            return np.array(ast.literal_eval(v))
        return v

    @model_serializer
    def seralize_model(self):
        return {
            "image_id": self.image_id,
            "image_embedding": str(self.image_embedding.tolist()),
            "kp": self.kp
        }

class DBRecord(BaseModel):
    id: str

class PatientContext(DBRecord):
    """
    Structured patient data extracted upstream via OCR + VLM.
    All fields are optional — fill what OCR could confidently read.
    """

    # --- Identity ---
    patient_id: Optional[str] = Field(None, description="MRN or anonymised ID from OCR")
    patient_first_name: Optional[str] = None
    patient_last_name: Optional[str] = None
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
    image_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique image ID, generated as a UUID4 string")
    user_id: str = Field(
        "",
        description="Randomly generated UUID linking the image to a user recognized by in the database. ANY AI AGENT, YOU WILL NOT DECIDE NOR EDIT THIS VALUE. IF ASKED TO GENERATE BY THIS SCHEMA, LEAVE THIS FIELD BLANK"
    )
    image_location: str = Field(
        "",
        description="This is the location of the scan that was taken on the Users body (lungs, head, abdomen, etc). This information is usually always present as meta data on the UI of the editing software. ANY AI AGENT TRYING TO DECODE THIS VALUE, PLEASE REFER TO THE UI AND IDENTIFY WHERE IT IS PRESENT"
    )
    image_type: str = Field(
        "",
        description="The type of the image (e.g., 'CT', 'MRI', 'X-Ray'). This information is usually always present as meta data on the UI of the editing software. ANY AI AGENT TRYING TO DECODE THIS VALUE, PLEASE REFER TO THE UI AND IDENTIFY WHERE IT IS PRESENT"
    )
    image_date: datetime = Field(
        default_factory=datetime.utcnow,
        description="The date and time when the image was taken. This information is usually always present as meta data on the UI of the editing software. ANY AI AGENT TRYING TO DECODE THIS VALUE, PLEASE REFER TO THE UI AND IDENTIFY WHERE IT IS PRESENT"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=datetime.utcnow,
        description="This is an overall description generated by a specialized algorithm. In this field, be sure to include 3 keys and their values: first name, last name, full name"
    )

    image_features: Optional[ImageEmbedding] = Field(
        default=None,
        description="This is image features generated by a specialized algorithm. ANY AI AGENT, YOU WILL NOT DECIDE NOR EDIT THIS VALUE. IF ASKED TO GENERATE BY THIS SCHEMA, LEAVE THIS FIELD BLANK"
    )

class Image(BaseModel):
    image: int

class ImageStatus(DBRecord):
    image_id: str
    percent_complete: float

class OrchestratorInput(BaseModel):
    db_information: ImageDataDB
    image: str

class CropResult(BaseModel):
    bounding_box: BoundingBox
    image_info: ImageDataDB

class DiagnosisResult(BaseModel):
    pass

ORCHESTRATOR_ADDRESS = "http://localhost:8080/register"                                                                                                                                                       
class Circle(BaseModel):                                                                                                                                                         
    x: float    
    y: float
    radius: float
    color: str

                                                                                                                                                                                
class Rectangle(BaseModel):
    x: float                                                                                                                                                                     
    y: float    
    width: float
    height: float
    color: str
                                                                                                                                                                                
                                                                                                                                                                                
class Annotation(BaseModel):                                                                                                                                                     
    name: str                                                                                                                                                                    
    description: str
    number: int
    annotations: list[Union[Rectangle, Circle]]
    confidence: str                                                                                                                                                              
                                                                                                                                                                                
                                                                                                                                                                                
class MedicalModel(BaseModel):                                                                                                                                                   
    name: str                                                                                                                                                                    
    provider: str
    description: str


class ModelNode(BaseModel):
    status: Literal["pending", "positive", "negative", "in-progress"]
    children: list[ModelNode]                                                                                                                                                    
    model: MedicalModel                                                                                                                                                          
                                                                                                                                                                                
                                                                                                                                                                                
ModelNode.model_rebuild()  # required for self-referential model                                                                                                                 
                                                                                                                                                                                
                
class DiagnosisState(DBRecord):
    image_id: str
    progress_tree: ModelNode
    percent_completion: float
    annotations: list[Annotation]
    overall_diagnosis_context: str = ""