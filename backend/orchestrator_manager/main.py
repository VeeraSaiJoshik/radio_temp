"""
Orchestrator Manager — real AI pipeline.

Same interface as the dummy orchestrator (backend/orchestrator/main.py):
  POST /register  →  accepts OrchestratorInput, starts background pipeline, returns immediately
  GET  /health    →  health check

Runs on port 8081 by default (dummy stays on 8080).
To switch the backend to use this orchestrator instead of the dummy, set:
  ORCHESTRATOR_ADDRESS=http://localhost:8081/register
in backend/.env
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading

import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

from models import OrchestratorInput
from pipeline import run_pipeline

load_dotenv()

app = FastAPI()


@app.post("/register")
def register(input: OrchestratorInput):
    image_id  = input.db_information.id
    image_b64 = input.image
    db_info   = input.db_information

    threading.Thread(
        target=run_pipeline,
        args=(image_id, image_b64, db_info),
        daemon=True,
    ).start()

    return {"status": "accepted", "image_id": image_id}


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8081"))
    uvicorn.run(app, host="127.0.0.1", port=port)
