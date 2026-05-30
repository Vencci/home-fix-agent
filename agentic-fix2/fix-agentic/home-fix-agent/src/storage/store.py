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


def list_sessions() -> list[dict]:
    """List all sessions with basic info, sorted newest first."""
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
                    "category": analysis.get("item_category", ""),
                })
            except Exception:
                results.append({"session_id": d.name, "status": "corrupt", "created_at": ""})
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results
