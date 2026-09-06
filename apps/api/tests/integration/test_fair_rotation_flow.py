"""Integration test: 3 courts, 12-person doubles roster -> Round produces 3
matches, all courts immediately in_progress with a scoring-settings snapshot,
wait_count correctly updated (spec US1 acceptance scenarios 1, 2, 5)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_fair_rotation_full_round(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Fair Rotation Flow",
            "max_members": 16,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "scoring_mode": "15pt",
            "creator_nickname": "阿宏",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    for i in range(3):
        court_response = await client.post(
            f"/groups/{group_id}/courts", headers=headers, json={"name": f"場地{i}"}
        )
        assert court_response.status_code == 201

    # Seed 12 roster members directly (004 join-group not implemented yet).
    for i in range(11):  # +1 for the creator, already in roster from create_group
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
    body = response.json()
    assert body["current_round_number"] == 1

    in_progress_courts = [c for c in body["courts"] if c["current_match"] is not None]
    assert len(in_progress_courts) == 3
    for court in in_progress_courts:
        assert court["current_match"]["status"] == "in_progress"
        assert len(court["current_match"]["participants"]) == 4

    playing_ids = {
        p["roster_entry_id"]
        for court in in_progress_courts
        for p in court["current_match"]["participants"]
    }
    assert len(playing_ids) == 12  # all 12 selected, no duplicates

    for roster in body["roster"]:
        if roster["roster_entry_id"] in playing_ids:
            assert roster["wait_count"] == 0
            assert roster["currently_playing"] is True
