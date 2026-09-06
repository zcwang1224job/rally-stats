"""Integration test: switch to individual_mixed -> generate a round -> verify
two-step dispatch result (spec US5 acceptance scenario). No Partnership rows
are ever created for this mechanism — teammates re-form every round."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_individual_mixed_round_generation(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Individual Mixed Flow",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "individual_mixed",
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

    # Creator + 7 seeded = 8 members -> exactly 2 doubles matches (4 courts' worth).
    for i in range(7):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    round_response = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert round_response.status_code == 200
    body = round_response.json()

    in_progress_courts = [c for c in body["courts"] if c["current_match"] is not None]
    assert len(in_progress_courts) == 2
    for court in in_progress_courts:
        assert len(court["current_match"]["participants"]) == 4  # 2v2

    all_playing = [
        p["roster_entry_id"]
        for court in in_progress_courts
        for p in court["current_match"]["participants"]
    ]
    assert len(all_playing) == len(set(all_playing)) == 8

    # individual_mixed never persists teammate pairs as Partnerships.
    partnerships_response = await client.get(f"/groups/{group_id}/partnerships", headers=headers)
    assert partnerships_response.status_code == 409
    assert partnerships_response.json()["error_code"] == "SCHEDULING_MECHANISM_MISMATCH"
