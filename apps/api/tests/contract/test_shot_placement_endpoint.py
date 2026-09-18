"""Contract test for POST .../matches/{match_id}/shot-placement (token +
admin versions), the 032-score-then-record replacement for
031-shot-placement-scoring's old atomic score-detailed endpoint: pressing
"+" now applies a plain `+1` immediately (POST .../score, unaffected) and
this endpoint attaches landing/player detail to that already-created
ScoreEvent afterward, so match pace never waits on the detail dialog."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_group_with_detailed_match(
    client: AsyncClient,
    session: AsyncSession,
    token: str,
    group_name: str,
    *,
    detailed_scoring_enabled: bool = True,
    scoreboard_scoring_enabled: bool = False,
) -> tuple[dict, dict, str, list[str], list[str]]:
    """Manual-scheduling doubles group with detailed_scoring_enabled flipped
    on BEFORE the match is created (so the new match's own snapshot picks it
    up), one court, 4 roster entries manually assigned 2v2 -> in_progress."""
    created = (
        await client.post(
            "/groups",
            json={
                "name": group_name,
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "P0",
                "turnstile_token": token,
            },
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    await session.execute(
        text(
            "UPDATE groups SET detailed_scoring_enabled = :detailed, "
            "scoreboard_scoring_enabled = :scoreboard WHERE id = :id"
        ),
        {
            "detailed": detailed_scoring_enabled,
            "scoreboard": scoreboard_scoring_enabled,
            "id": group_id,
        },
    )
    await session.commit()
    session.expire_all()

    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()

    roster_ids = [str(uuid.uuid4()) for _ in range(4)]
    for i, rid in enumerate(roster_ids):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": rid, "group_id": group_id, "nickname": f"P{i + 1}"},
        )
    await session.commit()
    session.expire_all()

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


async def _score_by_token(client: AsyncClient, token: str, match_id: str, side: str) -> str:
    """Scores a plain +1 for `side` via the (unchanged) /score endpoint and
    returns the score_event_id — the first step of the score-then-record
    flow, exactly what the frontend does before ever opening the picker."""
    response = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/score", json={"side": side, "delta": 1}
    )
    assert response.status_code == 200, response.text
    score_event_id = response.json()["score_event_id"]
    assert score_event_id is not None
    return score_event_id


async def test_record_shot_placement_via_control_panel_token_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement Control Panel"
    )
    score_event_id = await _score_by_token(client, court["control_panel_token"], match_id, "A")

    # Team A credited -> in-bounds landing must be on B's half (x>=0.5).
    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_event_id,
            "roster_entry_id": team_a_ids[0],
            "losing_roster_entry_id": team_b_ids[0],
            "landing_x": 0.62,
            "landing_y": 0.18,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"recorded": True}


async def test_record_shot_placement_via_admin_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement Admin"
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    score_event_id = await _score_by_token(client, court["control_panel_token"], match_id, "B")

    # Team B credited -> in-bounds landing must be on A's half (x<0.5).
    response = await client.post(
        f"/groups/{created['group_id']}/courts/{court['court_id']}/matches/{match_id}/shot-placement",
        headers=headers,
        json={
            "score_event_id": score_event_id,
            "roster_entry_id": team_b_ids[0],
            "losing_roster_entry_id": team_a_ids[0],
            "landing_x": 0.3,
            "landing_y": 0.8,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"recorded": True}


async def test_record_shot_placement_via_scoreboard_token_rejected_when_not_widened(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement SB Denied",
        scoreboard_scoring_enabled=False,
    )

    response = await client.post(
        f"/courts/by-token/{court['scoreboard_token']}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": str(uuid.uuid4()),
            "roster_entry_id": team_a_ids[0],
            "losing_roster_entry_id": team_b_ids[0],
            "landing_x": 0.5,
            "landing_y": 0.5,
        },
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


async def test_record_shot_placement_via_scoreboard_token_succeeds_once_widened(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement SB Allowed",
        scoreboard_scoring_enabled=True,
    )
    score_event_id = await _score_by_token(client, court["scoreboard_token"], match_id, "A")

    response = await client.post(
        f"/courts/by-token/{court['scoreboard_token']}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_event_id,
            "roster_entry_id": team_a_ids[0],
            "losing_roster_entry_id": team_b_ids[0],
            "landing_x": 0.5,
            "landing_y": 0.5,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"recorded": True}


async def test_record_shot_placement_rejects_unknown_score_event(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement Bad Event"
    )

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": str(uuid.uuid4()),
            "roster_entry_id": team_a_ids[0],
            "losing_roster_entry_id": team_b_ids[0],
            "landing_x": 0.5,
            "landing_y": 0.5,
        },
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "SCORE_EVENT_NOT_FOUND"


async def test_record_shot_placement_rejects_scoring_player_not_on_credited_side(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement Wrong Side"
    )
    score_event_id = await _score_by_token(client, court["control_panel_token"], match_id, "A")

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_event_id,
            "roster_entry_id": team_b_ids[0],
            "losing_roster_entry_id": team_a_ids[0],
            "landing_x": 0.8,
            "landing_y": 0.5,
        },
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "SCORING_PLAYER_NOT_ON_CREDITED_SIDE"


async def test_record_shot_placement_rejects_when_detailed_scoring_not_enabled(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement Simple Mode",
        detailed_scoring_enabled=False,
    )
    score_event_id = await _score_by_token(client, court["control_panel_token"], match_id, "A")

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_event_id,
            "roster_entry_id": team_a_ids[0],
            "losing_roster_entry_id": team_b_ids[0],
            "landing_x": 0.5,
            "landing_y": 0.5,
        },
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "DETAILED_SCORING_NOT_ENABLED"


async def test_record_shot_placement_rejects_invalid_landing_coordinates(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement Bad Coordinates"
    )
    score_event_id = await _score_by_token(client, court["control_panel_token"], match_id, "A")

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_event_id,
            "roster_entry_id": team_a_ids[0],
            "losing_roster_entry_id": team_b_ids[0],
            "landing_x": 5.0,
            "landing_y": 0.5,
        },
    )

    assert response.status_code == 422


async def test_record_shot_placement_rejects_attaching_twice(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement Double Attach"
    )
    score_event_id = await _score_by_token(client, court["control_panel_token"], match_id, "A")
    payload = {
        "score_event_id": score_event_id,
        "roster_entry_id": team_a_ids[0],
        "losing_roster_entry_id": team_b_ids[0],
        "landing_x": 0.6,
        "landing_y": 0.5,
    }
    first = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json=payload,
    )
    assert first.status_code == 200

    second = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json=payload,
    )

    assert second.status_code == 422
    assert second.json()["error_code"] == "SHOT_PLACEMENT_ALREADY_RECORDED"


async def test_record_shot_placement_allows_omitting_players_and_landing(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """032-optional-shot-placement-detail: every field beyond score_event_id
    is optional — the scorer can confirm with nothing else picked at all."""
    created, court, match_id, _team_a_ids, _team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Shot Placement Bare Confirm"
    )
    score_event_id = await _score_by_token(client, court["control_panel_token"], match_id, "A")

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={"score_event_id": score_event_id},
    )

    assert response.status_code == 200
    assert response.json() == {"recorded": True}


# ---------------------------------------------------------------- 035 ending_type (T009)


async def _stored_ending_types(session: AsyncSession, match_id: str) -> list[str | None]:
    rows = await session.execute(
        text(
            "SELECT ending_type FROM shot_placement_records WHERE match_id = :id "
            "ORDER BY created_at"
        ),
        {"id": match_id},
    )
    return [row[0] for row in rows]


async def test_each_of_the_five_ending_types_is_accepted_on_its_own(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """The exact five values the frontend's ENDING_TYPES lists, in its order —
    this is the check between the two sides. Nothing but the ending is sent
    (FR-010)."""
    _created, court, match_id, _a, _b = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Ending Types"
    )
    token = court["control_panel_token"]
    kinds = ["winner", "out", "net", "serve_fault", "other_error"]

    for kind in kinds:
        # A has served since its opening point, and a serve fault always
        # favors the receiver — so that one point goes to B.
        side = "B" if kind == "serve_fault" else "A"
        score_event_id = await _score_by_token(client, token, match_id, side)
        response = await client.post(
            f"/courts/by-token/{token}/matches/{match_id}/shot-placement",
            json={"score_event_id": score_event_id, "ending_type": kind},
        )
        assert response.status_code == 200, (kind, response.text)

    assert await _stored_ending_types(db_session, match_id) == kinds


async def test_request_without_ending_type_behaves_as_before(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court, match_id, team_a_ids, team_b_ids = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Ending Omitted"
    )
    token = court["control_panel_token"]
    score_event_id = await _score_by_token(client, token, match_id, "A")

    response = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_event_id,
            "roster_entry_id": team_a_ids[0],
            "losing_roster_entry_id": team_b_ids[0],
            "landing_x": 0.62,
            "landing_y": 0.18,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"recorded": True}
    assert await _stored_ending_types(db_session, match_id) == [None]


async def test_rejects_an_ending_type_outside_the_five(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court, match_id, _a, _b = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Ending Unknown"
    )
    token = court["control_panel_token"]
    score_event_id = await _score_by_token(client, token, match_id, "A")

    response = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/shot-placement",
        json={"score_event_id": score_event_id, "ending_type": "smash"},
    )

    assert response.status_code == 422
    assert await _stored_ending_types(db_session, match_id) == []


async def test_rejects_a_winner_that_landed_out_of_bounds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court, match_id, _a, _b = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Ending Contradiction"
    )
    token = court["control_panel_token"]
    score_event_id = await _score_by_token(client, token, match_id, "A")

    response = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/shot-placement",
        json={
            "score_event_id": score_event_id,
            "landing_x": 1.1,
            "landing_y": 0.5,
            "ending_type": "winner",
        },
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "ENDING_TYPE_CONTRADICTS_LANDING"
    assert await _stored_ending_types(db_session, match_id) == []


async def test_a_recorded_ending_type_cannot_be_changed_afterwards(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court, match_id, _a, _b = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Ending Immutable"
    )
    token = court["control_panel_token"]
    score_event_id = await _score_by_token(client, token, match_id, "A")
    url = f"/courts/by-token/{token}/matches/{match_id}/shot-placement"
    await client.post(url, json={"score_event_id": score_event_id, "ending_type": "net"})

    again = await client.post(url, json={"score_event_id": score_event_id, "ending_type": "out"})

    assert again.status_code == 422
    assert again.json()["error_code"] == "SHOT_PLACEMENT_ALREADY_RECORDED"
    assert await _stored_ending_types(db_session, match_id) == ["net"]


async def test_admin_and_all_courts_endpoints_take_the_ending_type_too(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """All three endpoints share one request schema and one service function;
    this pins that none of them forgot to pass the new field through."""
    created, court, match_id, _a, _b = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Ending Three Doors"
    )
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    admin_view = (
        await client.get(f"/groups/{created['group_id']}/admin", headers=admin_headers)
    ).json()
    all_courts_token = admin_view["all_courts_control_panel_token"]
    panel_token = court["control_panel_token"]

    first = await _score_by_token(client, panel_token, match_id, "A")
    by_admin = await client.post(
        f"/groups/{created['group_id']}/courts/{court['court_id']}/matches/{match_id}"
        "/shot-placement",
        headers=admin_headers,
        json={"score_event_id": first, "ending_type": "out"},
    )
    second = await _score_by_token(client, panel_token, match_id, "B")
    by_all_courts = await client.post(
        f"/groups/by-all-courts-token/{all_courts_token}/courts/{court['court_id']}"
        f"/matches/{match_id}/shot-placement",
        json={"score_event_id": second, "ending_type": "serve_fault"},
    )

    assert (by_admin.status_code, by_all_courts.status_code) == (200, 200)
    assert await _stored_ending_types(db_session, match_id) == ["out", "serve_fault"]


async def test_minus_one_withdraws_the_ending_type_with_the_point(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court, match_id, _a, _b = await _create_group_with_detailed_match(
        client, db_session, valid_turnstile_token, "Ending Withdrawn"
    )
    token = court["control_panel_token"]
    score_event_id = await _score_by_token(client, token, match_id, "A")
    await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/shot-placement",
        json={"score_event_id": score_event_id, "ending_type": "winner"},
    )

    undo = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/score", json={"side": "A", "delta": -1}
    )

    assert undo.status_code == 200
    assert await _stored_ending_types(db_session, match_id) == []
