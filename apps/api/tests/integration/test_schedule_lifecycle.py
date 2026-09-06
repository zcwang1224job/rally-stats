"""Mandatory full-lifecycle integration test (constitution principle II):
新增輪替名單成員 -> 產生 Round -> 完成/捨棄比賽 -> 自動領取下一場 -> Next Round.

Under algorithmic scheduling mechanisms, FR-005 sizes each round's selection
to exactly `courts * per_match` — round generation always saturates every
court in one pass, so there is never a leftover queued match to pull mid-
round. `advance_court_after_match_ends` correctly returning None (and the
court then showing `no_queued_match`) IS the expected "自動領取下一場" outcome
here, not a gap — the actual next-match pull only happens via the next
`generate_next_round()` call. This test exercises that whole chain."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match
from app.domains.schedule.service import advance_court_after_match_ends, round_is_complete

pytestmark = pytest.mark.asyncio


async def _seed_roster(session: AsyncSession, group_id: str, count: int) -> list[str]:
    ids = [str(uuid.uuid4()) for _ in range(count)]
    for i, pid in enumerate(ids):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": pid, "group_id": group_id, "nickname": f"P{i}"},
        )
    await session.commit()
    return ids


async def test_full_schedule_lifecycle(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Schedule Lifecycle",
            "max_members": 12,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿仁",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    court_ids = []
    for i in range(2):
        court_response = await client.post(
            f"/groups/{group_id}/courts", headers=headers, json={"name": f"場地{i}"}
        )
        court_ids.append(court_response.json()["court_id"])

    # Creator + 7 seeded = 8 -> exactly fills both doubles courts.
    await _seed_roster(db_session, group_id, 7)

    # 產生 Round: both courts should start an in_progress match.
    round_response = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert round_response.status_code == 200
    body = round_response.json()
    round_1_number = body["current_round_number"]
    in_progress = [c for c in body["courts"] if c["current_match"] is not None]
    assert len(in_progress) == 2
    match_id_a = in_progress[0]["current_match"]["match_id"]
    match_id_b = in_progress[1]["current_match"]["match_id"]

    # 新增輪替名單成員 mid-round: MUST NOT disturb the already-generated round.
    late_joiner_ids = await _seed_roster(db_session, group_id, 1)
    schedule_after_join = (await client.get(f"/groups/{group_id}/schedule", headers=headers)).json()
    assert schedule_after_join["current_round_number"] == round_1_number
    still_in_progress = [c for c in schedule_after_join["courts"] if c["current_match"] is not None]
    assert {c["current_match"]["match_id"] for c in still_in_progress} == {match_id_a, match_id_b}

    # 完成第一場比賽 (simulating 007's future +1/-1 endpoint reaching target score).
    match_a_id = uuid.UUID(match_id_a)
    match_a_result = await db_session.execute(select(Match).where(Match.id == match_a_id))
    match_a = match_a_result.scalar_one()
    match_a.status = "completed"
    await db_session.commit()

    # 自動領取下一場: nothing is queued (round generation already saturated every
    # court in one pass, per FR-005), so this correctly returns None.
    pulled = await advance_court_after_match_ends(db_session, match_a)
    await db_session.commit()
    assert pulled is None

    schedule_mid = (await client.get(f"/groups/{group_id}/schedule", headers=headers)).json()
    court_a_status = next(
        c
        for c in schedule_mid["courts"]
        if c["current_match"] is None or c["current_match"]["match_id"] != match_id_b
    )
    assert court_a_status["current_match"] is None
    assert court_a_status["waiting_reason"] == "no_queued_match"
    assert await round_is_complete(db_session, uuid.UUID(group_id), round_1_number) is False

    # 捨棄第二場比賽 (提前結束 -> abandoned, per FR-009/FR-041 unification).
    match_b_id = uuid.UUID(match_id_b)
    match_b_result = await db_session.execute(select(Match).where(Match.id == match_b_id))
    match_b = match_b_result.scalar_one()
    match_b.status = "abandoned"
    await db_session.commit()
    pulled_b = await advance_court_after_match_ends(db_session, match_b)
    await db_session.commit()
    assert pulled_b is None
    assert await round_is_complete(db_session, uuid.UUID(group_id), round_1_number) is True

    # Next Round: advances to round 2, both courts pick up new matches; the
    # mid-round joiner is now eligible for selection (not asserted who's
    # picked, only that generation succeeds and the round number advances).
    next_round_response = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert next_round_response.status_code == 200
    next_body = next_round_response.json()
    assert next_body["current_round_number"] == round_1_number + 1
    next_in_progress = [c for c in next_body["courts"] if c["current_match"] is not None]
    assert len(next_in_progress) == 2

    roster_entry_ids = {r["roster_entry_id"] for r in next_body["roster"]}
    assert late_joiner_ids[0] in roster_entry_ids
