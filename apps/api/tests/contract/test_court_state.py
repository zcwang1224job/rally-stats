"""Contract test for GET /courts/by-token/{token}/state per
contracts/scoring-api.md.

029-serve-rotation-display: also covers `current_match.serve` — see
contracts/court-state-serve-fields.md (specs/029-serve-rotation-display/)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_doubles_match_via_manual_assign(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str, group_name: str
) -> tuple[dict, dict, str, list[str], list[str]]:
    """Manual-scheduling doubles group, one court, 4 roster entries manually
    assigned 2v2 onto that court — puts the match straight to `in_progress`
    (same pattern as 030-score-serve-record's own integration tests)."""
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


async def _create_group_with_active_match(
    client: AsyncClient,
    session: AsyncSession,
    token: str,
    *,
    scheduling_mechanism: str = "fair_rotation",
) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Court State Contract",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": scheduling_mechanism,
            "creator_nickname": "阿正",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    # 021-group-creation-defaults FR-006: the group already has one
    # auto-created "球場一" court — use that instead of adding a second one,
    # so round generation has exactly one court to assign this test's single
    # match to (a second court would otherwise compete for it).
    courts_response = await client.get(f"/groups/{created['group_id']}/courts", headers=headers)
    court = courts_response.json()["courts"][0]

    await session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, 'P0', 'active', false)"
        ),
        {"id": str(uuid.uuid4()), "group_id": created["group_id"]},
    )
    await session.commit()

    if scheduling_mechanism != "manual":
        await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)

    return created, court


async def test_get_state_via_scoreboard_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")

    assert response.status_code == 200
    body = response.json()
    assert body["link_type"] == "scoreboard"
    assert body["round_number"] == 1
    assert body["current_match"] is not None
    assert body["current_match"]["status"] == "in_progress"
    assert body["current_match"]["score_a"] == 0
    assert body["current_match"]["score_b"] == 0
    assert len(body["current_match"]["participants"]) == 2
    assert body["waiting_reason"] is None


async def test_get_state_via_control_panel_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )

    response = await client.get(f"/courts/by-token/{court['control_panel_token']}/state")

    assert response.status_code == 200
    assert response.json()["link_type"] == "control_panel"


async def test_get_state_manual_mode_waiting(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, scheduling_mechanism="manual"
    )

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")

    assert response.status_code == 200
    body = response.json()
    assert body["current_match"] is None
    assert body["waiting_reason"] == "manual_assignment"
    assert body["next_up"] is None


async def test_get_state_invalid_token_returns_link_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/courts/by-token/{uuid.uuid4()}/state")
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


async def test_get_state_algorithmic_mode_picks_up_manually_queued_match(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """A genuinely-queued, court-unassigned match for the same round doesn't
    arise from real round generation (see research.md's note on
    `_generate_fair_rotation_matches` filling courts 1:1) — this test
    inserts one directly to prove `advance_court_after_match_ends` (called
    when the court's current match ends) picks it up immediately over HTTP.
    The `next_up` preview field itself (populated only when nothing gets
    picked up) is proven in isolation by
    tests/unit/domains/schedule/test_court_live_state.py, since that state
    is unreachable here — the same queued match this test inserts gets
    claimed synchronously before any GET .../state call could observe it
    as a preview rather than the new current_match."""
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    group_id = _created["group_id"]

    p3 = str(uuid.uuid4())
    p4 = str(uuid.uuid4())
    for pid, nickname in [(p3, "小華"), (p4, "小李")]:
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": pid, "group_id": group_id, "nickname": nickname},
        )
    queued_match_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO matches (id, group_id, court_id, round_number, status, "
            "target_score, deuce_threshold, cap_score) "
            "VALUES (:id, :group_id, NULL, 1, 'queued', 21, 20, 30)"
        ),
        {"id": queued_match_id, "group_id": group_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO match_participants (id, match_id, roster_entry_id, team) "
            "VALUES (:id1, :match_id, :p3, 'A'), (:id2, :match_id, :p4, 'B')"
        ),
        {
            "id1": str(uuid.uuid4()),
            "id2": str(uuid.uuid4()),
            "match_id": queued_match_id,
            "p3": p3,
            "p4": p4,
        },
    )
    await db_session.commit()

    current_match_id = (
        await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    ).json()["current_match"]["match_id"]
    await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{current_match_id}/end"
    )

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")

    assert response.status_code == 200
    body = response.json()
    assert body["current_match"] is not None
    assert body["current_match"]["match_id"] == queued_match_id
    assert body["waiting_reason"] is None
    assert body["next_up"] is None


# --- 029-serve-rotation-display: current_match.serve --------------------------


