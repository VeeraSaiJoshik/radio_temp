from dotenv import load_dotenv
from services.image_processor import base64_to_image
import google.generativeai as genai
import PIL.Image as Image
from models import BoundingBox, ImageInfo, CropResult, ImageDataDB
import cv2
import os
import json
import uuid
from services.testing_utils import image_path_to_base64

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
client = genai.GenerativeModel("gemini-2.5-pro")

def smart_crop_image(image: str) -> CropResult | bool:
    img: cv2.Mat = base64_to_image(image)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Red wraps around in HSV, so we need two ranges
    mask1 = cv2.inRange(hsv, (0, 120, 70), (10, 255, 255))
    mask2 = cv2.inRange(hsv, (170, 120, 70), (180, 255, 255))
    red_mask = cv2.bitwise_or(mask1, mask2)

    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return False

    # Pick the largest red contour (the outline border)
    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)

    bounding_box = BoundingBox(x=x, y=y, width=w, height=h)

    # Pass the full screenshot to Gemini to extract patient/scan metadata
    pil_image = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    prompt = (
        "You are analyzing a screenshot of a PACS medical imaging viewer. "
        "Extract any visible patient and scan information from the UI (e.g. overlays, sidebars, headers). "
        f"Extract the following information and return it as a JSON object in this format : {json.dumps(ImageDataDB.model_json_schema(), indent = 2)}"
        "Remember, in this software, there will be multiple names and meta data of multiple images on the side bar as a way for the doctor to navigate. You should only extract the patient and scan information that is currently pulled up. I.E pull the meta data information that is lcoated towards the center of the screen, in the window where the medical image annotation is taking place"
    )
    
    response = client.generate_content(
        [prompt, pil_image],
        generation_config=genai.GenerationConfig(response_mime_type="application/json"),
    )
    print(response.text)
    parsed = json.loads(response.text)
    if not parsed.get("id"):
        parsed["id"] = str(uuid.uuid4())
    image_info = ImageDataDB.model_validate(parsed)
    print(image_info)

    return CropResult(bounding_box=bounding_box, image_info=image_info)


if __name__ == "__main__":
    print("starting testing")
    result = smart_crop_image(image_path_to_base64("./images/med_img_3.png"))
    if result:
        print(result.model_dump_json(indent=2))
