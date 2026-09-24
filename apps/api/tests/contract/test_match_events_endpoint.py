"""043 T068: POST …/events and POST …/undo on the three scorer faces
(contracts/match-events-api.md §2, §4, §8)."""

import uuid
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _match(
    client: AsyncClient,
    db_session: AsyncSession,
    token: str,
    sport: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    created = (
        await client.post(
            "/groups",
            json={
                "max_members": 4,
                "team_size": 1,
                "sport": sport,
                "scheduling_mechanism": "manual",
                "creator_nickname": "P0",
                "turnstile_token": token,
                **extra,
            },
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]
    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "桌 1"})
    ).json()
    roster_ids = [str(uuid.uuid4()) for _ in range(2)]
    for i, rid in enumerate(roster_ids):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": rid, "group_id": group_id, "nickname": f"P{i + 1}"},
        )
    await db_session.commit()
    assign = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=headers,
        json={"participant_ids": roster_ids, "teams": {roster_ids[0]: "A", roster_ids[1]: "B"}},
    )
    assert assign.status_code == 201, assign.text
    admin_view = (await client.get(f"/groups/{group_id}/admin", headers=headers)).json()
    match_id = assign.json()["match_id"]
    return {
        "group_id": group_id,
        "headers": headers,
        "match_id": match_id,
        "token_url": (
            f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}"
        ),
        "admin_url": f"/groups/{group_id}/courts/{court['court_id']}/matches/{match_id}",
        "all_url": (
            f"/groups/by-all-courts-token/{admin_view['all_courts_control_panel_token']}"
            f"/courts/{court['court_id']}/matches/{match_id}"
        ),
    }


BILLIARDS = {"sport_key": "billiards"}
FRAME_SCORED = {"frame_scoring_enabled": True, "frame_target": 3, "frame_win_by": 2}


def _face(m: dict[str, Any], face: str) -> tuple[str, dict[str, str]]:
    if face == "token":
        return m["token_url"], {}
    if face == "admin":
        return m["admin_url"], m["headers"]
    return m["all_url"], {}


FACES = ["token", "admin", "all_courts"]


