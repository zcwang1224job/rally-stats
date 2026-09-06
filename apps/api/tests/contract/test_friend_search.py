"""Contract test for GET /members/search and POST /friends/requests, per
specs/006-member-friends/contracts/{member-api,friends-api}.md."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_and_verify(session: AsyncSession, email: str, nickname: str) -> str:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member.user_number


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return str(response.json()["access_token"])


async def test_search_returns_none_status_for_a_stranger(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "friendsearchc1@example.com", "小美")
    other_number = await _register_and_verify(db_session, "friendsearchc2@example.com", "小華")
    token = await _login(client, "friendsearchc1@example.com")

    response = await client.get(
        "/members/search",
        params={"user_number": other_number},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_number"] == other_number
    assert body["friendship_status"] == "none"


async def test_search_self_returns_cannot_search_self(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    own_number = await _register_and_verify(db_session, "friendsearchc3@example.com", "小美")
    token = await _login(client, "friendsearchc3@example.com")

    response = await client.get(
        "/members/search",
        params={"user_number": own_number},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CANNOT_SEARCH_SELF"


async def test_create_friend_request_then_appears_pending_both_directions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "friendsearchc4@example.com", "A")
    b_number = await _register_and_verify(db_session, "friendsearchc5@example.com", "B")
    token_a = await _login(client, "friendsearchc4@example.com")

    create_response = await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert create_response.status_code == 201
    assert create_response.json()["status"] == "pending"

    a_search_b = await client.get(
        "/members/search",
        params={"user_number": b_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert a_search_b.json()["friendship_status"] == "pending_outgoing"

    token_b = await _login(client, "friendsearchc5@example.com")
    a_number = (
        await client.get(
            "/members/me", headers={"Authorization": f"Bearer {token_a}"}
        )
    ).json()["user_number"]
    b_search_a = await client.get(
        "/members/search",
        params={"user_number": a_number},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert b_search_a.json()["friendship_status"] == "pending_incoming"

    duplicate_response = await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["error_code"] == "FRIEND_REQUEST_ALREADY_PENDING"
