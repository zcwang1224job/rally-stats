"""Contract test for DELETE /groups/{group_id}/members/{roster_entry_id} per
contracts/schedule-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_group_with_member(
    client: AsyncClient, session: AsyncSession, token: str
) -> tuple[dict, str]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Kick Member Contract",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿凱",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    roster_entry_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, :nickname, 'active', false)"
        ),
        {"id": roster_entry_id, "group_id": created["group_id"], "nickname": "小美"},
    )
    await session.commit()
    return created, roster_entry_id


async def test_kick_member_returns_kicked_status(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, roster_entry_id = await _create_group_with_member(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.delete(
        f"/groups/{created['group_id']}/members/{roster_entry_id}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["roster_entry_id"] == roster_entry_id
    assert body["status"] == "kicked"


async def test_kick_member_requires_admin_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, roster_entry_id = await _create_group_with_member(
        client, db_session, valid_turnstile_token
    )
    response = await client.delete(f"/groups/{created['group_id']}/members/{roster_entry_id}")
    assert response.status_code == 401


async def test_kick_member_unknown_roster_entry_returns_404(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, _roster_entry_id = await _create_group_with_member(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.delete(
        f"/groups/{created['group_id']}/members/{uuid.uuid4()}", headers=headers
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "ROSTER_ENTRY_NOT_FOUND"


async def test_kick_member_already_kicked_returns_409(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, roster_entry_id = await _create_group_with_member(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    first = await client.delete(
        f"/groups/{created['group_id']}/members/{roster_entry_id}", headers=headers
    )
    assert first.status_code == 200

    second = await client.delete(
        f"/groups/{created['group_id']}/members/{roster_entry_id}", headers=headers
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "ROSTER_ENTRY_ALREADY_LEFT"
