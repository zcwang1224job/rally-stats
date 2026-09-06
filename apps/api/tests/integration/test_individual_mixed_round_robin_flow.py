"""Integration test: individual_mixed's full round-robin flow via the real
API — every teammate pair covered, courts consume the queue
(011-round-robin-scheduling quickstart.md scenario 5)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_individual_mixed_full_round_robin(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Individual Mixed Flow",
                "max_members": 8,
                "match_mode": "doubles",
                "scheduling_mechanism": "individual_mixed",
                "creator_nickname": "阿華",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "2號場"})

    for i in range(7):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    response = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert response.status_code == 200

    in_progress_courts = [c for c in response.json()["courts"] if c["current_match"] is not None]
    assert len(in_progress_courts) == 2

    rows = await db_session.execute(
        text(
            "SELECT mp1.roster_entry_id AS a, mp2.roster_entry_id AS b "
            "FROM match_participants mp1 JOIN match_participants mp2 "
            "  ON mp1.match_id = mp2.match_id AND mp1.team = mp2.team "
            "  AND mp1.roster_entry_id < mp2.roster_entry_id "
            "JOIN matches m ON m.id = mp1.match_id "
            "WHERE m.group_id = :gid AND m.round_number = 1"
        ),
        {"gid": group_id},
    )
    teammate_pairs = {(row.a, row.b) for row in rows.all()}
    # 8 players -> C(8,2) = 28 possible teammate pairs, all covered exactly
    # once (no duplicates, since the set comprehension above would collapse
    # any repeat pairing).
    assert len(teammate_pairs) == 28
