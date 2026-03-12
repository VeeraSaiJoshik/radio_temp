from services.image_processor import base64_to_image
from models import BoundingBox
import cv2

from services.testing_utils import image_path_to_base64

def smart_crop_image(image: str):
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

    result = BoundingBox(x=x, y=y, width=w, height=h)

    cropped = img[y:y + h, x:x + w]
    cv2.imshow("Cropped Image", cropped)
    cv2.waitKey(-1)

    return result


if __name__ == "__main__":
    print("starting testing")
    smart_crop_image(image_path_to_base64("./images/med_img_3.png"))