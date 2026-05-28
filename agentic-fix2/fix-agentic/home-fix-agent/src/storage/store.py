"""Storage layer: persist pipeline artifacts as JSON per session."""
from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel
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
    path = _session_dir(session_id) / "result.json"
    if not path.exists():
        return None
    return PipelineResult.model_validate_json(path.read_text())


def list_sessions() -> list[dict]:
    """List all sessions with basic info."""
    results = []
    for d in sorted(sessions_dir().iterdir(), reverse=True):
        if not d.is_dir():
            continue
        rfile = d / "result.json"
        if rfile.exists():
            try:
                r = PipelineResult.model_validate_json(rfile.read_text())
                results.append({
                    "session_id": r.session.session_id,
                    "created_at": r.session.created_at.isoformat(),
                    "status": r.session.status.value,
                    "category": r.analysis.item_category if r.analysis else "",
                    "picks": len(r.products),
                })
            except Exception:
                results.append({"session_id": d.name, "status": "corrupt"})
    return results
