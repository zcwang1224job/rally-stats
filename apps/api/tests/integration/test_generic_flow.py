"""043 T090–T091: an "other" activity end to end — +N score steps, "end and
record the result" with draws, and the draw in standings, records and the
detail page (contracts/match-events-api.md §3, Decision 4, FR-017, FR-020,
US5)."""

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

DODGEBALL = {"sport_key": "other", "name": "躲避球"}


async def _group(
    client: AsyncClient, session: AsyncSession, token: str, **params: Any
) -> dict[str, Any]:
    created = (
        await client.post(
            "/groups",
            json={
                "max_members": 8,
                "team_size": 2,
                "sport": DODGEBALL,
                "scheduling_mechanism": "manual",
                "creator_nickname": "P0",
                "turnstile_token": token,
                **params,
            },
        )
    ).json()
    assert "group_id" in created, created
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    court = (
        await client.post(
            f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "場 A"}
        )
    ).json()
    players = [str(uuid.uuid4()) for _ in range(4)]
    for i, rid in enumerate(players):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": rid, "group_id": created["group_id"], "nickname": f"P{i + 1}"},
        )
    await session.commit()
    admin = (await client.get(f"/groups/{created['group_id']}/admin", headers=headers)).json()
    return {
        "created": created,
        "headers": headers,
        "court": court,
        "players": players,
        "all_courts_token": admin["all_courts_control_panel_token"],
    }


async def _start(client: AsyncClient, g: dict[str, Any]) -> str:
    a1, a2, b1, b2 = g["players"]
    assign = await client.post(
        f"/courts/{g['court']['court_id']}/manual-assign",
        headers=g["headers"],
        json={
            "participant_ids": g["players"],
            "teams": {a1: "A", a2: "A", b1: "B", b2: "B"},
        },
    )
    assert assign.status_code == 201, assign.text
    return str(assign.json()["match_id"])


def _urls(g: dict[str, Any], match_id: str) -> dict[str, tuple[str, dict[str, str]]]:
    court_id = g["court"]["court_id"]
    return {
        "token": (
            f"/courts/by-token/{g['court']['control_panel_token']}/matches/{match_id}",
            {},
        ),
        "admin": (
            f"/groups/{g['created']['group_id']}/courts/{court_id}/matches/{match_id}",
            g["headers"],
        ),
        "all_courts": (
            f"/groups/by-all-courts-token/{g['all_courts_token']}/courts/{court_id}"
            f"/matches/{match_id}",
            {},
        ),
    }


MANUAL = {"end_mode": "manual", "allow_draw": True, "score_steps": [1, 2]}


