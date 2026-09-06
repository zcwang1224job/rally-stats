"""Contract test for GET /members/me/groups and
POST /groups/{group_id}/forgot-admin-pin, per
specs/006-member-friends/contracts/{member-api,forgot-admin-pin-api}.md."""

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


async def test_my_groups_and_forgot_admin_pin_contract(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await _register_and_verify(db_session, "forgotpinc1@example.com", "小美")
    access_token = await _login(client, "forgotpinc1@example.com")
    headers = {"Authorization": f"Bearer {access_token}"}

    empty_groups = await client.get("/members/me/groups", headers=headers)
    assert empty_groups.status_code == 200
    assert empty_groups.json()["groups"] == []

    created = (
        await client.post(
            "/groups",
            json={
                "name": "Contract Forgot Pin",
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "turnstile_token": valid_turnstile_token,
            },
            headers=headers,
        )
    ).json()

    groups_response = await client.get("/members/me/groups", headers=headers)
    assert groups_response.status_code == 200
    groups = groups_response.json()["groups"]
    assert len(groups) == 1
    assert groups[0]["group_id"] == created["group_id"]
    assert groups[0]["status"] == "active"

    forgot_response = await client.post(
        f"/groups/{created['group_id']}/forgot-admin-pin", headers=headers
    )
    assert forgot_response.status_code == 200
    body = forgot_response.json()
    assert body["admin_pin"] != created["admin_pin"]
    assert body["admin_token"] != created["admin_token"]

    # New token works, old one doesn't.
    stale = await client.patch(
        f"/groups/{created['group_id']}",
        headers={"Authorization": f"Bearer {created['admin_token']}"},
        json={"expected_version": 0, "name": "should fail"},
    )
    assert stale.status_code == 401

    fresh = await client.patch(
        f"/groups/{created['group_id']}",
        headers={"Authorization": f"Bearer {body['admin_token']}"},
        json={"expected_version": 0, "name": "should succeed"},
    )
    assert fresh.status_code == 200


async def test_forgot_admin_pin_requires_verified_member(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    member = await register(db_session, "forgotpinc2@example.com", "abc12345")
    member.nickname = "小華"
    await db_session.commit()
    access_token = await _login(client, "forgotpinc2@example.com")
    headers = {"Authorization": f"Bearer {access_token}"}

    created = (
        await client.post(
            "/groups",
            json={
                "name": "Unverified Forgot Pin",
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "turnstile_token": valid_turnstile_token,
            },
            headers=headers,
        )
    ).json()

    response = await client.post(
        f"/groups/{created['group_id']}/forgot-admin-pin", headers=headers
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"
