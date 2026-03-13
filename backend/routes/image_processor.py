from fastapi import APIRouter
import cv2
from pydantic import BaseModel
from models import ORCHESTRATOR_ADDRESS, DiagnosisState, ImageStatus, CropResult, MedicalModel, ModelNode, OrchestratorInput
from dotenv import load_dotenv
from services.database import FirebaseDatabase
from services.gemini_cropper import smart_crop_image
import services.image_processor as img_processor
from requests import post

load_dotenv()
firebase_database = FirebaseDatabase()

class GetImageIDInput(BaseModel):
    image_base64: str

router = APIRouter()

@router.post("/get_image_id")
def get_image_id(input: GetImageIDInput):
    input_image = img_processor.base64_to_image(input.image_base64)
    crop_image_data: CropResult | bool = smart_crop_image(input.image_base64)

    if False == crop_image_data:
        return {
            "pass": False,
            "error": "No red bounding box found in the image."
        }
    
    cropped_image = img_processor.crop_image(input_image, crop_image_data.bounding_box)
    
    patient_id = firebase_database.get_user_id_by_first_name(crop_image_data.image_info.metadata["first_name"], crop_image_data.image_info.metadata["last_name"])
    crop_image_data.image_info.user_id = patient_id

    # bring back image id
    image_embeddings = img_processor.get_orb_descriptor(cropped_image)
    crop_image_data.image_info.image_features = image_embeddings
    image_id = img_processor.query_image_id(image_embeddings)

    if image_id is False:
        firebase_database.set_rl_data("images", crop_image_data.image_info)
        firebase_database.set_rl_data("diagnosis", DiagnosisState(
            id=crop_image_data.image_info.id,
            image_id=crop_image_data.image_info.id,
            progress_tree=ModelNode(
                status="in-progress",
                children=[],
                model=MedicalModel(
                    name="Orchestrator",
                    description="Identifies which potential models to run based on doctors diagnosis",
                    provider="Stanford AI Lab", 
                )
            ),
            percent_completion=0.0,
            annotations=[]
        ))

        post(ORCHESTRATOR_ADDRESS, json=OrchestratorInput(
            db_information=crop_image_data.image_info,
            image=input.image_base64
        ).model_dump(mode="json"))

        return {
            "pass": True,
            "status": "Image has not been cached before, evaluating image now", 
            "image_id": ""
        }
    else : 
        return {
            "pass": True,
            "status": "Image has been chached, retrieve information", 
            "image_id": image_id
        }

@router.get("/find_image_id")
def get_image_id(input: GetImageIDInput):
    pass

@router.get("/get_user_information")
def get_image_id(input: GetImageIDInput):
    pass

@router.get("/crop_image")
def get_image_id(input: GetImageIDInput):
    pass
