"""Clerk JWT verification and user identity helpers."""
from __future__ import annotations
import base64
import json
import logging
import os
import time

import httpx
import jwt

logger = logging.getLogger(__name__)

# ── JWKS cache ────────────────────────────────────────────────────────────────
_jwks_keys: list = []
_jwks_fetched_at: float = 0
_JWKS_TTL = 300  # seconds


def _clerk_jwks_url() -> str | None:
    """Derive Clerk's JWKS URL from the publishable key, or use explicit override."""
    explicit = os.environ.get("CLERK_JWKS_URL", "").strip()
    if explicit:
        return explicit
    pk = os.environ.get("CLERK_PUBLISHABLE_KEY", "").strip()
    if not pk:
        return None
    try:
        # Clerk publishable key format: pk_{test|live}_{base64(domain)}$
        b64 = pk.split("_", 2)[2].rstrip("$")
        # Standard base64 padding
        b64 += "=" * (4 - len(b64) % 4)
        domain = base64.b64decode(b64).decode().strip().rstrip("/")
        return f"https://{domain}/.well-known/jwks.json"
    except Exception as e:
        logger.warning("Cannot derive JWKS URL from publishable key: %s", e)
        return None


def _get_jwks() -> list:
    global _jwks_keys, _jwks_fetched_at
    now = time.time()
    if _jwks_keys and now - _jwks_fetched_at < _JWKS_TTL:
        return _jwks_keys
    url = _clerk_jwks_url()
    if not url:
        return _jwks_keys
    try:
        r = httpx.get(url, timeout=5)
        r.raise_for_status()
        _jwks_keys = r.json().get("keys", [])
        _jwks_fetched_at = now
        logger.info("JWKS refreshed (%d keys)", len(_jwks_keys))
    except Exception as e:
        logger.warning("JWKS fetch failed: %s", e)
    return _jwks_keys


# ── Token verification ────────────────────────────────────────────────────────

def verify_token(token: str) -> dict | None:
    """Return decoded JWT payload if the Clerk token is valid, else None."""
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        return None
    kid = header.get("kid")
    for key_data in _get_jwks():
        if key_data.get("kid") == kid:
            try:
                pub = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
                return jwt.decode(token, pub, algorithms=["RS256"],
                                  options={"verify_aud": False})
            except Exception as e:
                logger.debug("JWT decode failed: %s", e)
                return None
    logger.debug("No matching JWK for kid=%s", kid)
    return None


# ── Public helpers ─────────────────────────────────────────────────────────────

def clerk_enabled() -> bool:
    """True when Clerk credentials are configured (auth is enforced)."""
    return bool(os.environ.get("CLERK_PUBLISHABLE_KEY") or
                os.environ.get("CLERK_JWKS_URL"))


DEV_USER_ID: str = os.environ.get("DEV_USER_ID", "")


def get_user_id(request) -> str | None:
    """Extract and verify the Clerk user ID from the Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = verify_token(auth[7:])
    return payload.get("sub") if payload else None


def is_dev(user_id: str | None) -> bool:
    return bool(DEV_USER_ID and user_id == DEV_USER_ID)
