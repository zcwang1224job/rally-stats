"""Ably REST publish wrapper — the ONLY place the backend writes to Ably.

Constitution principle X: server is the single source of truth. All frontend
Ably tokens are subscribe-only; every event is published here, after the
triggering database transaction has already committed.
"""

import json
import logging
from typing import Any

from ably import AblyRest

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: AblyRest | None = None


def _get_client() -> AblyRest:
    global _client
    if _client is None:
        _client = AblyRest(get_settings().ably_api_key)
    return _client


async def publish(channel_name: str, event: str, payload: dict[str, Any]) -> None:
    """Publish a single event to a single channel.

    Callers MUST have already committed their DB write before calling this —
    the database is the single source of truth (constitution X), and delivery
    of this event is best-effort: connected clients get it in ~1s, while
    disconnected clients fall back to the heartbeat/reconnect state-refresh
    path (specs/architecture.md). A transient Ably failure here MUST NOT fail
    a request whose business-state write already succeeded.
    """
    try:
        channel = _get_client().channels.get(channel_name)
        await channel.publish(event, payload)
    except Exception:
        logger.exception("Ably publish failed for channel=%s event=%s", channel_name, event)


async def create_subscribe_token_request() -> dict[str, Any]:
    """Signed Ably TokenRequest with subscribe-only capability, for the browser
    to exchange for a short-lived token via the JS SDK's `authCallback`.
    Constitution X: the frontend MUST NEVER hold the raw Ably API key or a
    publish-capable token — every write goes through `publish()` above."""
    token_request = await _get_client().auth.create_token_request(
        token_params={"capability": json.dumps({"*": ["subscribe"]})}
    )
    return dict(token_request.to_dict())


def court_channel(group_id: str, court_id: str) -> str:
    return f"court:{group_id}:{court_id}"


def group_notifications_channel(group_id: str) -> str:
    return f"group:{group_id}:notifications"
