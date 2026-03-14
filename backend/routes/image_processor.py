from fastapi import APIRouter
import cv2
import base64
import traceback
from pydantic import BaseModel
from models import ORCHESTRATOR_ADDRESS, DiagnosisState, ImageStatus, CropResult, MedicalModel, ModelNode, OrchestratorInput, RawImage
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
        try:
            firebase_database.set_rl_data("images", crop_image_data.image_info)
        except Exception as e:
            print(f"Warning: Firebase write to 'images' failed: {e}")
        _, buffer = cv2.imencode('.jpg', cropped_image)
        image_b64 = base64.b64encode(buffer).decode('utf-8')
        try:
            firebase_database.set_rl_data("raw_image", RawImage(
                id=crop_image_data.image_info.id,
                image_id=crop_image_data.image_info.id,
                image_b64=image_b64
            ))
        except Exception as e:
            print(f"Warning: Firebase write to 'raw_image' failed: {e}")
        try:
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
        except Exception as e:
            print(f"Warning: Firebase write to 'diagnosis' failed: {e}")

        try:
            post(ORCHESTRATOR_ADDRESS, json=OrchestratorInput(
                db_information=crop_image_data.image_info,
                image=input.image_base64
            ).model_dump(mode="json"))
        except Exception as e:
            print(f"Warning: Orchestrator call failed (likely offline): {e}")

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
def find_image_id(input: GetImageIDInput):
    pass

@router.get("/get_user_information")
def get_user_information(input: GetImageIDInput):
    pass

@router.get("/crop_image")
def crop_image(input: GetImageIDInput):
    pass
