"""Contract test for GET /groups/{group_id}/schedule/matches
(011-round-robin-scheduling) — the "本輪賽程清單" admin read model."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_round_matches_lists_full_pregenerated_schedule(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Round Matches Contract",
                "max_members": 8,
                "match_mode": "singles",
                "scheduling_mechanism": "fair_rotation",
                "creator_nickname": "阿正",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    # 021-group-creation-defaults FR-006: the group already has one
    # auto-created "球場一" court — a second court would let 2 concurrent
    # matches run instead of the 1 this test expects.

    for i in range(4):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    response = await client.get(f"/groups/{group_id}/schedule/matches", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["round_number"] == 1
    assert len(body["matches"]) == 10  # C(5,2)
    statuses = {m["status"] for m in body["matches"]}
    assert statuses == {"queued", "in_progress"}
    assert sum(1 for m in body["matches"] if m["status"] == "in_progress") == 1
    for match in body["matches"]:
        assert len(match["participants"]) == 2


async def test_round_matches_requires_admin_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Round Matches No Auth",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿正",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()

    response = await client.get(f"/groups/{created['group_id']}/schedule/matches")

    assert response.status_code == 401
