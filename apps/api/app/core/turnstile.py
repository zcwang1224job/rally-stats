"""Cloudflare Turnstile verification (fail-closed per specs/001 research.md #7).

Any timeout, transport error, or non-success response is treated as verification
failure — never silently allowed through. Only the "register" and "create group"
endpoints call this (see spec FR-007 and specs/architecture.md Constitution Check XI).
"""

import httpx

from app.core.config import get_settings
from app.core.errors import ApiError

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile_token(token: str, remote_ip: str | None = None) -> None:
    """Raise ApiError(CAPTCHA_INVALID | CAPTCHA_EXPIRED) if verification fails."""
    settings = get_settings()
    payload = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=settings.turnstile_timeout_seconds) as client:
            response = await client.post(SITEVERIFY_URL, data=payload)
    except httpx.TimeoutException as exc:
        raise ApiError("CAPTCHA_INVALID", status_code=400) from exc
    except httpx.HTTPError as exc:
        raise ApiError("CAPTCHA_INVALID", status_code=400) from exc

    if response.status_code != 200:
        raise ApiError("CAPTCHA_INVALID", status_code=400)

    body = response.json()
    if body.get("success") is True:
        return

    error_codes: list[str] = body.get("error-codes", [])
    if "timeout-or-duplicate" in error_codes:
        raise ApiError("CAPTCHA_EXPIRED", status_code=400)
    raise ApiError("CAPTCHA_INVALID", status_code=400)
