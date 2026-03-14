import asyncio
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from models import DiagnosisState, RawImage
from services.database import FirebaseDatabase

firebase_database = FirebaseDatabase()

router = APIRouter()

@router.get("/raw_image/{image_id}")
def get_raw_image(image_id: str):
    data = firebase_database.get_rl_data(f"raw_image/{image_id}")

    if data is None:
        raise HTTPException(status_code=404, detail=f"No raw image found for image_id: {image_id}")

    return data


@router.get("/diagnosis/stream")
async def stream_diagnosis(request: Request):
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_change(event):
        if event.event_type != "put" or event.data is None:
            return
        # Initial load — path is "/" with all children as a dict
        if event.path == "/":
            if isinstance(event.data, dict):
                for image_id, data in event.data.items():
                    if isinstance(data, dict):
                        loop.call_soon_threadsafe(queue.put_nowait, {"image_id": image_id, **data})
        else:
            # Individual child update — path is "/<image_id>"
            image_id = event.path.lstrip("/")
            if isinstance(event.data, dict):
                loop.call_soon_threadsafe(queue.put_nowait, {"image_id": image_id, **event.data})

    ref = firebase_database.db.child("diagnosis")
    listener = ref.listen(on_change)

    async def generate():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            listener.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/diagnosis/{image_id}", response_model=DiagnosisState)
def get_diagnosis(image_id: str):
    data = firebase_database.get_rl_data(f"diagnosis/{image_id}")

    if data is None:
        raise HTTPException(status_code=404, detail=f"No diagnosis found for image_id: {image_id}")

    return DiagnosisState.model_validate(data)
