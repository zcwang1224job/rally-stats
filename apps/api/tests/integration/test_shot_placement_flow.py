"""Integration test: 032-score-then-record — 開啟詳細模式 → 開賽 → 按

"+" 立即加分（不受詳細落點視窗影響節奏）→ 事後補記落點/球員細節（各自建立
獨立的 ShotPlacementRecord，正確連結各自的 ScoreEvent）→ 查詢紀錄。對應
quickstart.md 情境 2、8（031-shot-placement-scoring 的原始情境，經
032 調整為分兩步進行）。"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import ScoreEvent, ShotPlacementRecord

pytestmark = pytest.mark.asyncio


async def _create_detailed_doubles_match(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str, group_name: str
) -> tuple[dict, dict, str, list[str], list[str]]:
    created = (
        await client.post(
            "/groups",
            json={
                "name": group_name,
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "P0",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    await db_session.execute(
        text("UPDATE groups SET detailed_scoring_enabled = true WHERE id = :id"),
        {"id": group_id},
    )
    await db_session.commit()
    db_session.expire_all()

    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()

    roster_ids = [str(uuid.uuid4()) for _ in range(4)]
    for i, rid in enumerate(roster_ids):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": rid, "group_id": group_id, "nickname": f"P{i + 1}"},
        )
    await db_session.commit()
    db_session.expire_all()

    team_a_ids, team_b_ids = roster_ids[:2], roster_ids[2:]
    teams = {pid: "A" for pid in team_a_ids} | {pid: "B" for pid in team_b_ids}
    assign_response = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=headers,
        json={"participant_ids": roster_ids, "teams": teams},
    )
    assert assign_response.status_code == 201, assign_response.text
    match_id = assign_response.json()["match_id"]
    return created, court, match_id, team_a_ids, team_b_ids


async def _score_then_record(
    client: AsyncClient,
    token: str,
    match_id: str,
    side: str,
    roster_entry_id: str,
    losing_roster_entry_id: str,
    landing_x: float,
    landing_y: float,
) -> dict:
    """The real two-step flow (032-score-then-record): a plain +1 first
    (score immediately, unaffected by the detail dialog), then the
    shot-placement attach call pinned to that point's score_event_id."""
    score_response = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/score", json={"side": side, "delta": 1}
    )
    assert score_response.status_code == 200, score_response.text
    score_event_id = score_response.json()["score_event_id"]
    assert score_event_id is not None

    placement_response = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_event_id,
            "roster_entry_id": roster_entry_id,
            "losing_roster_entry_id": losing_roster_entry_id,
            "landing_x": landing_x,
            "landing_y": landing_y,
        },
    )
    assert placement_response.status_code == 200, placement_response.text
    return score_response.json()


async def test_two_detailed_points_each_create_independent_records(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_detailed_doubles_match(
        client, db_session, valid_turnstile_token, "Shot Placement Flow"
    )
    token = court["control_panel_token"]

    # Landing in B's half (x>=0.5) -> B failed to return it -> A scores.
    first = await _score_then_record(
        client, token, match_id, "A", team_a_ids[0], team_b_ids[0], 0.8, 0.4
    )
    assert first["score_a"] == 1

    # Landing in A's half (x<0.5) -> A failed to return it -> B scores.
    second = await _score_then_record(
        client, token, match_id, "B", team_b_ids[1], team_a_ids[1], 0.1, 0.1
    )
    assert second["score_b"] == 1

    events = (
        await db_session.execute(
            select(ScoreEvent)
            .where(ScoreEvent.match_id == uuid.UUID(match_id))
            .order_by(ScoreEvent.created_at)
        )
    ).scalars().all()
    assert len(events) == 2

    records = (
        await db_session.execute(
            select(ShotPlacementRecord)
            .where(ShotPlacementRecord.match_id == uuid.UUID(match_id))
            .order_by(ShotPlacementRecord.created_at)
        )
    ).scalars().all()
    assert len(records) == 2

    assert records[0].score_event_id == events[0].id
    assert str(records[0].roster_entry_id) == team_a_ids[0]
    assert str(records[0].losing_roster_entry_id) == team_b_ids[0]
    assert records[0].team == "A"
    assert records[0].landing_x == 0.8
    assert records[0].landing_y == 0.4

    assert records[1].score_event_id == events[1].id
    assert str(records[1].roster_entry_id) == team_b_ids[1]
    assert str(records[1].losing_roster_entry_id) == team_a_ids[1]
    assert records[1].team == "B"
    assert records[1].landing_x == 0.1
    assert records[1].landing_y == 0.1


async def test_score_applies_immediately_even_if_detail_is_never_recorded(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """032-score-then-record's whole point: the scorer can skip/delay the
    detail dialog (e.g. cancel it) without the point itself ever being held
    up — the score is already committed by the plain +1 alone."""
    created, court, match_id, _team_a_ids, _team_b_ids = await _create_detailed_doubles_match(
        client, db_session, valid_turnstile_token, "Shot Placement Skip Detail"
    )

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 200
    assert response.json()["score_a"] == 1
    assert response.json()["score_event_id"] is not None

    records = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == uuid.UUID(match_id))
        )
    ).scalars().all()
    assert records == []


