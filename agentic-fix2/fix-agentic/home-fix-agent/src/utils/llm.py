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

def _encode_image(path: str) -> str:
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode()

def llm_vision_json(system: str, user_text: str, image_path: str, retries: int = 2) -> dict:
    """Call LLM with an image, expecting JSON output."""
    client, model = _client()
    b64 = _encode_image(image_path)
    ext = Path(image_path).suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "heic": "image/heic"}.get(ext, "image/jpeg")

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
