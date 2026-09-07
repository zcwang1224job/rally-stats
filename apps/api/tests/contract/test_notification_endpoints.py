"""Contract test for GET /notifications, GET /notifications/unread-count,
POST /notifications/{id}/read, POST /notifications/read-all, per
specs/012-realtime-notifications/contracts/notification-api.md."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_and_verify(session: AsyncSession, email: str, nickname: str) -> None:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return str(response.json()["access_token"])


async def test_list_and_read_all_contract(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register_and_verify(db_session, "notifcontract-a@example.com", "甲")
    await _register_and_verify(db_session, "notifcontract-b@example.com", "乙")
    token_a = await _login(client, "notifcontract-a@example.com")
    token_b = await _login(client, "notifcontract-b@example.com")
    b_number = (
        await client.get("/members/me", headers={"Authorization": f"Bearer {token_b}"})
    ).json()["user_number"]

    await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    listed = await client.get("/notifications", headers={"Authorization": f"Bearer {token_b}"})
    assert listed.status_code == 200
    body = listed.json()
    assert body["unread_count"] == 1
    assert body["page"] == 1
    assert body["total_pages"] == 1
    assert len(body["notifications"]) == 1
    assert body["notifications"][0]["type"] == "friend_request"
    assert body["notifications"][0]["friend_request"]["requester"]["nickname"] == "甲"

    read_all = await client.post(
        "/notifications/read-all", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert read_all.status_code == 200
    assert read_all.json()["marked_count"] == 1

    read_all_again = await client.post(
        "/notifications/read-all", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert read_all_again.json()["marked_count"] == 0


async def test_mark_single_read_contract(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register_and_verify(db_session, "notifcontract-c@example.com", "丙")
    await _register_and_verify(db_session, "notifcontract-d@example.com", "丁")
    token_c = await _login(client, "notifcontract-c@example.com")
    token_d = await _login(client, "notifcontract-d@example.com")
    d_number = (
        await client.get("/members/me", headers={"Authorization": f"Bearer {token_d}"})
    ).json()["user_number"]

    await client.post(
        "/friends/requests",
        json={"addressee_user_number": d_number},
        headers={"Authorization": f"Bearer {token_c}"},
    )
    notification_id = (
        await client.get("/notifications", headers={"Authorization": f"Bearer {token_d}"})
    ).json()["notifications"][0]["notification_id"]

    marked = await client.post(
        f"/notifications/{notification_id}/read",
        headers={"Authorization": f"Bearer {token_d}"},
    )
    assert marked.status_code == 200
    assert marked.json() == {"notification_id": notification_id, "read": True}

    unread_count = await client.get(
        "/notifications/unread-count", headers={"Authorization": f"Bearer {token_d}"}
    )
    assert unread_count.json() == {"unread_count": 0}


async def test_mark_read_rejects_foreign_notification(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "notifcontract-e@example.com", "戊")
    await _register_and_verify(db_session, "notifcontract-f@example.com", "己")
    await _register_and_verify(db_session, "notifcontract-g@example.com", "庚")
    token_e = await _login(client, "notifcontract-e@example.com")
    token_f = await _login(client, "notifcontract-f@example.com")
    token_g = await _login(client, "notifcontract-g@example.com")
    f_number = (
        await client.get("/members/me", headers={"Authorization": f"Bearer {token_f}"})
    ).json()["user_number"]

    await client.post(
        "/friends/requests",
        json={"addressee_user_number": f_number},
        headers={"Authorization": f"Bearer {token_e}"},
    )
    notification_id = (
        await client.get("/notifications", headers={"Authorization": f"Bearer {token_f}"})
    ).json()["notifications"][0]["notification_id"]

    response = await client.post(
        f"/notifications/{notification_id}/read",
        headers={"Authorization": f"Bearer {token_g}"},
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "NOTIFICATION_NOT_FOUND"


async def test_notification_endpoints_require_login(client: AsyncClient) -> None:
    assert (await client.get("/notifications")).status_code == 401
    assert (await client.get("/notifications/unread-count")).status_code == 401
    assert (await client.post("/notifications/read-all")).status_code == 401
