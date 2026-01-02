from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from .settings import Settings, get_settings

SUPPORTED_API_HEADERS = ("x-api-key", "api_key")


def _extract_api_key(headers) -> Optional[str]:
    for header_name, header_value in headers.items():
        if header_name.lower() in SUPPORTED_API_HEADERS:
            if header_value:
                return header_value
    return None


async def require_api_key(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    api_key = _extract_api_key(request.headers)
    if not api_key or api_key != settings.mcp_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