@pytest.mark.parametrize("face", ["token", "admin", "all_courts"])
async def test_finish_on_every_face(
    face: str,
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.domains.schedule.service.publish", publish_mock)
    g = await _group(client, db_session, valid_turnstile_token, **MANUAL)
    match_id = await _start(client, g)
    url, headers = _urls(g, match_id)[face]

    step = await client.post(f"{url}/score", headers=headers, json={"side": "A", "delta": 2})
    assert step.status_code == 200, step.text
    assert step.json()["score_a"] == 2
    await client.post(f"{url}/score", headers=headers, json={"side": "B", "delta": 2})

    finished = await client.post(f"{url}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "completed"
    assert finished.json()["winner_team"] == "D"
    ended = [c.args[2] for c in publish_mock.await_args_list if c.args[1] == "match.ended"]
    assert ended and ended[0]["winner_team"] == "D"


async def test_score_steps_and_undo(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.domains.schedule.service.publish", AsyncMock())
    g = await _group(client, db_session, valid_turnstile_token, **MANUAL)
    url = _urls(g, await _start(client, g))["token"][0]

    refused = await client.post(f"{url}/score", json={"side": "A", "delta": 3})
    assert refused.status_code == 422
    assert refused.json()["error_code"] == "SCORE_STEP_NOT_ALLOWED"
    assert (await client.post(f"{url}/score", json={"side": "A", "delta": 2})).status_code == 200
    # Generic scoring only adds; a mistake is taken back with undo.
    minus = await client.post(f"{url}/score", json={"side": "A", "delta": -2})
    assert minus.status_code == 422
    await client.post(f"{url}/score", json={"side": "B", "delta": 1})
    undone = await client.post(f"{url}/undo")
    assert undone.status_code == 200, undone.text
    assert (undone.json()["score_a"], undone.json()["score_b"]) == (2, 0)


async def test_badminton_refuses_steps_and_finish(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.domains.schedule.service.publish", AsyncMock())
    g = await _group(
        client, db_session, valid_turnstile_token, sport={"sport_key": "badminton"}
    )
    url = _urls(g, await _start(client, g))["token"][0]
    two = await client.post(f"{url}/score", json={"side": "A", "delta": 2})
    assert two.status_code == 422
    finish = await client.post(f"{url}/finish")
    assert finish.status_code == 409
    assert finish.json()["error_code"] == "FINISH_NOT_AVAILABLE"


async def test_level_score_without_draws_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.domains.schedule.service.publish", AsyncMock())
    g = await _group(
        client, db_session, valid_turnstile_token, end_mode="manual", allow_draw=False
    )
    url = _urls(g, await _start(client, g))["token"][0]
    level = await client.post(f"{url}/finish")
    assert level.status_code == 409
    assert level.json()["error_code"] == "DRAW_NOT_ALLOWED"
    await client.post(f"{url}/score", json={"side": "B", "delta": 1})
    won = await client.post(f"{url}/finish")
    assert won.json()["winner_team"] == "B"

    # /end still abandons: no result recorded.
    g2 = await _group(client, db_session, valid_turnstile_token, end_mode="manual")
    url2 = _urls(g2, await _start(client, g2))["token"][0]
    ended = await client.post(f"{url2}/end")
    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "abandoned"


async def test_target_mode_has_no_finish(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.domains.schedule.service.publish", AsyncMock())
    g = await _group(
        client,
        db_session,
        valid_turnstile_token,
        end_mode="target",
        target_score=3,
        allow_draw=False,
    )
    url = _urls(g, await _start(client, g))["token"][0]
    finish = await client.post(f"{url}/finish")
    assert finish.status_code == 409
    assert finish.json()["error_code"] == "FINISH_NOT_AVAILABLE"
    for _ in range(3):
        last = await client.post(f"{url}/score", json={"side": "A", "delta": 1})
    assert last.json()["status"] == "completed"


async def test_draw_in_standings_and_detail(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.domains.schedule.service.publish", AsyncMock())
    g = await _group(client, db_session, valid_turnstile_token, **MANUAL)
    token = {"guest_session_token": g["created"]["guest_session_token"]}
    # Standings tally rounds with a round-history row; manual assignment
    # plays in the group's current round without starting one.
    await db_session.execute(
        text(
            "INSERT INTO round_history (group_id, round_number, started_at) "
            "SELECT id, current_round_number, now() FROM groups "
            "WHERE id = :id"
        ),
        {"id": g["created"]["group_id"]},
    )
    await db_session.commit()

    draw_id = await _start(client, g)
    url = _urls(g, draw_id)["token"][0]
    await client.post(f"{url}/score", json={"side": "A", "delta": 2})
    await client.post(f"{url}/score", json={"side": "B", "delta": 1})
    await client.post(f"{url}/score", json={"side": "B", "delta": 1})
    assert (await client.post(f"{url}/finish")).json()["winner_team"] == "D"
    # The round's match list shows the draw too (a 500 before the fix).
    round_matches = await client.get(
        f"/groups/{g['created']['group_id']}/member-schedule/round-matches", params=token
    )
    assert round_matches.status_code == 200, round_matches.text
    assert [m["winner_team"] for m in round_matches.json()["matches"]] == ["D"]

    win_id = await _start(client, g)
    url = _urls(g, win_id)["token"][0]
    await client.post(f"{url}/score", json={"side": "A", "delta": 1})
    assert (await client.post(f"{url}/finish")).json()["winner_team"] == "A"

    standings = await client.get(f"/groups/{g['created']['group_id']}/standings", params=token)
    assert standings.status_code == 200, standings.text
    rows = {row["nickname"]: row for row in standings.json()["members"]}
    assert (rows["P1"]["total_wins"], rows["P1"]["total_losses"], rows["P1"]["total_draws"]) == (
        1,
        0,
        1,
    )
    assert (rows["P3"]["total_wins"], rows["P3"]["total_losses"], rows["P3"]["total_draws"]) == (
        0,
        1,
        1,
    )
    assert rows["P1"]["rank"] == 1

    records = (
        await client.get(f"/groups/{g['created']['group_id']}/match-records", params=token)
    ).json()
    assert {m["winner_team"] for m in records["matches"]} == {"A", "D"}
    players = {p["nickname"]: p for p in records["player_records"]}
    assert (players["P1"]["wins"], players["P1"]["draws"], players["P1"]["matches"]) == (1, 1, 2)
    assert players["P3"]["losses"] == 1

    detail = (
        await client.get(
            f"/groups/{g['created']['group_id']}/match-records/{draw_id}", params=token
        )
    ).json()
    assert detail["winner_team"] == "D"
    assert detail["serve_stats"] is None
    timeline, grid = detail["sections"]
    assert timeline["kind"] == "score_timeline"
    assert [(e["side"], e["delta"]) for e in timeline["data"]["events"]] == [
        ("A", 2),
        ("B", 1),
        ("B", 1),
    ]
    assert timeline["data"]["target_score"] is None
    assert grid["kind"] == "metric_grid"
    assert [m["key"] for m in grid["data"]["metrics"]] == ["points_for", "points_against", "margin"]
