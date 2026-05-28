"""Photo intake: validate and store user photos."""
from __future__ import annotations
import shutil
from pathlib import Path
from src.utils.config import sessions_dir

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic"}
MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

def validate_and_store(photo_path: str, session_id: str) -> str:
    """Validate photo format/size, copy to session dir. Returns stored path."""
    src = Path(photo_path)
    if not src.exists():
        raise FileNotFoundError(f"Photo not found: {photo_path}")
    if src.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported format {src.suffix}. Supported: {', '.join(ALLOWED_EXTENSIONS)}")
    if src.stat().st_size > MAX_SIZE_BYTES:
        raise ValueError(f"File too large ({src.stat().st_size} bytes). Max: {MAX_SIZE_BYTES} bytes")

    dest_dir = sessions_dir() / session_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"photo{src.suffix.lower()}"
    shutil.copy2(src, dest)
    return str(dest)
