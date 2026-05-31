"""Storage layer: persist pipeline artifacts as JSON per session."""
from __future__ import annotations
import json
from pathlib import Path
from src.models.schemas import PipelineResult
from src.utils.config import sessions_dir


def _session_dir(session_id: str) -> Path:
    d = sessions_dir() / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_result(result: PipelineResult) -> Path:
    """Save full pipeline result to session directory."""
    d = _session_dir(result.session.session_id)
    path = d / "result.json"
    path.write_text(result.model_dump_json(indent=2))
    return path


def load_result(session_id: str) -> PipelineResult | None:
    """Load a pipeline result from a session directory."""
    path = sessions_dir() / session_id / "result.json"
    if not path.exists():
        return None
    return PipelineResult.model_validate_json(path.read_text())


def delete_session(session_id: str) -> bool:
    """Delete a session directory. Returns True if deleted, False if not found."""
    import shutil
    d = sessions_dir() / session_id
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True


def list_sessions(user_id: str | None = None, dev_user_id: str = "") -> list[dict]:
    """List sessions, sorted newest first.

    When user_id is given, only return sessions owned by that user
    (dev_user_id sees all sessions regardless).
    """
    results = []
    for d in sessions_dir().iterdir():
        if not d.is_dir():
            continue
        rfile = d / "result.json"
        if rfile.exists():
            try:
                raw = json.loads(rfile.read_text())
                session = raw.get("session", {})
                analysis = raw.get("analysis") or {}
                results.append({
                    "session_id": session.get("session_id", d.name),
                    "created_at": session.get("created_at", ""),
                    "status": session.get("status", "unknown"),
                    "category": session.get("display_name") or analysis.get("item_category", ""),
                    "user_id": session.get("user_id", ""),
                })
            except Exception:
                results.append({"session_id": d.name, "status": "corrupt",
                                 "created_at": "", "user_id": ""})

    if user_id and user_id != dev_user_id:
        results = [r for r in results if r.get("user_id") == user_id]

    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results
