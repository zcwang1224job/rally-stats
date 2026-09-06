"""Integration test: A/B become mutual friends -> both see each other in
GET /friends -> A unfriends -> both lists update immediately, B receives no
notification of any kind -> B can resend without limit (spec.md US7
acceptance scenario 4, FR-045/046)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.models import FriendRequest
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def test_full_friend_lifecycle_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    member_a = await register(db_session, "lifecycleflowA@example.com", "abc12345")
    member_a.verification_status = "verified"
    member_a.nickname = "甲"
    member_b = await register(db_session, "lifecycleflowB@example.com", "abc12345")
    member_b.verification_status = "verified"
    member_b.nickname = "乙"
    await db_session.commit()

    token_a = (
        await client.post(
            "/auth/login", json={"email": "lifecycleflowA@example.com", "password": "abc12345"}
        )
    ).json()["access_token"]
    token_b = (
        await client.post(
            "/auth/login", json={"email": "lifecycleflowB@example.com", "password": "abc12345"}
        )
    ).json()["access_token"]

    created = (
        await client.post(
            "/friends/requests",
            json={"addressee_user_number": member_b.user_number},
            headers={"Authorization": f"Bearer {token_a}"},
        )
    ).json()
    await client.post(
        f"/friends/requests/{created['friend_request_id']}/accept",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # Both sides see each other.
    assert (
        await client.get("/friends", headers={"Authorization": f"Bearer {token_a}"})
    ).json()["friends"][0]["member_id"] == str(member_b.id)
    assert (
        await client.get("/friends", headers={"Authorization": f"Bearer {token_b}"})
    ).json()["friends"][0]["member_id"] == str(member_a.id)

    # A unfriends.
    unfriend_response = await client.delete(
        f"/friends/{created['friend_request_id']}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert unfriend_response.status_code == 200

    # Both lists update immediately.
    assert (
        await client.get("/friends", headers={"Authorization": f"Bearer {token_a}"})
    ).json()["friends"] == []
    assert (
        await client.get("/friends", headers={"Authorization": f"Bearer {token_b}"})
    ).json()["friends"] == []

    # No new pending request exists for B to have been "notified" via —
    # only the one now-`unfriended` row exists for this pair.
    result = await db_session.execute(
        select(FriendRequest).where(FriendRequest.requester_id == member_a.id)
    )
    rows = list(result.scalars())
    assert len(rows) == 1
    assert rows[0].status == "unfriended"

    # B can resend without any limit imposed by the prior relationship.
    resend_response = await client.post(
        "/friends/requests",
        json={"addressee_user_number": member_a.user_number},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resend_response.status_code == 201
    assert resend_response.json()["status"] == "pending"
