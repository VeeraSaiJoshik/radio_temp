from fastapi import APIRouter
import cv2
from pydantic import BaseModel
from models import BoundingBox
from dotenv import load_dotenv
import services.image_processor as img_processor

load_dotenv()

class GetImageIDInput(BaseModel):
    image_base64: str

router = APIRouter()

@router.get("/get_image_id")
def get_image_id(input: GetImageIDInput):
    input_image = img_processor.base64_to_image(input.image_base64)
    # crop image
    # bring back image id
    # write the orchestration end point
    
    return {"image_id": "12345"}

@router.get("/find_image_id")
def get_image_id(input: GetImageIDInput):
    pass

@router.get("/get_user_information")
def get_image_id(input: GetImageIDInput):
    pass

@router.get("/crop_image")
def get_image_id(input: GetImageIDInput):
    pass