async def test_abandoning_match_does_not_affect_existing_shot_placement_records(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """FR-009: shot-placement history for a match that gets abandoned mid-way
    MUST remain untouched (quickstart.md 情境 8)."""
    created, court, match_id, team_a_ids, team_b_ids = await _create_detailed_doubles_match(
        client, db_session, valid_turnstile_token, "Shot Placement Abandon"
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    await _score_then_record(
        client, court["control_panel_token"], match_id, "A", team_a_ids[0], team_b_ids[0], 0.5, 0.5
    )

    before = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == uuid.UUID(match_id))
        )
    ).scalars().all()
    assert len(before) == 1

    end_response = await client.post(
        f"/groups/{created['group_id']}/courts/{court['court_id']}/matches/{match_id}/end",
        headers=headers,
    )
    assert end_response.status_code == 200
    assert end_response.json()["status"] == "abandoned"

    after = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == uuid.UUID(match_id))
        )
    ).scalars().all()
    assert len(after) == 1
    assert after[0].id == before[0].id


async def test_toggling_group_setting_does_not_affect_existing_match_via_api(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """spec.md User Story 2 Acceptance Scenario 1/2, exercised through the
    real PATCH endpoint rather than a raw DB update: a match already
    in_progress before the toggle keeps its simple-mode snapshot; a match
    created afterwards picks up the new setting."""
    group_response = await client.post(
        "/groups",
        json={
            "name": "Detailed Mode Snapshot API",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "P0",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()
    roster_ids = [str(uuid.uuid4()) for _ in range(4)]
    for i, rid in enumerate(roster_ids):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": rid, "group_id": group_id, "nickname": f"P{i + 1}"},
        )
    await db_session.commit()
    teams = {pid: "A" for pid in roster_ids[:2]} | {pid: "B" for pid in roster_ids[2:]}
    existing_match = (
        await client.post(
            f"/courts/{court['court_id']}/manual-assign",
            headers=headers,
            json={"participant_ids": roster_ids, "teams": teams},
        )
    ).json()

    patch_response = await client.patch(
        f"/groups/{group_id}/detailed-scoring", headers=headers, json={"enabled": True}
    )
    assert patch_response.status_code == 200

    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    assert state.json()["current_match"]["match_id"] == existing_match["match_id"]
    assert state.json()["current_match"]["detailed_scoring_enabled"] is False

    await client.post(
        f"/groups/{group_id}/courts/{court['court_id']}/matches/{existing_match['match_id']}/end",
        headers=headers,
    )
    court2 = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "2號場"})
    ).json()
    new_roster_ids = [str(uuid.uuid4()) for _ in range(4)]
    for i, rid in enumerate(new_roster_ids):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": rid, "group_id": group_id, "nickname": f"Q{i + 1}"},
        )
    await db_session.commit()
    new_teams = {pid: "A" for pid in new_roster_ids[:2]} | {pid: "B" for pid in new_roster_ids[2:]}
    new_match = (
        await client.post(
            f"/courts/{court2['court_id']}/manual-assign",
            headers=headers,
            json={"participant_ids": new_roster_ids, "teams": new_teams},
        )
    ).json()

    new_state = await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")
    assert new_state.json()["current_match"]["match_id"] == new_match["match_id"]
    assert new_state.json()["current_match"]["detailed_scoring_enabled"] is True


async def test_full_flow_score_then_record_then_correct(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """quickstart.md 情境 3: 標落點加分 → 修正比分收回，比分與紀錄筆數皆
    正確；更早的其他落點紀錄不受影響。"""
    created, court, match_id, team_a_ids, team_b_ids = await _create_detailed_doubles_match(
        client, db_session, valid_turnstile_token, "Shot Placement Score Undo"
    )
    token = court["control_panel_token"]

    # Both land in B's half (x>=0.5) -> B failed to return -> A scores.
    first = await _score_then_record(
        client, token, match_id, "A", team_a_ids[0], team_b_ids[0], 0.85, 0.25
    )
    assert first["score_a"] == 1

    second = await _score_then_record(
        client, token, match_id, "A", team_a_ids[1], team_b_ids[1], 0.65, 0.45
    )
    assert second["score_a"] == 2

    corrected = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/score",
        json={"side": "A", "delta": -1},
    )
    assert corrected.status_code == 200
    assert corrected.json()["score_a"] == 1

    remaining = (
        await db_session.execute(
            select(ShotPlacementRecord)
            .where(ShotPlacementRecord.match_id == uuid.UUID(match_id))
            .order_by(ShotPlacementRecord.created_at)
        )
    ).scalars().all()
    assert len(remaining) == 1
    assert str(remaining[0].roster_entry_id) == team_a_ids[0]
    assert remaining[0].landing_x == 0.85
