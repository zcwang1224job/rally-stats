"""Integration test: 030-score-serve-record — 兩個「比賽轉為進行中」掛鉤
點皆完成發球狀態初始化（Foundational）、開賽 → 連續加分（含 side-out）
→ 查詢 score_serve_records 皆各自正確且不被覆蓋（US1/US2）、`-1` 不建立
紀錄也不改動發球狀態（FR-004）、連結重新產生不影響既有紀錄（FR-006
Edge Case）。對應 quickstart.md 情境 1–4、6。"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match, ScoreServeRecord

pytestmark = pytest.mark.asyncio


async def _insert_roster_entries(
    db_session: AsyncSession, group_id: str, count: int
) -> list[str]:
    roster_ids = [str(uuid.uuid4()) for _ in range(count)]
    for i, rid in enumerate(roster_ids):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": rid, "group_id": group_id, "nickname": f"P{i + 1}"},
        )
    await db_session.commit()
    return roster_ids


async def _create_doubles_match_via_manual_assign(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str, group_name: str
) -> tuple[dict, dict, dict, str, list[str], list[str]]:
    """Manual-scheduling doubles group, one court, 4 roster entries manually
    assigned 2v2 onto that court — puts the match straight to `in_progress`
    via `create_match_with_participants()` (Foundational hook #1)."""
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

    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()

    roster_ids = await _insert_roster_entries(db_session, group_id, 4)
    team_a_ids, team_b_ids = roster_ids[:2], roster_ids[2:]
    teams = {pid: "A" for pid in team_a_ids} | {pid: "B" for pid in team_b_ids}
    assign_response = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=headers,
        json={"participant_ids": roster_ids, "teams": teams},
    )
    assert assign_response.status_code == 201, assign_response.text
    match_id = assign_response.json()["match_id"]
    return created, headers, court, match_id, team_a_ids, team_b_ids


# --- Foundational: both match-start hooks initialize serve state ------------


