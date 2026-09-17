"""Contract test for GET /groups/{group_id}/match-records/{match_id} per
contracts/match-record-detail-api.md (016-match-score-timeline)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_group_with_active_match(
    client: AsyncClient,
    session: AsyncSession,
    token: str,
    *,
    name: str = "Match Detail Contract",
    detailed_scoring_enabled: bool = False,
) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": name,
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "scoring_mode": "custom",
            "custom_scoring": {"target_score": 3, "deuce_threshold": 2, "cap_score": 5},
            "creator_nickname": "阿翔",
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
    if detailed_scoring_enabled:
        # 032-match-record-scoring-stats: MUST be set BEFORE next-round pulls
        # a match onto the court — matches.detailed_scoring_enabled is a
        # snapshot taken at creation time (031-shot-placement-scoring).
        await session.execute(
            text("UPDATE groups SET detailed_scoring_enabled = true WHERE id = :id"),
            {"id": created["group_id"]},
        )
    await session.commit()
    session.expire_all()
    await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)

    return created, court


async def _get_match_id(client: AsyncClient, court: dict) -> str:
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id: str = state.json()["current_match"]["match_id"]
    return match_id


async def _complete_match(client: AsyncClient, court: dict, match_id: str) -> None:
    """Plays out the 3-point custom-scoring match to a natural finish via
    the real control-panel scoring endpoint (same write path production
    traffic uses), so score_events end up populated exactly like they
    would for a real match."""
    for _ in range(3):
        response = await client.post(
            f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
            json={"side": "A", "delta": 1},
        )
        assert response.status_code == 200


async def test_success_with_guest_token_returns_complete_record(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)
    await _complete_match(client, court, match_id)

    guest_join = await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})
    guest_token = guest_join.json()["guest_session_token"]

    response = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": guest_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["match_id"] == match_id
    assert body["record_completeness"] == "complete"
    assert body["score_a"] == 3
    assert body["winner_team"] == "A"
    assert len(body["events"]) == 3
    assert [e["elapsed_seconds"] for e in body["events"]] == sorted(
        e["elapsed_seconds"] for e in body["events"]
    )
    assert body["events"][0]["score_a"] == 1
    assert body["events"][-1]["score_a"] == 3


async def test_without_token_returns_membership_required(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)
    await _complete_match(client, court, match_id)

    response = await client.get(f"/groups/{created['group_id']}/match-records/{match_id}")

    assert response.status_code == 403
    assert response.json()["error_code"] == "MEMBERSHIP_REQUIRED"


async def test_incomplete_match_returns_match_not_found(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)
    guest_join = await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})
    guest_token = guest_join.json()["guest_session_token"]

    response = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": guest_token},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "MATCH_NOT_FOUND"


async def test_detailed_match_returns_shot_placement_detail_and_player_stats(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """032-match-record-scoring-stats: end-to-end through the real scoring +
    shot-placement write endpoints (same paths production traffic uses),
    then asserts the extended GET .../match-records/{match_id} response."""
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, detailed_scoring_enabled=True
    )
    match_id = await _get_match_id(client, court)
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    participants = state.json()["current_match"]["participants"]
    team_a_id = next(p["roster_entry_id"] for p in participants if p["team"] == "A")
    team_b_id = next(p["roster_entry_id"] for p in participants if p["team"] == "B")

    # Point 1: full detail (scoring + losing player + landing).
    score_1 = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )
    await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_1.json()["score_event_id"],
            "roster_entry_id": team_a_id,
            "losing_roster_entry_id": team_b_id,
            "landing_x": 0.62,
            "landing_y": 0.18,
        },
    )
    # Point 2: skipped — no shot-placement call at all.
    await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )
    # Point 3: only the scoring player recorded, no landing/losing player.
    score_3 = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )
    await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={"score_event_id": score_3.json()["score_event_id"], "roster_entry_id": team_a_id},
    )

    guest_join = await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})
    guest_token = guest_join.json()["guest_session_token"]
    response = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": guest_token},
    )

    assert response.status_code == 200
    body = response.json()
    events = body["events"]
    assert events[0]["detail"]["scoring_roster_entry_id"] == team_a_id
    assert events[0]["detail"]["losing_roster_entry_id"] == team_b_id
    assert events[0]["detail"]["landing_x"] == 0.62
    assert events[1]["detail"] is None
    assert events[2]["detail"]["scoring_roster_entry_id"] == team_a_id
    assert events[2]["detail"]["losing_roster_entry_id"] is None

    stats_by_id = {s["roster_entry_id"]: s for s in body["player_stats"]}
    assert stats_by_id[team_a_id]["scored_count"] == 2
    assert stats_by_id[team_a_id]["fault_count"] == 0
    assert stats_by_id[team_b_id]["scored_count"] == 0
    assert stats_by_id[team_b_id]["fault_count"] == 1

    # 033-match-record-derived-stats: same placements, regrouped per player —
    # totals must agree with player_stats, plotted points only where a
    # landing was actually recorded.
    landing_by_id = {p["roster_entry_id"]: p for p in body["landing_distribution"]}
    assert set(landing_by_id) == set(stats_by_id)
    assert landing_by_id[team_a_id]["scored"] == [{"x": 0.62, "y": 0.18}]
    assert landing_by_id[team_a_id]["scored_total"] == 2
    assert landing_by_id[team_b_id]["lost"] == [{"x": 0.62, "y": 0.18}]
    assert landing_by_id[team_b_id]["lost_total"] == 1


async def test_derived_stats_from_the_real_write_path(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """033-match-record-derived-stats: A, B, A, A (3:1) scored through the
    real control-panel endpoint, so the serve records are exactly what
    production writes — a snapshot taken AFTER each point. Whoever the
    random pre-match draw picked, the first point is excluded and the rest
    is fully determined: A serves points 2 and 4 (wins one), B serves point
    3 (loses it). Reading each point's OWN record instead would report
    every serve as won."""
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)
    for side in ("A", "B", "A", "A"):
        scored = await client.post(
            f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
            json={"side": side, "delta": 1},
        )
        assert scored.status_code == 200

    guest_join = await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})
    response = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": guest_join.json()["guest_session_token"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["score_a"], body["score_b"]) == (3, 1)

    serve = body["serve_stats"]
    team_a, team_b = serve["teams"]
    assert (team_a["team"], team_b["team"]) == ("A", "B")
    assert (team_a["serve_points_won"], team_a["serve_points_total"]) == (1, 2)
    assert (team_b["serve_points_won"], team_b["serve_points_total"]) == (0, 1)
    assert (team_a["receive_points_won"], team_a["receive_points_total"]) == (1, 1)
    assert (team_b["receive_points_won"], team_b["receive_points_total"]) == (1, 2)
    assert serve["excluded_points"] == 1
    assert (
        team_a["serve_points_total"] + team_b["serve_points_total"] + serve["excluded_points"]
        == body["score_a"] + body["score_b"]
    )
    assert serve["players"] == []  # singles: no separate player level

    momentum = body["momentum_stats"]
    assert [run["length"] for run in momentum["longest_runs"]] == [2, 1]
    assert [lead["margin"] for lead in momentum["max_leads"]] == [2, 0]
    assert momentum["lead_changes"] == []

    tempo = body["tempo_stats"]
    assert tempo["counted_points"] == 4
    assert tempo["longest"]["seconds"] >= tempo["average_seconds"] >= 0

    assert body["landing_distribution"] == []  # simple scoring mode

    # 034-clutch-points-player-dashboard (contracts/match-record-detail-api.md)
    clutch = body["clutch_stats"]
    assert set(clutch) == {
        "endgame_from", "endgame", "deuce", "match_points", "by_state", "comeback",
    }
    assert clutch["endgame_from"] is None and clutch["endgame"] is None  # 3-point target
    assert clutch["deuce"] is None
    assert [m["team"] for m in clutch["match_points"]] == ["A", "B"]
    assert clutch["match_points"][0] == {"team": "A", "held": 1, "converted_on": 1, "saved": 0}
    assert clutch["match_points"][1] == {"team": "B", "held": 0, "converted_on": None, "saved": 0}
    assert [state["team"] for state in clutch["by_state"]] == ["A", "B"]
    for state in clutch["by_state"]:
        assert (
            sum(state[key]["total"] for key in ("leading", "tied", "trailing"))
            == body["score_a"] + body["score_b"]
        )
        # FR-017: clutch points belong to the team, never to a player.
        assert "roster_entry_id" not in state
    # A never trailed, which is exactly B's zero max lead in momentum_stats.
    assert clutch["comeback"] is None
    assert momentum["max_leads"][1]["margin"] == 0


async def test_match_from_different_group_returns_match_not_found(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created_a, court_a = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, name="Match Detail Contract A"
    )
    match_id_a = await _get_match_id(client, court_a)
    await _complete_match(client, court_a, match_id_a)

    created_b, _court_b = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, name="Match Detail Contract B"
    )
    guest_join_b = await client.post(
        f"/groups/{created_b['group_id']}/join", json={"nickname": "小華"}
    )
    guest_token_b = guest_join_b.json()["guest_session_token"]

    response = await client.get(
        f"/groups/{created_b['group_id']}/match-records/{match_id_a}",
        params={"guest_session_token": guest_token_b},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "MATCH_NOT_FOUND"
