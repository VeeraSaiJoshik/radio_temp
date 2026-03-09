"""FastAPI server exposing the Python runtime to the Electron shell."""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from desktop_bridge.service import BridgeService


class FlagRequest(BaseModel):
    override_note: str = ""


def build_app(*, start_backend_server: bool, demo_mode: bool) -> FastAPI:
    service = BridgeService(
        start_backend_server=start_backend_server,
        demo_mode=demo_mode,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = service
        await service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(title="Radiology Copilot Electron Bridge", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/state")
    async def state():
        return await service.get_state()

    @app.post("/api/capture")
    async def capture():
        try:
            return await service.capture_and_analyze()
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/dismiss")
    async def dismiss():
        return await service.dismiss_current_read()

    @app.post("/api/flag")
    async def flag(request: FlagRequest):
        try:
            return await service.flag_current_read(request.override_note)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket("/api/events")
    async def events_socket(websocket: WebSocket):
        await websocket.accept()
        queue = await service.events.subscribe()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            await service.events.unsubscribe(queue)

    return app


def run_bridge_server(
    *,
    host: str = config.DESKTOP_BRIDGE_HOST,
    port: int = config.DESKTOP_BRIDGE_PORT,
    start_backend_server: bool = True,
    demo_mode: bool = False,
) -> None:
    app = build_app(
        start_backend_server=start_backend_server,
        demo_mode=demo_mode,
    )
    uvicorn.run(app, host=host, port=port, log_level="warning")
