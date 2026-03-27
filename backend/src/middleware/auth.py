"""Simple API key authentication middleware.

If the API_KEY setting is configured, write-endpoints (POST, PATCH, DELETE)
require the ``X-API-Key`` header to match. When API_KEY is not set the
dependency is a no-op, allowing unauthenticated development use.
"""

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from src.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> None:
    """FastAPI dependency that enforces API key auth on mutating endpoints.

    Skips validation entirely when ``settings.api_key`` is not configured
    (dev mode). For configured keys, only POST/PATCH/DELETE methods are
    checked; GET and other read-only methods pass through.

    Raises:
        HTTPException: 401 if key is missing, 403 if key is wrong.
    """
    if settings.api_key is None:
        # No API key configured — dev mode, allow everything
        return

    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
