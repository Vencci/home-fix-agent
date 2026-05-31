"""LLM client wrapper with vision support and JSON parsing."""
from __future__ import annotations
import base64
import json
import logging
from pathlib import Path
from openai import OpenAI
from src.utils.config import get_llm_config

logger = logging.getLogger(__name__)

def _client() -> tuple[OpenAI, str]:
    cfg = get_llm_config()
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"]), cfg["model"]

def encode_image(path: str) -> tuple[str, str]:
    """Return (base64_string, mime_type) for an image file."""
    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode()
    ext = Path(path).suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "heic": "image/heic"}.get(ext, "image/jpeg")
    return b64, mime

def llm_vision_json(system: str, user_text: str, image_path: str, retries: int = 2,
                    _encoded: tuple[str, str] | None = None) -> dict:
    """Call LLM with an image, expecting JSON output.

    Pass _encoded=(b64, mime) to avoid re-reading the file when calling multiple times
    for the same photo.
    """
    client, model = _client()
    if _encoded:
        b64, mime = _encoded
    else:
        b64, mime = encode_image(image_path)

    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ]},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            logger.warning("Vision LLM attempt %d failed: %s", attempt + 1, e)
            if attempt == retries:
                raise
    return {}

def llm_text(system: str, user_text: str, retries: int = 1) -> str:
    """Call LLM expecting a plain text response."""
    client, model = _client()
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.4,
                max_tokens=400,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning("LLM text attempt %d failed: %s", attempt + 1, e)
            if attempt == retries:
                raise
    return ""

def llm_json(system: str, user_text: str, retries: int = 2) -> dict:
    """Call LLM expecting JSON output (text only, no image)."""
    client, model = _client()
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            logger.warning("LLM attempt %d failed: %s", attempt + 1, e)
            if attempt == retries:
                raise
    return {}
