import hashlib
import secrets
from fastapi import Header, HTTPException
from app.config import API_KEYS

def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

async def require_api_key(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer API key")
    key = authorization.removeprefix("Bearer ").strip()
    # Constant-time comparisons avoid leaking key matches through timing.
    if not any(secrets.compare_digest(key, configured) for configured in API_KEYS):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return hash_api_key(key)
