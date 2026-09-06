"""Contract test for POST /groups/{group_id}/creator-admin-token and the
`created_by_me` field on GET /groups — "回到我的團" for a logged-in member
who created the group, without touching the PIN (unlike forgot-admin-pin,
this MUST NOT invalidate any admin token already issued elsewhere)."""

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


async def test_creator_admin_token_does_not_invalidate_existing_admin_session(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await _register_and_verify(db_session, "creatortoken1@example.com", "小美")
    access_token = await _login(client, "creatortoken1@example.com")
    member_headers = {"Authorization": f"Bearer {access_token}"}

    created = (
        await client.post(
            "/groups",
            json={
                "name": "Creator Token Contract",
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "turnstile_token": valid_turnstile_token,
            },
            headers=member_headers,
        )
    ).json()

    response = await client.post(
        f"/groups/{created['group_id']}/creator-admin-token", headers=member_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["group_id"] == created["group_id"]

    # Both the original token (from creation) AND the newly issued one work
    # — issuing the new one MUST NOT bump admin_token_version or otherwise
    # invalidate the original, unlike forgot-admin-pin.
    original_still_works = await client.get(
        f"/groups/{created['group_id']}/admin",
        headers={"Authorization": f"Bearer {created['admin_token']}"},
    )
    assert original_still_works.status_code == 200

    new_works_too = await client.get(
        f"/groups/{created['group_id']}/admin",
        headers={"Authorization": f"Bearer {body['admin_token']}"},
    )
    assert new_works_too.status_code == 200


async def test_creator_admin_token_rejects_non_creator(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await _register_and_verify(db_session, "creatortoken2@example.com", "小美")
    creator_token = await _login(client, "creatortoken2@example.com")
    creator_headers = {"Authorization": f"Bearer {creator_token}"}
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Creator Token Contract 2",
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "turnstile_token": valid_turnstile_token,
            },
            headers=creator_headers,
        )
    ).json()

    await _register_and_verify(db_session, "creatortoken3@example.com", "小華")
    other_token = await _login(client, "creatortoken3@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = await client.post(
        f"/groups/{created['group_id']}/creator-admin-token", headers=other_headers
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "NOT_GROUP_CREATOR"


async def test_group_list_reports_created_by_me(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await _register_and_verify(db_session, "creatortoken4@example.com", "小美")
    creator_token = await _login(client, "creatortoken4@example.com")
    creator_headers = {"Authorization": f"Bearer {creator_token}"}
    await client.post(
        "/groups",
        json={
            "name": "Creator Token List",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "turnstile_token": valid_turnstile_token,
        },
        headers=creator_headers,
    )

    own_view = await client.get("/groups?page=1", headers=creator_headers)
    own_item = next(g for g in own_view.json()["groups"] if g["name"] == "Creator Token List")
    assert own_item["created_by_me"] is True
    assert own_item["joined_by_me"] is True

    await _register_and_verify(db_session, "creatortoken5@example.com", "小華")
    other_token = await _login(client, "creatortoken5@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    other_view = await client.get("/groups?page=1", headers=other_headers)
    other_item = next(g for g in other_view.json()["groups"] if g["name"] == "Creator Token List")
    assert other_item["created_by_me"] is False

    anon_view = await client.get("/groups?page=1")
    anon_item = next(g for g in anon_view.json()["groups"] if g["name"] == "Creator Token List")
    assert anon_item["created_by_me"] is None
