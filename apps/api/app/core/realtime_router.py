"""Shared endpoint issuing subscribe-only Ably tokens to any frontend client."""

from typing import Any

from fastapi import APIRouter

from app.core.realtime import create_subscribe_token_request

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.get("/ably-token")
async def get_ably_token() -> dict[str, Any]:
    """Signed, subscribe-only Ably TokenRequest for the Ably JS SDK's
    `authUrl`. The frontend never receives a publish-capable credential."""
    return await create_subscribe_token_request()
