"""Contract test for GET /groups/{group_id}'s optional `already_joined`
field — lets a logged-in Member's join flow skip the password step for a
group they're already an active member of, without requiring auth at all
for Guests (the endpoint stays fully public otherwise)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member

pytestmark = pytest.mark.asyncio


async def _register_and_login(
    client: AsyncClient, db_session: AsyncSession, email: str, turnstile_token: str
) -> str:
    await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": turnstile_token,
        },
    )
    result = await db_session.execute(select(Member).where(Member.email == email))
    member = result.scalar_one()
    member.verification_status = "verified"
    await db_session.commit()

    login_response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return str(login_response.json()["access_token"])


async def test_already_joined_is_null_without_auth(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Already Joined Contract",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿正",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()

    response = await client.get(f"/groups/{created['group_id']}")

    assert response.status_code == 200
    assert response.json()["already_joined"] is None


async def test_already_joined_true_for_a_member_who_joined(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Already Joined Contract",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿正",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    group_id = created["group_id"]

    access_token = await _register_and_login(
        client, db_session, "already-joined@example.com", valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    await client.patch("/members/me/nickname", headers=headers, json={"nickname": "會員小張"})
    join_response = await client.post(f"/groups/{group_id}/join", headers=headers, json={})
    assert join_response.status_code == 201

    response = await client.get(f"/groups/{group_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["already_joined"] is True


async def test_already_joined_false_for_a_logged_in_member_who_has_not_joined(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Already Joined Contract",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿正",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    group_id = created["group_id"]

    access_token = await _register_and_login(
        client, db_session, "not-joined@example.com", valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {access_token}"}

    response = await client.get(f"/groups/{group_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["already_joined"] is False
