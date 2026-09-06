"""Integration test: A searches B's user_number -> sends a friend request ->
A re-searching B sees "待回覆" (pending_outgoing), B searching A sees
"待處理" (pending_incoming) — spec.md US7 acceptance scenario 1."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def test_search_and_send_request_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    member_a = await register(db_session, "searchflowA@example.com", "abc12345")
    member_a.verification_status = "verified"
    member_a.nickname = "甲"
    member_b = await register(db_session, "searchflowB@example.com", "abc12345")
    member_b.verification_status = "verified"
    member_b.nickname = "乙"
    await db_session.commit()

    token_a = (
        await client.post(
            "/auth/login", json={"email": "searchflowA@example.com", "password": "abc12345"}
        )
    ).json()["access_token"]
    token_b = (
        await client.post(
            "/auth/login", json={"email": "searchflowB@example.com", "password": "abc12345"}
        )
    ).json()["access_token"]

    # A finds B, not yet friends.
    initial_search = await client.get(
        "/members/search",
        params={"user_number": member_b.user_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert initial_search.json()["friendship_status"] == "none"

    # A sends the request.
    await client.post(
        "/friends/requests",
        json={"addressee_user_number": member_b.user_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # A sees "pending_outgoing" for B.
    a_view = await client.get(
        "/members/search",
        params={"user_number": member_b.user_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert a_view.json()["friendship_status"] == "pending_outgoing"

    # B sees "pending_incoming" for A, and finds it in the incoming list.
    b_view = await client.get(
        "/members/search",
        params={"user_number": member_a.user_number},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert b_view.json()["friendship_status"] == "pending_incoming"

    incoming = await client.get(
        "/friends/requests/incoming", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert len(incoming.json()["requests"]) == 1
    assert incoming.json()["requests"][0]["requester"]["user_number"] == member_a.user_number
