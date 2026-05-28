"""Configuration loader."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIGS_DIR = _ROOT / "configs"
PROMPTS_DIR = _ROOT / "prompts"
DATA_DIR = _ROOT / "data"
STATIC_DIR = _ROOT / "static"

def load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}

def load_categories() -> dict[str, Any]:
    return load_yaml(CONFIGS_DIR / "categories.yaml")

def load_ranking() -> dict[str, Any]:
    return load_yaml(CONFIGS_DIR / "ranking.yaml")

def load_prompt(name: str) -> str:
    p = PROMPTS_DIR / f"{name}.md"
    return p.read_text() if p.exists() else ""

def get_llm_config() -> dict[str, str]:
    return {
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "base_url": os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
    }

def sessions_dir() -> Path:
    d = DATA_DIR / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d
