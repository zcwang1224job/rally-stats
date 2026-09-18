"""Ably REST publish wrapper — the ONLY place the backend writes to Ably.

Constitution principle X: server is the single source of truth. All frontend
Ably tokens are subscribe-only; every event is published here, after the
triggering database transaction has already committed.
"""

import json
import logging
from contextvars import ContextVar
from typing import Any

from ably import AblyRest
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: AblyRest | None = None

# Set by PublishAfterResponseMiddleware for the length of one HTTP request:
# publish() appends here instead of calling Ably, and the middleware sends
# the collected events, in order, once the response has gone out.
_deferred: ContextVar[list[tuple[str, str, dict[str, Any]]] | None] = ContextVar(
    "realtime_deferred", default=None
)


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

    Inside an HTTP request the event is only queued: the Ably round trip
    (~65 ms, far more when Ably is slow) would otherwise sit in front of the
    response — a scorer's "+" waited on it before anything moved on screen.
    PublishAfterResponseMiddleware sends it right after the response. Outside
    a request (the scheduler) it is sent straight away.
    """
    deferred = _deferred.get()
    if deferred is not None:
        deferred.append((channel_name, event, payload))
        return
    await _send(channel_name, event, payload)


async def _send(channel_name: str, event: str, payload: dict[str, Any]) -> None:
    try:
        channel = _get_client().channels.get(channel_name)
        await channel.publish(event, payload)
    except Exception:
        logger.exception("Ably publish failed for channel=%s event=%s", channel_name, event)


class PublishAfterResponseMiddleware:
    """Collects every publish() of one HTTP request and sends them after the
    response, in the order they were published — so one request's events
    (e.g. match.ended, then rotation.updated) still arrive in order. They go
    out even when the request failed afterwards: publish() is only ever
    called after a commit, so each event describes state that is already
    true. Pure ASGI rather than BaseHTTPMiddleware, so the context variable
    set here is the one the endpoint sees."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        pending: list[tuple[str, str, dict[str, Any]]] = []
        token = _deferred.set(pending)
        try:
            await self.app(scope, receive, send)
        finally:
            _deferred.reset(token)
            for channel_name, event, payload in pending:
                await _send(channel_name, event, payload)


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


def member_notifications_channel(member_id: str) -> str:
    return f"member:{member_id}:notifications"
