"""Web UI: FastAPI server with chat-driven interface."""
from __future__ import annotations
import asyncio
import json
import os
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
from src.utils.auth import DEV_USER_ID, clerk_enabled, get_user_id, is_dev
from src.utils.config import STATIC_DIR

# ── SSE helper ────────────────────────────────────────────────────────────────
_STREAM_DONE = object()

def _next_stream_event(gen):
    try:
        return next(gen)
    except StopIteration:
        return _STREAM_DONE

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Home Fix Agent")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_SESSION_ID_RE = re.compile(r"^[a-f0-9]{12}$")

def _valid_session_id(sid: str) -> bool:
    return bool(_SESSION_ID_RE.match(sid))

# ── Auth helpers ──────────────────────────────────────────────────────────────

def _auth(request: Request) -> tuple[str | None, JSONResponse | None]:
    """Return (user_id, None) or (None, error_response).

    If Clerk is not configured, auth is optional (returns user_id=None, no error).
    """
    user_id = get_user_id(request)
    if clerk_enabled() and not user_id:
        return None, JSONResponse({"error": "Authentication required"}, status_code=401)
    return user_id, None

def _owns_session(result: PipelineResult, user_id: str | None) -> bool:
    """True if the user is allowed to access this session."""
    if is_dev(user_id):
        return True
    if not clerk_enabled():
        return True  # unauthenticated mode — no ownership enforcement
    return result.session.user_id == (user_id or "")

# ── Rate limiter ──────────────────────────────────────────────────────────────
_RATE_ANON   = 2   # requests/min — unauthenticated
_RATE_AUTHED = 4   # requests/min — authenticated users
_RATE_WINDOW = 60
_request_log: dict[str, list[float]] = defaultdict(list)

def _check_rate_limit(request: Request, user_id: str | None) -> str | None:
    if is_dev(user_id):
        return None  # dev account: unlimited
    key   = user_id or (request.client.host if request.client else "unknown")
    limit = _RATE_AUTHED if user_id else _RATE_ANON
    now   = time.time()
    _request_log[key] = [t for t in _request_log[key] if now - t < _RATE_WINDOW]
    if len(_request_log[key]) >= limit:
        return f"Rate limit exceeded (max {limit}/min). Please wait."
    _request_log[key].append(now)
    return None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/config")
async def api_config():
    """Frontend-safe config: Clerk publishable key and auth flag."""
    return JSONResponse({
        "clerk_publishable_key": os.environ.get("CLERK_PUBLISHABLE_KEY", ""),
        "auth_required": clerk_enabled(),
    })


@app.post("/analyze-stream")
async def analyze_stream(request: Request, photo: UploadFile = File(...), description: str = Form("")):
    """Start a new session and stream progress as SSE events."""
    user_id, err = _auth(request)
    if err:
        return err
    if rate_err := _check_rate_limit(request, user_id):
        return JSONResponse({"error": rate_err}, status_code=429)

    suffix = Path(photo.filename or "photo.jpg").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(photo.file, tmp)
        tmp_path = tmp.name

    session = Session(description=description, user_id=user_id or "")
    sid = session.session_id
    try:
        stored = validate_and_store(tmp_path, sid)
    except (FileNotFoundError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    async def event_stream():
        loop = asyncio.get_running_loop()
        gen = stream_session(stored, description, session_id=sid, user_id=user_id or "")
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
    user_id, err = _auth(request)
    if err:
        return err
    if rate_err := _check_rate_limit(request, user_id):
        return JSONResponse({"error": rate_err}, status_code=429)
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    result = load_result(session_id)
    if not result:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    if not _owns_session(result, user_id):
        return JSONResponse({"error": "Not found"}, status_code=404)
    result = advance(result, message)
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/order")
async def place_order(request: Request, session_id: str = Form(...), product_index: int = Form(...)):
    user_id, err = _auth(request)
    if err:
        return err
    if rate_err := _check_rate_limit(request, user_id):
        return JSONResponse({"error": rate_err}, status_code=429)
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    r = load_result(session_id)
    if not r or product_index < 0 or product_index >= len(r.products):
        return JSONResponse({"error": "Invalid session or product"}, status_code=400)
    if not _owns_session(r, user_id):
        return JSONResponse({"error": "Not found"}, status_code=404)
    product = r.products[product_index]
    order = order_manager.create_order(session_id, product)
    order = order_manager.confirm_order(order)
    r.order = order
    r.stage = PipelineStage.RESULTS  # keep session open after ordering
    save_result(r)
    return JSONResponse(r.model_dump(mode="json"))


@app.delete("/session/{session_id}")
async def delete_session_endpoint(request: Request, session_id: str):
    user_id, err = _auth(request)
    if err:
        return err
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    r = load_result(session_id)
    if not r:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _owns_session(r, user_id):
        return JSONResponse({"error": "Not found"}, status_code=404)
    delete_session(session_id)
    return JSONResponse({"ok": True})


@app.post("/session/{session_id}/rename")
async def rename_session(request: Request, session_id: str, name: str = Form(...)):
    user_id, err = _auth(request)
    if err:
        return err
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    r = load_result(session_id)
    if not r:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _owns_session(r, user_id):
        return JSONResponse({"error": "Not found"}, status_code=404)
    r.session.display_name = name.strip()[:80]
    save_result(r)
    return JSONResponse({"ok": True})


@app.get("/history")
async def history(request: Request):
    user_id, err = _auth(request)
    if err:
        return err
    return JSONResponse(list_sessions(user_id=user_id, dev_user_id=DEV_USER_ID))


@app.get("/session/{session_id}")
async def get_session(request: Request, session_id: str):
    user_id, err = _auth(request)
    if err:
        return err
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    r = load_result(session_id)
    if not r:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _owns_session(r, user_id):
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(r.model_dump(mode="json"))


@app.get("/session/{session_id}/photo")
async def get_photo(request: Request, session_id: str):
    user_id, err = _auth(request)
    if err:
        return err
    if not _valid_session_id(session_id):
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)
    r = load_result(session_id)
    if not r or not r.session.photo_path:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _owns_session(r, user_id):
        return JSONResponse({"error": "Not found"}, status_code=404)
    photo = Path(r.session.photo_path)
    if not photo.exists():
        return JSONResponse({"error": "Photo not found"}, status_code=404)
    return FileResponse(photo)


def start_server():
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting web UI at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
