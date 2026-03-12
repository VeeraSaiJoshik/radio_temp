from fastapi import FastAPI
import uvicorn

from routes.image_processor import router as ip_router

app = FastAPI()

app.include_router(ip_router, prefix="/image-processor")

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)