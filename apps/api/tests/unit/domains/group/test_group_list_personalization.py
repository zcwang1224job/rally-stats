"""Unit test: GET /groups' joined_by_me field — null when unauthenticated,
false when logged in but not a member of that group, true when an active
member (US6, FR-006)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_and_login(client: AsyncClient, db_session: AsyncSession, email: str) -> str:
    member = await register(db_session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = "小明"
    await db_session.commit()
    login_response = await client.post(
        "/auth/login", json={"email": email, "password": "abc12345"}
    )
    return str(login_response.json()["access_token"])


async def _make_group(client: AsyncClient, valid_turnstile_token: str, name: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": name,
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "開團者",
            "turnstile_token": valid_turnstile_token,
        },
    )
    return response.json()


async def test_joined_by_me_null_when_unauthenticated(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    await _make_group(client, valid_turnstile_token, "個人化測試-未登入")

    response = await client.get("/groups")
    item = next(g for g in response.json()["groups"] if g["name"] == "個人化測試-未登入")
    assert item["joined_by_me"] is None


async def test_joined_by_me_false_when_not_a_member(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await _make_group(client, valid_turnstile_token, "個人化測試-未加入")
    access_token = await _register_and_login(client, db_session, "notmember@example.com")

    response = await client.get(
        "/groups", headers={"Authorization": f"Bearer {access_token}"}
    )
    item = next(g for g in response.json()["groups"] if g["name"] == "個人化測試-未加入")
    assert item["joined_by_me"] is False


async def test_joined_by_me_true_when_active_member(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _make_group(client, valid_turnstile_token, "個人化測試-已加入")
    access_token = await _register_and_login(client, db_session, "ismember@example.com")

    join_response = await client.post(
        f"/groups/{created['group_id']}/join",
        headers={"Authorization": f"Bearer {access_token}"},
        json={},
    )
    assert join_response.status_code == 201

    response = await client.get(
        "/groups", headers={"Authorization": f"Bearer {access_token}"}
    )
    item = next(g for g in response.json()["groups"] if g["name"] == "個人化測試-已加入")
    assert item["joined_by_me"] is True
