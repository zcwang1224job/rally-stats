"""Contract test for POST /courts/{court_id}/manual-assign per
contracts/schedule-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_manual_group_with_court(
    client: AsyncClient, session: AsyncSession, token: str
) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Manual Assign Contract",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿凱",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    court_response = await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "1號場"}
    )
    court = court_response.json()

    for i in range(3):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": created["group_id"], "nickname": f"P{i}"},
        )
    await session.commit()

    return created, court


async def test_manual_assign_creates_in_progress_match(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_manual_group_with_court(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    roster = await db_session.execute(
        text("SELECT id FROM roster_entries WHERE group_id = :gid ORDER BY joined_at"),
        {"gid": created["group_id"]},
    )
    ids = [str(row[0]) for row in roster.all()]
    assert len(ids) == 4

    response = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=headers,
        json={
            "participant_ids": ids,
            "teams": {ids[0]: "A", ids[1]: "A", ids[2]: "B", ids[3]: "B"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "in_progress"
    assert len(body["participants"]) == 4


async def test_manual_assign_requires_admin_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_manual_group_with_court(
        client, db_session, valid_turnstile_token
    )
    response = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        json={"participant_ids": [], "teams": {}},
    )
    assert response.status_code == 401
