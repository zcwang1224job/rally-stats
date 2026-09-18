"""PublishAfterResponseMiddleware — publish() inside a request is held back
until the response has gone out, so a scorer's "+" no longer waits on the
Ably round trip. Built against a throwaway FastAPI app, called as raw ASGI so
the test sees exactly when the response body was sent relative to each
Ably send."""

from typing import Any

import pytest
from fastapi import FastAPI
from starlette.types import Message

from app.core import realtime
from app.core.errors import CloudFrontSafeStatusMiddleware
from app.core.realtime import PublishAfterResponseMiddleware, publish


@pytest.fixture
def log(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    entries: list[str] = []

    async def fake_send(channel_name: str, event: str, payload: dict[str, Any]) -> None:
        entries.append(f"ably:{event}")

    monkeypatch.setattr(realtime, "_send", fake_send)
    return entries


def _make_app(*, cloudfront: bool = False) -> FastAPI:
    app = FastAPI()
    if cloudfront:
        # Production also runs this BaseHTTPMiddleware underneath — the
        # deferral must still see the endpoint's publish() calls through it.
        app.add_middleware(CloudFrontSafeStatusMiddleware)
    app.add_middleware(PublishAfterResponseMiddleware)

    @app.post("/score")
    async def _score() -> dict[str, str]:
        await publish("court:g:c", "match.scoreUpdated", {})
        await publish("court:g:c", "match.ended", {})
        return {"ok": "yes"}

    @app.post("/boom")
    async def _boom() -> None:
        await publish("court:g:c", "match.scoreUpdated", {})
        raise RuntimeError("after the commit")

    return app


async def _call(app: FastAPI, path: str, log: list[str]) -> None:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test")],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            log.append("response sent")

    await app(scope, receive, send)


@pytest.mark.parametrize("cloudfront", [False, True])
async def test_events_go_out_after_the_response_in_publish_order(
    log: list[str], cloudfront: bool
) -> None:
    await _call(_make_app(cloudfront=cloudfront), "/score", log)

    assert log == ["response sent", "ably:match.scoreUpdated", "ably:match.ended"]


async def test_events_still_go_out_when_the_request_fails_after_publishing(
    log: list[str],
) -> None:
    """publish() only ever follows a commit, so the event is already true.
    (An unhandled error's 500 is written by Starlette's ServerErrorMiddleware,
    which sits outside every added middleware — so here the event goes out
    just before that response, not after it.)"""
    with pytest.raises(RuntimeError):
        await _call(_make_app(), "/boom", log)

    assert "ably:match.scoreUpdated" in log


async def test_publish_outside_a_request_is_sent_straight_away(log: list[str]) -> None:
    await publish("court:g:c", "match.nextRound", {})

    assert log == ["ably:match.nextRound"]
