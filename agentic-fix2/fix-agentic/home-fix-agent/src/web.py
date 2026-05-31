"""Web UI: FastAPI server with chat-driven interface."""
from __future__ import annotations
import asyncio
import json
import re
import shutil
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.agents import order_manager
from src.intake.photo import validate_and_store
from src.models.schemas import PipelineResult, PipelineStage, Session
from src.pipeline import advance, start_session, stream_session
from src.storage.store import delete_session, list_sessions, load_result, save_result
from src.utils.config import STATIC_DIR

_STREAM_DONE = object()

def _next_stream_event(gen):
    try:
        return next(gen)
    except StopIteration:
        return _STREAM_DONE

app = FastAPI(title="Reparo")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_SESSION_ID_RE = re.compile(r"^[a-f0-9]{12}$")

def _valid_session_id(sid: str) -> bool:
    return bool(_SESSION_ID_RE.match(sid))

# Rate limiter: 4 requests per 60 seconds per IP
_RATE_LIMIT = 4
_RATE_WINDOW = 60
_request_log: dict[str, list[float]] = defaultdict(list)

def _check_rate_limit(request: Request) -> str | None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    _request_log[ip] = [t for t in _request_log[ip] if now - t < _RATE_WINDOW]
    if len(_request_log[ip]) >= _RATE_LIMIT:
        return f"Rate limit exceeded (max {_RATE_LIMIT}/min). Please wait."
    _request_log[ip].append(now)
    return None


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/analyze-stream")
async def analyze_stream(request: Request, photo: UploadFile = File(...), description: str = Form("")):
    if err := _check_rate_limit(request):
        return JSONResponse({"error": err}, status_code=429)
    suffix = Path(photo.filename or "photo.jpg").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(photo.file, tmp)
        tmp_path = tmp.name

    session = Session(description=description)
    sid = session.session_id
    try:
        stored = validate_and_store(tmp_path, sid)
    except (FileNotFoundError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    async def event_stream():
        loop = asyncio.get_running_loop()
        gen = stream_session(stored, description, session_id=sid)
        while True:
            try:
                item = await loop.run_in_executor(None, _next_stream_event, gen)
                if item is _STREAM_DONE:
                    break
                event_type, result = item
                if event_type == "analysis":
                    payload = {
                        "type": "analysis",
                        "session_id": result.session.session_id,
                        "analysis": result.analysis.model_dump(mode="json") if result.analysis else None,
                        "stage": result.stage.value,
                        "error": result.error,
                    }
                elif event_type == "spec":
                    payload = {"type": "spec",
                               "spec": result.spec.model_dump(mode="json") if result.spec else None}
                elif event_type == "products":
                    payload = {
                        "type": "products",
                        "session_id": result.session.session_id,
                        "products": [p.model_dump(mode="json") for p in result.products],
                        "part_searches": [ps.model_dump(mode="json") for ps in result.part_searches],
                    }
                elif event_type == "done":
                    payload = {"type": "done", "result": result.model_dump(mode="json")}
                elif event_type == "error":
                    payload = {"type": "error", "message": result.error or "Unknown error"}
                else:
                    continue
                yield f"data: {json.dumps(payload)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat")
async def chat(request: Request, session_id: str = Form(...), message: str = Form(...)):
    if err := _check_rate_limit(request):
        return JSONResponse({"error": err}, status_code=429)
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    result = load_result(session_id)
    if not result:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    result = advance(result, message)
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/order")
async def place_order(request: Request, session_id: str = Form(...), product_index: int = Form(...)):
    if err := _check_rate_limit(request):
        return JSONResponse({"error": err}, status_code=429)
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    r = load_result(session_id)
    if not r or product_index < 0 or product_index >= len(r.products):
        return JSONResponse({"error": "Invalid session or product"}, status_code=400)
    product = r.products[product_index]
    order = order_manager.create_order(session_id, product)
    order = order_manager.confirm_order(order)
    r.order = order
    r.stage = PipelineStage.RESULTS
    save_result(r)
    return JSONResponse(r.model_dump(mode="json"))


@app.delete("/session/{session_id}")
async def delete_session_endpoint(session_id: str):
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    if delete_session(session_id):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.post("/session/{session_id}/rename")
async def rename_session(session_id: str, name: str = Form(...)):
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    r = load_result(session_id)
    if not r:
        return JSONResponse({"error": "Not found"}, status_code=404)
    r.session.display_name = name.strip()[:80]
    save_result(r)
    return JSONResponse({"ok": True})


@app.get("/history")
async def history():
    return JSONResponse(list_sessions())


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    r = load_result(session_id)
    if not r:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(r.model_dump(mode="json"))


@app.get("/session/{session_id}/photo")
async def get_photo(session_id: str):
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    r = load_result(session_id)
    if not r or not r.session.photo_path:
        return JSONResponse({"error": "Not found"}, status_code=404)
    photo = Path(r.session.photo_path)
    if not photo.exists():
        return JSONResponse({"error": "Photo not found"}, status_code=404)
    return FileResponse(photo)


def start_server():
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting web UI at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
