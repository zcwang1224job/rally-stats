"""Contract test for POST /groups/{group_id}/join per contracts/join-api.md."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_and_login(client: AsyncClient, db_session: AsyncSession, email: str) -> str:
    member = await register(db_session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = "會員小明"
    await db_session.commit()
    login_response = await client.post(
        "/auth/login", json={"email": email, "password": "abc12345"}
    )
    return str(login_response.json()["access_token"])


async def _create_group(
    client: AsyncClient,
    valid_turnstile_token: str,
    *,
    password: str | None = None,
    max_members: int = 8,
    match_mode: str = "doubles",
) -> dict:
    payload = {
        "name": "Join Contract Group",
        "max_members": max_members,
        "match_mode": match_mode,
        "scheduling_mechanism": "manual",
        "creator_nickname": "阿明",
        "turnstile_token": valid_turnstile_token,
    }
    if password:
        payload["password"] = password
    response = await client.post("/groups", json=payload)
    return response.json()


async def test_join_as_guest_succeeds(client: AsyncClient, valid_turnstile_token: str) -> None:
    created = await _create_group(client, valid_turnstile_token)

    response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["nickname"] == "小美"
    assert body["guest_session_token"]
    assert body["created_new"] is True


async def test_join_requires_correct_password(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token, password="secret123")

    wrong_response = await client.post(
        f"/groups/{created['group_id']}/join",
        json={"password": "wrong", "nickname": "小美"},
    )
    assert wrong_response.status_code == 401
    assert wrong_response.json()["error_code"] == "GROUP_PASSWORD_INCORRECT"

    correct_response = await client.post(
        f"/groups/{created['group_id']}/join",
        json={"password": "secret123", "nickname": "小美"},
    )
    assert correct_response.status_code == 201


async def test_join_rejects_missing_nickname_for_guest(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)

    response = await client.post(f"/groups/{created['group_id']}/join", json={})
    assert response.status_code == 400
    assert response.json()["error_code"] == "NICKNAME_REQUIRED_FOR_GUEST"


async def test_join_unknown_group(client: AsyncClient) -> None:
    response = await client.post(f"/groups/{uuid.uuid4()}/join", json={"nickname": "小美"})
    assert response.status_code == 404
    assert response.json()["error_code"] == "GROUP_NOT_FOUND"


async def test_join_disbanded_group(client: AsyncClient, valid_turnstile_token: str) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.post(f"/groups/{created['group_id']}/disband", headers=headers)

    response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "GROUP_DISBANDED"


async def test_join_full_group_returns_409(client: AsyncClient, valid_turnstile_token: str) -> None:
    created = await _create_group(
        client, valid_turnstile_token, max_members=2, match_mode="singles"
    )
    await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})

    response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小華"}
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "GROUP_FULL"


async def test_join_concurrent_requests_last_slot_only_one_succeeds(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    """FR-013 scenario 4: both requests pass the (implicit) precondition of
    "the group isn't full yet" at request time, but only one can actually
    win the last slot — the other MUST be rejected at commit time, not
    silently double-booked."""
    created = await _create_group(
        client, valid_turnstile_token, max_members=2, match_mode="singles"
    )

    responses = await asyncio.gather(
        client.post(f"/groups/{created['group_id']}/join", json={"nickname": "甲"}),
        client.post(f"/groups/{created['group_id']}/join", json={"nickname": "乙"}),
    )
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 409]


async def test_join_as_member_uses_member_nickname(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    access_token = await _register_and_login(client, db_session, "memberjoin@example.com")

    response = await client.post(
        f"/groups/{created['group_id']}/join",
        headers={"Authorization": f"Bearer {access_token}"},
        json={},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["nickname"] == "會員小明"
    assert body["guest_session_token"] is None


async def test_join_as_member_without_nickname_rejected(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    member = await register(db_session, "nonickname@example.com", "abc12345")
    member.verification_status = "verified"
    await db_session.commit()
    login_response = await client.post(
        "/auth/login", json={"email": "nonickname@example.com", "password": "abc12345"}
    )
    access_token = login_response.json()["access_token"]

    response = await client.post(
        f"/groups/{created['group_id']}/join",
        headers={"Authorization": f"Bearer {access_token}"},
        json={},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "MEMBER_NICKNAME_NOT_SET"


async def test_join_as_member_already_active_short_circuits(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    access_token = await _register_and_login(client, db_session, "shortcircuit@example.com")
    headers = {"Authorization": f"Bearer {access_token}"}

    first_response = await client.post(
        f"/groups/{created['group_id']}/join", headers=headers, json={}
    )
    assert first_response.json()["created_new"] is True

    second_response = await client.post(
        f"/groups/{created['group_id']}/join", headers=headers, json={}
    )
    assert second_response.status_code == 201
    assert second_response.json()["created_new"] is False
    assert (
        second_response.json()["roster_entry_id"] == first_response.json()["roster_entry_id"]
    )
