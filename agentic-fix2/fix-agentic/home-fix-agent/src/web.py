"""Web UI: FastAPI server with chat-driven interface."""
from __future__ import annotations
import shutil
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.agents import order_manager
from src.intake.photo import validate_and_store
from src.models.schemas import PipelineResult, PipelineStage, Session
from src.pipeline import advance, start_session
from src.storage.store import list_sessions, load_result, save_result
from src.utils.config import STATIC_DIR

app = FastAPI(title="Home Fix Agent")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Rate limiter: 2 requests per 60 seconds per IP
_RATE_LIMIT = 2
_RATE_WINDOW = 60
_request_log: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(request: Request) -> str | None:
    """Returns error message if rate limited, None if OK."""
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    # Prune old entries
    _request_log[ip] = [t for t in _request_log[ip] if now - t < _RATE_WINDOW]
    if len(_request_log[ip]) >= _RATE_LIMIT:
        return f"Rate limit exceeded. Please wait before making another request (max {_RATE_LIMIT} per minute)."
    _request_log[ip].append(now)
    return None


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/analyze")
async def analyze(request: Request, photo: UploadFile = File(...), description: str = Form("")):
    """Start a new session: upload photo and run through analysis + spec extraction."""
    if err := _check_rate_limit(request):
        return JSONResponse({"error": err}, status_code=429)
    suffix = Path(photo.filename or "photo.jpg").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(photo.file, tmp)
        tmp_path = tmp.name

    # Validate and store
    session = Session(description=description)
    sid = session.session_id
    try:
        stored = validate_and_store(tmp_path, sid)
    except (FileNotFoundError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Run incremental pipeline (blocks at clarification if needed)
    result = start_session(stored, description)
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/chat")
async def chat(request: Request, session_id: str = Form(...), message: str = Form(...)):
    """Send a message to an existing session to advance the pipeline."""
    if err := _check_rate_limit(request):
        return JSONResponse({"error": err}, status_code=429)
    result = load_result(session_id)
    if not result:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    result = advance(result, message)
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/order")
async def place_order(request: Request, session_id: str = Form(...), product_index: int = Form(...)):
    """Place an order for a selected product."""
    if err := _check_rate_limit(request):
        return JSONResponse({"error": err}, status_code=429)
    r = load_result(session_id)
    if not r or product_index < 0 or product_index >= len(r.products):
        return JSONResponse({"error": "Invalid session or product"}, status_code=400)

    product = r.products[product_index]
    order = order_manager.create_order(session_id, product)
    order = order_manager.confirm_order(order)
    r.order = order
    r.stage = PipelineStage.DONE
    save_result(r)
    return JSONResponse(r.model_dump(mode="json"))


@app.get("/history")
async def history():
    return JSONResponse(list_sessions())


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    r = load_result(session_id)
    if not r:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(r.model_dump(mode="json"))


@app.get("/session/{session_id}/photo")
async def get_photo(session_id: str):
    """Serve the session's uploaded photo."""
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
