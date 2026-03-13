from fastapi import APIRouter, HTTPException
from models import DiagnosisState
from services.database import FirebaseDatabase

firebase_database = FirebaseDatabase()

router = APIRouter()

@router.get("/diagnosis/{image_id}", response_model=DiagnosisState)
def get_diagnosis(image_id: str):
    data = firebase_database.get_rl_data(f"diagnosis/{image_id}")

    if data is None:
        raise HTTPException(status_code=404, detail=f"No diagnosis found for image_id: {image_id}")

    return DiagnosisState.model_validate(data)