@pytest.mark.parametrize("face", FACES)
async def test_frame_end_moves_the_match_score_on_every_face(
    face: str,
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.domains.schedule.service.publish", publish_mock)
    m = await _match(client, db_session, valid_turnstile_token, BILLIARDS)
    url, headers = _face(m, face)

    response = await client.post(
        f"{url}/events",
        headers=headers,
        json={"kind": "frames.frame_end", "payload": {"winner_team": "B"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] is True
    assert (body["score_a"], body["score_b"]) == (0, 1)
    assert body["status"] == "in_progress"
    assert body["follow_up_score_event_id"]
    assert body["sport_state"]["frame_no"] == 2

    applied = [c.args[2] for c in publish_mock.await_args_list if c.args[1] == "match.eventApplied"]
    assert len(applied) == 1
    assert applied[0]["score_b"] == 1
    assert applied[0]["sport_state"]["frame_no"] == 2


async def test_undeclared_kind_is_422(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    m = await _match(client, db_session, valid_turnstile_token, BILLIARDS)
    response = await client.post(
        f"{m['token_url']}/events", json={"kind": "generic.anything", "payload": {}}
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "EVENT_KIND_NOT_ALLOWED"


async def test_badminton_has_no_events_and_refuses_undo(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    m = await _match(client, db_session, valid_turnstile_token, {"sport_key": "badminton"})
    response = await client.post(
        f"{m['token_url']}/events",
        json={"kind": "frames.frame_end", "payload": {"winner_team": "A"}},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "EVENT_KIND_NOT_ALLOWED"

    await client.post(f"{m['token_url']}/score", json={"side": "A", "delta": 1})
    undo = await client.post(f"{m['token_url']}/undo")
    assert undo.status_code == 409
    assert undo.json()["error_code"] == "UNDO_NOT_SUPPORTED"


async def test_bad_payload_is_422(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    m = await _match(client, db_session, valid_turnstile_token, BILLIARDS)
    response = await client.post(
        f"{m['token_url']}/events",
        json={"kind": "frames.frame_end", "payload": {"winner_team": "C"}},
    )
    assert response.status_code == 422


async def test_direct_points_are_refused_for_frames(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    m = await _match(client, db_session, valid_turnstile_token, BILLIARDS)
    response = await client.post(f"{m['token_url']}/score", json={"side": "A", "delta": 1})
    assert response.status_code == 422


@pytest.mark.parametrize("face", FACES)
async def test_undo_takes_back_the_last_action(
    face: str,
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.domains.schedule.service.publish", AsyncMock())
    m = await _match(client, db_session, valid_turnstile_token, BILLIARDS)
    url, headers = _face(m, face)

    nothing = await client.post(f"{url}/undo", headers=headers)
    assert nothing.status_code == 409
    assert nothing.json()["error_code"] == "NOTHING_TO_UNDO"

    for winner in ("A", "A"):
        await client.post(
            f"{url}/events",
            headers=headers,
            json={"kind": "frames.frame_end", "payload": {"winner_team": winner}},
        )
    undone = await client.post(f"{url}/undo", headers=headers)
    assert undone.status_code == 200, undone.text
    assert (undone.json()["score_a"], undone.json()["score_b"]) == (1, 0)
    assert undone.json()["sport_state"]["frame_no"] == 2


async def test_in_frame_points_end_a_frame_at_the_target(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.domains.schedule.service.publish", AsyncMock())
    m = await _match(
        client,
        db_session,
        valid_turnstile_token,
        BILLIARDS,
        type_params=FRAME_SCORED,
    )
    url = m["token_url"]

    async def point(side: str, delta: int = 1) -> dict[str, Any]:
        response = await client.post(
            f"{url}/events",
            json={"kind": "frames.frame_point", "payload": {"side": side, "delta": delta}},
        )
        assert response.status_code == 200, response.text
        return response.json()

    await point("A")
    await point("A")
    await point("B")
    await point("B")
    level = await point("A")  # 3:2, lead of 1 < win_by 2
    assert level["score_a"] == 0
    assert level["sport_state"]["frame_score_a"] == 3
    won = await point("A")  # 4:2
    assert won["score_a"] == 1
    assert won["follow_up_score_event_id"]
    assert won["sport_state"] == {
        "frame_no": 2,
        "frame_score_a": 0,
        "frame_score_b": 0,
        "frames_to_win": 5,
        "frame_scoring_enabled": True,
        "frame_target": 3,
    }

    # Undo takes back the winning point AND the frame it ended, as one action.
    undone = (await client.post(f"{url}/undo")).json()
    assert undone["score_a"] == 0
    assert undone["sport_state"]["frame_no"] == 1
    assert (undone["sport_state"]["frame_score_a"], undone["sport_state"]["frame_score_b"]) == (
        3,
        2,
    )

    floor = await client.post(
        f"{url}/events",
        json={"kind": "frames.frame_point", "payload": {"side": "B", "delta": -1}},
    )
    assert floor.status_code == 200
    minus = await client.post(
        f"{url}/events",
        json={"kind": "frames.frame_point", "payload": {"side": "B", "delta": -1}},
    )
    assert minus.status_code == 200
    below = await client.post(
        f"{url}/events",
        json={"kind": "frames.frame_point", "payload": {"side": "B", "delta": -1}},
    )
    assert below.status_code == 409


async def test_frame_points_refused_when_not_enabled(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    m = await _match(client, db_session, valid_turnstile_token, BILLIARDS)
    response = await client.post(
        f"{m['token_url']}/events",
        json={"kind": "frames.frame_point", "payload": {"side": "A", "delta": 1}},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "FRAME_SCORING_DISABLED"


async def test_reaching_the_frame_target_completes_the_match(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.domains.schedule.service.publish", publish_mock)
    m = await _match(client, db_session, valid_turnstile_token, BILLIARDS)
    end: Callable[[str], Any] = lambda winner: client.post(  # noqa: E731
        f"{m['token_url']}/events",
        json={"kind": "frames.frame_end", "payload": {"winner_team": winner}},
    )
    for winner in ("A", "B", "A", "A", "B", "A"):
        last = await end(winner)
        assert last.status_code == 200, last.text
    assert last.json()["status"] == "in_progress"
    final = await end("A")
    assert final.json()["status"] == "completed"
    assert final.json()["winner_team"] == "A"
    assert (final.json()["score_a"], final.json()["score_b"]) == (5, 2)
    assert any(c.args[1] == "match.ended" for c in publish_mock.await_args_list)

    after = await end("B")
    assert after.status_code == 409
    assert after.json()["error_code"] == "MATCH_NOT_IN_PROGRESS"
    undo = await client.post(f"{m['token_url']}/undo")
    assert undo.status_code == 409