async def test_get_state_serve_field_doubles(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court, _match_id, team_a_ids, team_b_ids = (
        await _create_doubles_match_via_manual_assign(
            client, db_session, valid_turnstile_token, "Court State Serve Doubles"
        )
    )

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")

    assert response.status_code == 200
    serve = response.json()["current_match"]["serve"]
    assert serve is not None
    assert serve["server_team"] in ("A", "B")
    assert serve["server_roster_entry_id"] in team_a_ids + team_b_ids
    assert serve["team_a_right_roster_entry_id"] is not None
    assert serve["team_a_left_roster_entry_id"] is not None
    assert serve["team_b_right_roster_entry_id"] is not None
    assert serve["team_b_left_roster_entry_id"] is not None
    assert {serve["team_a_right_roster_entry_id"], serve["team_a_left_roster_entry_id"]} == set(
        team_a_ids
    )
    assert {serve["team_b_right_roster_entry_id"], serve["team_b_left_roster_entry_id"]} == set(
        team_b_ids
    )
    # server_roster_entry_id must be whichever of that team's two station
    # slots corresponds to serve["server_team"].
    server_team_slots = (
        {serve["team_a_right_roster_entry_id"], serve["team_a_left_roster_entry_id"]}
        if serve["server_team"] == "A"
        else {serve["team_b_right_roster_entry_id"], serve["team_b_left_roster_entry_id"]}
    )
    assert serve["server_roster_entry_id"] in server_team_slots


async def test_get_state_serve_field_singles(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")

    assert response.status_code == 200
    serve = response.json()["current_match"]["serve"]
    assert serve is not None
    team_a_slots = [serve["team_a_right_roster_entry_id"], serve["team_a_left_roster_entry_id"]]
    team_b_slots = [serve["team_b_right_roster_entry_id"], serve["team_b_left_roster_entry_id"]]
    assert sum(slot is not None for slot in team_a_slots) == 1
    assert sum(slot is not None for slot in team_b_slots) == 1


# --- User Story 2: serve populated immediately at match start -----------------


async def test_get_state_serve_populated_immediately_at_match_start(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """No scoring call anywhere in this test — `serve` MUST already be
    non-null the moment a match becomes in_progress (FR-001/FR-002,
    already implemented and unit-tested by 030-score-serve-record; this
    confirms the API surface this feature adds correctly reflects it)."""
    _created, court, _match_id, team_a_ids, team_b_ids = (
        await _create_doubles_match_via_manual_assign(
            client, db_session, valid_turnstile_token, "Court State Serve US2"
        )
    )

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")

    assert response.status_code == 200
    serve = response.json()["current_match"]["serve"]
    assert serve is not None
    assert serve["server_roster_entry_id"] in team_a_ids + team_b_ids


# --- 031-shot-placement-scoring: detailed_scoring_enabled reflects the ------
# --- match's own snapshot, not a live read of the group's current setting --


async def test_get_state_detailed_scoring_enabled_defaults_false(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")

    assert response.status_code == 200
    assert response.json()["current_match"]["detailed_scoring_enabled"] is False


async def test_get_state_detailed_scoring_enabled_true_when_set_before_match_created(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Court State Detailed Scoring",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿正",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    courts_response = await client.get(f"/groups/{created['group_id']}/courts", headers=headers)
    court = courts_response.json()["courts"][0]

    await db_session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, 'P0', 'active', false)"
        ),
        {"id": str(uuid.uuid4()), "group_id": created["group_id"]},
    )
    await db_session.execute(
        text("UPDATE groups SET detailed_scoring_enabled = true WHERE id = :id"),
        {"id": created["group_id"]},
    )
    await db_session.commit()
    # expire_on_commit=False (conftest.py) means the Group object loaded
    # earlier in this request cycle (group creation) keeps its stale
    # in-memory detailed_scoring_enabled unless explicitly expired — the
    # raw UPDATE above bypasses the ORM and doesn't invalidate it on its own
    # (same pattern as tests/unit/scheduler/test_auto_disband.py).
    db_session.expire_all()
    await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")

    assert response.status_code == 200
    assert response.json()["current_match"]["detailed_scoring_enabled"] is True


async def test_get_state_detailed_scoring_enabled_reflects_snapshot_at_creation(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """The match's detailed_scoring_enabled MUST come from its own snapshot
    (taken when it was created), not a live read of the group's current
    setting — flip the group's setting on AFTER the match already exists and
    confirm the already-created match still reports False (FR-006)."""
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    group_id = _created["group_id"]

    await db_session.execute(
        text("UPDATE groups SET detailed_scoring_enabled = true WHERE id = :id"),
        {"id": group_id},
    )
    await db_session.commit()

    response = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")

    assert response.status_code == 200
    assert response.json()["current_match"]["detailed_scoring_enabled"] is False
