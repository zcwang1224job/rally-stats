"""Integration test: a match reaching a terminal state triggers auto-advance
on its court, and once the whole round is done, Auto Next Round (if enabled)
generates the next round automatically (spec US3 acceptance scenarios 1, 2)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.schedule.models import Match
from app.domains.schedule.service import (
    advance_court_after_match_ends,
    check_round_complete_and_maybe_auto_advance,
)

pytestmark = pytest.mark.asyncio


async def test_round_lifecycle_with_auto_next_round(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Round Lifecycle Flow",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿良",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})

    # Creator + 1 seeded member = exactly 2, fills the one singles court.
    await db_session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, 'P0', 'active', false)"
        ),
        {"id": str(uuid.uuid4()), "group_id": group_id},
    )
    await db_session.commit()

    await client.patch(
        f"/groups/{group_id}/auto-next-round", headers=headers, json={"enabled": True}
    )

    round1 = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert round1.json()["current_round_number"] == 1
    match_id = round1.json()["courts"][0]["current_match"]["match_id"]

    # Simulate 007's scoring endpoint marking the match complete, then the
    # two hooks 007 will call: advance_court_after_match_ends, then
    # check_round_complete_and_maybe_auto_advance.
    result = await db_session.execute(select(Match).where(Match.id == uuid.UUID(match_id)))
    match = result.scalar_one()
    match.status = "completed"
    await db_session.commit()

    pulled = await advance_court_after_match_ends(db_session, match)
    await db_session.commit()
    assert pulled is None  # nothing else queued this round (courts == players/per_match)

    group_result = await db_session.execute(
        text("SELECT current_round_number FROM groups WHERE id = :id"), {"id": group_id}
    )
    round_before = group_result.scalar_one()
    assert round_before == 1

    group_obj_result = await db_session.execute(
        select(Group).where(Group.id == uuid.UUID(group_id))
    )
    group_obj = group_obj_result.scalar_one()

    advanced = await check_round_complete_and_maybe_auto_advance(db_session, group_obj)
    await db_session.commit()
    assert advanced is True
    assert group_obj.current_round_number == 2

    schedule = await client.get(f"/groups/{group_id}/schedule", headers=headers)
    assert schedule.json()["current_round_number"] == 2
    assert schedule.json()["courts"][0]["current_match"] is not None
