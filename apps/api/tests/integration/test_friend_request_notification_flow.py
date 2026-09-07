"""Integration test: sending a friend request creates a notification for
the addressee in the same transaction, and it's immediately visible via
GET /notifications/unread-count and GET /notifications — the full
US1/US2/US3 loop (specs/012-realtime-notifications/quickstart.md)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_verified(session: AsyncSession, email: str, nickname: str) -> str:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member.user_number


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return str(response.json()["access_token"])


async def test_friend_request_notification_full_flow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_verified(db_session, "notifflow-a@example.com", "A")
    b_user_number = await _register_verified(db_session, "notifflow-b@example.com", "B")

    token_a = await _login(client, "notifflow-a@example.com")
    token_b = await _login(client, "notifflow-b@example.com")

    unread_before = await client.get(
        "/notifications/unread-count", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert unread_before.json()["unread_count"] == 0

    created = await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_user_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert created.status_code == 201
    friend_request_id = created.json()["friend_request_id"]

    unread_after = await client.get(
        "/notifications/unread-count", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert unread_after.json()["unread_count"] == 1

    listed = await client.get(
        "/notifications", headers={"Authorization": f"Bearer {token_b}"}
    )
    body = listed.json()
    assert body["unread_count"] == 1
    assert len(body["notifications"]) == 1
    notification = body["notifications"][0]
    assert notification["type"] == "friend_request"
    assert notification["read"] is False
    assert notification["friend_request"]["friend_request_id"] == friend_request_id
    assert notification["friend_request"]["status"] == "pending"
    assert notification["friend_request"]["requester"]["nickname"] == "A"

    # A (the requester) sees no notification of their own outgoing request.
    a_notifications = await client.get(
        "/notifications", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert a_notifications.json()["notifications"] == []

    marked = await client.post(
        f"/notifications/{notification['notification_id']}/read",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert marked.json()["read"] is True

    unread_final = await client.get(
        "/notifications/unread-count", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert unread_final.json()["unread_count"] == 0


async def test_notification_reflects_request_resolved_elsewhere_and_mark_all_read(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """quickstart.md Edge Case: a friend request accepted directly from
    /friends/requests (never through the notification) still shows its
    current status, not the "pending" it had at notification-creation
    time. Also closes the loop on "全部標示已讀" (FR-008) across multiple
    notifications."""
    await _register_verified(db_session, "notifflow-c@example.com", "C")
    b_user_number = await _register_verified(db_session, "notifflow-d@example.com", "D")
    token_a = await _login(client, "notifflow-c@example.com")
    token_b = await _login(client, "notifflow-d@example.com")

    first = await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_user_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    await client.post(
        f"/friends/requests/{first.json()['friend_request_id']}/accept",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    listed = await client.get("/notifications", headers={"Authorization": f"Bearer {token_b}"})
    assert listed.json()["notifications"][0]["friend_request"]["status"] == "accepted"

    # A second, unrelated notification (a fresh requester) to prove
    # read-all sweeps every unread row for this member, not just one.
    await _register_verified(db_session, "notifflow-e@example.com", "E")
    token_e = await _login(client, "notifflow-e@example.com")
    await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_user_number},
        headers={"Authorization": f"Bearer {token_e}"},
    )

    unread_count_headers = {"Authorization": f"Bearer {token_b}"}
    assert (
        await client.get("/notifications/unread-count", headers=unread_count_headers)
    ).json()["unread_count"] == 2

    read_all = await client.post(
        "/notifications/read-all", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert read_all.json()["marked_count"] == 2
    assert (
        await client.get("/notifications/unread-count", headers=unread_count_headers)
    ).json()["unread_count"] == 0
