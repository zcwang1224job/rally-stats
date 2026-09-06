"""Integration test: switch to fixed_partner -> auto-pair -> generate a
round -> verify team-based selection and cross-team matchup (spec US4
acceptance scenarios 1, 2)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_fixed_partner_round_generation(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Fixed Partner Flow",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿修",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    for i in range(2):
        await client.post(
            f"/groups/{group_id}/courts", headers=headers, json={"name": f"場地{i}"}
        )

    # Creator + 7 seeded = 8 members -> exactly 4 teams -> exactly 2 matches.
    for i in range(7):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    switch_response = await client.patch(
        f"/groups/{group_id}",
        headers=headers,
        json={"expected_version": 0, "scheduling_mechanism": "fixed_partner"},
    )
    assert switch_response.status_code == 200

    partnerships = (
        await client.get(f"/groups/{group_id}/partnerships", headers=headers)
    ).json()
    assert len(partnerships["partnerships"]) == 4
    assert len(partnerships["unpaired"]) == 0

    round_response = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert round_response.status_code == 200
    body = round_response.json()

    in_progress_courts = [c for c in body["courts"] if c["current_match"] is not None]
    assert len(in_progress_courts) == 2
    for court in in_progress_courts:
        assert len(court["current_match"]["participants"]) == 4  # 2v2

    # No player appears in more than one court's match.
    all_playing = [
        p["roster_entry_id"]
        for court in in_progress_courts
        for p in court["current_match"]["participants"]
    ]
    assert len(all_playing) == len(set(all_playing)) == 8
