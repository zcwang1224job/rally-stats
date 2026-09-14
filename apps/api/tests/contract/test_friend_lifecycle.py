"""Contract test for GET /friends, GET /friends/requests/incoming,
POST /friends/requests/{id}/accept|reject, DELETE /friends/{id}, per
specs/006-member-friends/contracts/friends-api.md."""

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


async def test_accept_reject_list_and_unfriend_contract(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "lifecyclec1@example.com", "甲")
    await _register_and_verify(db_session, "lifecyclec2@example.com", "乙")
    token_a = await _login(client, "lifecyclec1@example.com")
    token_b = await _login(client, "lifecyclec2@example.com")

    b_number = (
        await client.get("/members/me", headers={"Authorization": f"Bearer {token_b}"})
    ).json()["user_number"]

    create_response = await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    friend_request_id = create_response.json()["friend_request_id"]

    incoming = await client.get(
        "/friends/requests/incoming", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert incoming.status_code == 200
    assert len(incoming.json()["requests"]) == 1

    accept_response = await client.post(
        f"/friends/requests/{friend_request_id}/accept",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["status"] == "accepted"

    friends_a = await client.get("/friends", headers={"Authorization": f"Bearer {token_a}"})
    friends_b = await client.get("/friends", headers={"Authorization": f"Bearer {token_b}"})
    assert len(friends_a.json()["friends"]) == 1
    assert len(friends_b.json()["friends"]) == 1
    # FriendSummary.friend_request_id is what the frontend's unfriend
    # action targets — confirm it round-trips to the id the request was
    # actually created with (research.md/contracts gap fix).
    assert friends_a.json()["friends"][0]["friend_request_id"] == friend_request_id

    unfriend_response = await client.delete(
        f"/friends/{friends_a.json()['friends'][0]['friend_request_id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert unfriend_response.status_code == 200
    assert unfriend_response.json()["status"] == "unfriended"

    friends_a_after = await client.get("/friends", headers={"Authorization": f"Bearer {token_a}"})
    friends_b_after = await client.get("/friends", headers={"Authorization": f"Bearer {token_b}"})
    assert friends_a_after.json()["friends"] == []
    assert friends_b_after.json()["friends"] == []


async def test_reject_contract(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register_and_verify(db_session, "lifecyclec3@example.com", "丙")
    await _register_and_verify(db_session, "lifecyclec4@example.com", "丁")
    token_a = await _login(client, "lifecyclec3@example.com")
    token_b = await _login(client, "lifecyclec4@example.com")
    b_number = (
        await client.get("/members/me", headers={"Authorization": f"Bearer {token_b}"})
    ).json()["user_number"]

    create_response = await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_number},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    friend_request_id = create_response.json()["friend_request_id"]

    reject_response = await client.post(
        f"/friends/requests/{friend_request_id}/reject",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    friends_a = await client.get("/friends", headers={"Authorization": f"Bearer {token_a}"})
    assert friends_a.json()["friends"] == []


# --- 026-match-record-friend-invite ---


async def test_create_friend_request_by_member_contract(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "bymemberc1@example.com", "甲")
    await _register_and_verify(db_session, "bymemberc2@example.com", "乙")
    token_a = await _login(client, "bymemberc1@example.com")
    token_b = await _login(client, "bymemberc2@example.com")
    b_id = (
        await client.get("/members/me", headers={"Authorization": f"Bearer {token_b}"})
    ).json()["member_id"]

    response = await client.post(
        "/friends/requests/by-member",
        json={"addressee_member_id": b_id},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert "friend_request_id" in response.json()

    duplicate = await client.post(
        "/friends/requests/by-member",
        json={"addressee_member_id": b_id},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error_code"] == "FRIEND_REQUEST_ALREADY_PENDING"


async def test_create_friend_request_by_member_error_mapping(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "bymemberc3@example.com", "丙")
    token_a = await _login(client, "bymemberc3@example.com")
    a_id = (
        await client.get("/members/me", headers={"Authorization": f"Bearer {token_a}"})
    ).json()["member_id"]

    not_found = await client.post(
        "/friends/requests/by-member",
        json={"addressee_member_id": "00000000-0000-0000-0000-000000000000"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert not_found.status_code == 404
    assert not_found.json()["error_code"] == "MEMBER_NOT_FOUND"

    self_invite = await client.post(
        "/friends/requests/by-member",
        json={"addressee_member_id": a_id},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert self_invite.status_code == 400
    assert self_invite.json()["error_code"] == "CANNOT_FRIEND_SELF"


async def test_invite_candidates_contract(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register_and_verify(db_session, "candc1@example.com", "甲")
    await _register_and_verify(db_session, "candc2@example.com", "乙")
    token_a = await _login(client, "candc1@example.com")
    token_b = await _login(client, "candc2@example.com")
    target_id = (
        await client.get("/members/me", headers={"Authorization": f"Bearer {token_b}"})
    ).json()["member_id"]

    response = await client.post(
        "/friends/invite-candidates",
        json={"member_ids": [target_id]},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 200
    (candidate,) = response.json()["candidates"]
    assert candidate["member_id"] == target_id
    assert candidate["friendship_status"] == "none"
    assert candidate["invite_eligible"] is True