async def test_manual_assign_initializes_serve_state(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """create_match_with_participants() hook — doubles, via manual-assign."""
    _created, _headers, _court, match_id, team_a_ids, team_b_ids = (
        await _create_doubles_match_via_manual_assign(
            client, db_session, valid_turnstile_token, "Serve Init Manual"
        )
    )

    match = (
        await db_session.execute(select(Match).where(Match.id == uuid.UUID(match_id)))
    ).scalar_one()
    assert match.serving_team in ("A", "B")
    assert str(match.team_a_reference_server_id) in team_a_ids
    assert str(match.team_b_reference_server_id) in team_b_ids

    records = (
        await db_session.execute(
            select(ScoreServeRecord).where(ScoreServeRecord.match_id == match.id)
        )
    ).scalars().all()
    # FR-007: no scoring has happened yet -> no records.
    assert records == []


async def test_pull_queued_match_initializes_serve_state(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """pull_queued_match_for_court() hook — singles, via fair_rotation's
    自動 next-round → 領取排隊比賽 flow (same as test_scoring_flow.py)."""
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Serve Init Pull Queue",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "fair_rotation",
                "creator_nickname": "P0",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]
    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()
    await _insert_roster_entries(db_session, group_id, 3)

    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    state = (await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")).json()
    match_id = state["current_match"]["match_id"]

    match = (
        await db_session.execute(select(Match).where(Match.id == uuid.UUID(match_id)))
    ).scalar_one()
    assert match.serving_team in ("A", "B")
    assert match.team_a_reference_server_id is not None
    assert match.team_b_reference_server_id is not None


# --- US1/US2: scoring creates independent, correct, non-overwritten records --


async def test_scoring_sequence_creates_independent_correct_records(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, _headers, court, match_id, team_a_ids, team_b_ids = (
        await _create_doubles_match_via_manual_assign(
            client, db_session, valid_turnstile_token, "Serve Sequence"
        )
    )
    match = (
        await db_session.execute(select(Match).where(Match.id == uuid.UUID(match_id)))
    ).scalar_one()
    serving_team = match.serving_team
    other_team = "B" if serving_team == "A" else "A"
    control_url = f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}"

    # (1) the serving team scores again -> no side-out.
    await client.post(f"{control_url}/score", json={"side": serving_team, "delta": 1})
    # (2) the other team scores -> side-out, serve passes to them.
    await client.post(f"{control_url}/score", json={"side": other_team, "delta": 1})
    # (3) that new server's team scores again -> no side-out.
    await client.post(f"{control_url}/score", json={"side": other_team, "delta": 1})

    records = (
        await db_session.execute(
            select(ScoreServeRecord)
            .where(ScoreServeRecord.match_id == match.id)
            .order_by(ScoreServeRecord.created_at)
        )
    ).scalars().all()
    assert len(records) == 3

    # (1): same server as the match's initial serve state.
    assert records[0].server_team == serving_team
    initial_server = (
        match.team_a_reference_server_id
        if serving_team == "A"
        else match.team_b_reference_server_id
    )
    assert records[0].server_roster_entry_id == initial_server

    # (2): side-out -> server_team flips; server is whichever of the other
    # team's two participants ISN'T the one who was already frozen as their
    # reference (doubles alternation, research.md Decision 2).
    assert records[1].server_team == other_team
    other_team_ids = team_a_ids if other_team == "A" else team_b_ids
    assert str(records[1].server_roster_entry_id) in other_team_ids

    # (3): same server as (2) — that team kept serving.
    assert records[2].server_team == other_team
    assert records[2].server_roster_entry_id == records[1].server_roster_entry_id

    # Every record independently carries all 4 doubles station slots.
    for record in records:
        assert record.team_a_right_roster_entry_id is not None
        assert record.team_a_left_roster_entry_id is not None
        assert record.team_b_right_roster_entry_id is not None
        assert record.team_b_left_roster_entry_id is not None

    # The first record is untouched by the later two (FR-003: not overwritten).
    assert records[0].server_team == serving_team
    assert records[0].server_roster_entry_id == initial_server


async def test_minus_one_creates_no_record_and_does_not_disturb_existing_ones(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, _headers, court, match_id, _team_a_ids, _team_b_ids = (
        await _create_doubles_match_via_manual_assign(
            client, db_session, valid_turnstile_token, "Serve Minus One"
        )
    )
    match = (
        await db_session.execute(select(Match).where(Match.id == uuid.UUID(match_id)))
    ).scalar_one()
    serving_team = match.serving_team
    control_url = f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}"

    await client.post(f"{control_url}/score", json={"side": serving_team, "delta": 1})
    records_before = (
        await db_session.execute(
            select(ScoreServeRecord).where(ScoreServeRecord.match_id == match.id)
        )
    ).scalars().all()
    assert len(records_before) == 1
    snapshot_before = (
        records_before[0].server_roster_entry_id,
        records_before[0].server_team,
        records_before[0].team_a_right_roster_entry_id,
        records_before[0].team_a_left_roster_entry_id,
        records_before[0].team_b_right_roster_entry_id,
        records_before[0].team_b_left_roster_entry_id,
    )

    await client.post(f"{control_url}/score", json={"side": serving_team, "delta": -1})

    records_after = (
        await db_session.execute(
            select(ScoreServeRecord).where(ScoreServeRecord.match_id == match.id)
        )
    ).scalars().all()
    assert len(records_after) == 1
    snapshot_after = (
        records_after[0].server_roster_entry_id,
        records_after[0].server_team,
        records_after[0].team_a_right_roster_entry_id,
        records_after[0].team_a_left_roster_entry_id,
        records_after[0].team_b_right_roster_entry_id,
        records_after[0].team_b_left_roster_entry_id,
    )
    assert snapshot_after == snapshot_before

    await db_session.refresh(match)
    assert match.serving_team == serving_team


async def test_minus_one_after_a_side_out_restores_the_pre_side_out_server(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """feature/control-panel-scoreboard-style bugfix: undoing a point that
    caused a side-out previously left match.serving_team/reference_server_id
    at their POST-point (post-swap) values while only the score rolled
    back — combined with the now-reverted score, `_build_serve_station()`
    would then compute the wrong server. `-1` must restore the live serve
    columns to exactly what they were right before the undone point, using
    the read-only ScoreServeRecord history (never itself modified, per
    FR-004) — not just leave them stale."""
    _created, _headers, court, match_id, _team_a_ids, _team_b_ids = (
        await _create_doubles_match_via_manual_assign(
            client, db_session, valid_turnstile_token, "Serve Cancel Side Out"
        )
    )
    match = (
        await db_session.execute(select(Match).where(Match.id == uuid.UUID(match_id)))
    ).scalar_one()
    serving_team = match.serving_team
    other_team = "B" if serving_team == "A" else "A"
    control_url = f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}"

    # A prior, non-side-out point first — undoing THIS match's very first
    # point is a separate, narrower edge case (see apply_score_delta()'s
    # comment): the initial random assignment is never itself snapshotted,
    # so there is nothing to fall back to. Scoring one such point first
    # gives the side-out below a real snapshot to revert to.
    await client.post(f"{control_url}/score", json={"side": serving_team, "delta": 1})
    await db_session.refresh(match)
    pre_side_out_team_a_reference = match.team_a_reference_server_id
    pre_side_out_team_b_reference = match.team_b_reference_server_id
    assert match.serving_team == serving_team

    # The receiving team wins the next rally -> a genuine side-out.
    score_response = await client.post(
        f"{control_url}/score", json={"side": other_team, "delta": 1}
    )
    assert score_response.json()["serve"]["server_team"] == other_team
    await db_session.refresh(match)
    assert match.serving_team == other_team  # sanity check: side-out really happened

    # Undo that exact (side-out) point.
    cancel_response = await client.post(
        f"{control_url}/score", json={"side": other_team, "delta": -1}
    )
    cancel_body = cancel_response.json()

    await db_session.refresh(match)
    assert match.serving_team == serving_team
    assert match.team_a_reference_server_id == pre_side_out_team_a_reference
    assert match.team_b_reference_server_id == pre_side_out_team_b_reference
    # The acting client's own response reflects the correctly-reverted
    # server directly — not the stale, just-undone one.
    assert cancel_body["serve"]["server_team"] == serving_team
    expected_server = (
        pre_side_out_team_a_reference if serving_team == "A" else pre_side_out_team_b_reference
    )
    assert cancel_body["serve"]["server_roster_entry_id"] == str(expected_server)

    # 030-score-serve-record FR-004: both prior ScoreServeRecords (the
    # first point, and the side-out point this correction just undid) are
    # read-only history — this correction must not touch either of them.
    records = (
        await db_session.execute(
            select(ScoreServeRecord)
            .where(ScoreServeRecord.match_id == match.id)
            .order_by(ScoreServeRecord.created_at)
        )
    ).scalars().all()
    assert len(records) == 2
    assert records[0].server_team == serving_team
    assert records[1].server_team == other_team


# --- Polish (E2/FR-006): link regeneration doesn't affect existing records --


async def test_link_regeneration_does_not_affect_existing_records(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, headers, court, match_id, _team_a_ids, _team_b_ids = (
        await _create_doubles_match_via_manual_assign(
            client, db_session, valid_turnstile_token, "Serve Link Regen"
        )
    )
    match = (
        await db_session.execute(select(Match).where(Match.id == uuid.UUID(match_id)))
    ).scalar_one()
    control_url = f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}"
    await client.post(f"{control_url}/score", json={"side": match.serving_team, "delta": 1})

    records_before = (
        await db_session.execute(
            select(ScoreServeRecord)
            .where(ScoreServeRecord.match_id == match.id)
            .order_by(ScoreServeRecord.created_at)
        )
    ).scalars().all()
    assert len(records_before) == 1

    await client.post(
        f"/courts/{court['court_id']}/regenerate-scoreboard-link",
        headers=headers,
        json={"expected_version": 0},
    )
    await client.post(
        f"/courts/{court['court_id']}/regenerate-control-panel-link",
        headers=headers,
        json={"expected_version": 0},
    )

    records_after = (
        await db_session.execute(
            select(ScoreServeRecord)
            .where(ScoreServeRecord.match_id == match.id)
            .order_by(ScoreServeRecord.created_at)
        )
    ).scalars().all()
    assert len(records_after) == 1
    assert records_after[0].id == records_before[0].id
    assert records_after[0].server_roster_entry_id == records_before[0].server_roster_entry_id
    assert records_after[0].created_at == records_before[0].created_at
