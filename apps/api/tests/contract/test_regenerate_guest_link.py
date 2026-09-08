"""Contract test for POST /groups/{group_id}/members/{roster_entry_id}/
regenerate-guest-link — constitution IV: every link-type token MUST be
independently regenerable by the admin to invalidate a leaked copy."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_and_login(client: AsyncClient, db_session: AsyncSession, email: str) -> str:
    member = await register(db_session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = "會員小華"
    await db_session.commit()
    login_response = await client.post(
        "/auth/login", json={"email": email, "password": "abc12345"}
    )
    return str(login_response.json()["access_token"])


async def _create_group_with_guest(client: AsyncClient, valid_turnstile_token: str) -> dict:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Regenerate Guest Link Contract",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    add_response = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小明"}, headers=headers
    )
    return {**created, **add_response.json()}


async def test_regenerate_guest_link_returns_a_different_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group_with_guest(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/members/{created['roster_entry_id']}"
        "/regenerate-guest-link",
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["roster_entry_id"] == created["roster_entry_id"]
    assert body["guest_session_token"] != created["guest_session_token"]


async def test_old_guest_link_stops_working_after_regeneration(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group_with_guest(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    old_token = created["guest_session_token"]

    await client.post(
        f"/groups/{created['group_id']}/members/{created['roster_entry_id']}"
        "/regenerate-guest-link",
        headers=headers,
    )

    stale_lookup = await client.get(f"/groups/by-guest-token/{old_token}")
    assert stale_lookup.status_code == 404


async def test_regenerate_guest_link_requires_admin_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group_with_guest(client, valid_turnstile_token)

    response = await client.post(
        f"/groups/{created['group_id']}/members/{created['roster_entry_id']}"
        "/regenerate-guest-link",
    )
    assert response.status_code == 401


async def test_regenerate_guest_link_unknown_roster_entry_returns_404(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group_with_guest(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/members/{uuid.uuid4()}/regenerate-guest-link",
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "ROSTER_ENTRY_NOT_FOUND"


async def test_regenerate_guest_link_rejects_a_member_entry(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """A Member's roster entry has no guest_session_token concept — there's
    nothing to regenerate."""
    group_response = await client.post(
        "/groups",
        json={
            "name": "Regen Guest Link Member",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    access_token = await _register_and_login(
        client, db_session, "regen-guest-link-member@example.com"
    )
    join_response = await client.post(
        f"/groups/{created['group_id']}/join",
        json={},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    member_roster_entry_id = join_response.json()["roster_entry_id"]

    response = await client.post(
        f"/groups/{created['group_id']}/members/{member_roster_entry_id}"
        "/regenerate-guest-link",
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "NOT_A_GUEST_ENTRY"
