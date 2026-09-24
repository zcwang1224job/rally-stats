"""043 T050: a table tennis group end to end — net rally rules without
badminton's serve and shot-placement modules (FR-016, FR-025, US2)."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import ScoreServeRecord

pytestmark = pytest.mark.asyncio


async def _table_tennis_match(
    client: AsyncClient, db_session: AsyncSession, token: str
) -> tuple[dict, dict, str]:
    created = (
        await client.post(
            "/groups",
            json={
                "max_members": 4,
                "team_size": 1,
                "sport": {"sport_key": "table_tennis"},
                "scheduling_mechanism": "manual",
                "creator_nickname": "P0",
                "turnstile_token": token,
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
        json={
            "participant_ids": roster_ids,
            "teams": {roster_ids[0]: "A", roster_ids[1]: "B"},
        },
    )
    assert assign.status_code == 201, assign.text
    return created, court, assign.json()["match_id"]


async def test_no_cap_ends_only_on_a_two_point_lead(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.domains.schedule.service.publish", publish_mock)
    created, court, match_id = await _table_tennis_match(
        client, db_session, valid_turnstile_token
    )
    url = f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}"

    state = (await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")).json()
    current = state["current_match"]
    assert current["serve"] is None
    assert current["cap_score"] is None and current["target_score"] == 11
    assert state["sport"]["sport_key"] == "table_tennis"

    # 10:10, then alternate to 14:14, then A takes two in a row.
    for _ in range(10):
        await client.post(f"{url}/score", json={"side": "A", "delta": 1})
        await client.post(f"{url}/score", json={"side": "B", "delta": 1})
    for _ in range(4):
        await client.post(f"{url}/score", json={"side": "A", "delta": 1})
        last = await client.post(f"{url}/score", json={"side": "B", "delta": 1})
        assert last.json()["status"] == "in_progress"
    await client.post(f"{url}/score", json={"side": "A", "delta": 1})
    final = await client.post(f"{url}/score", json={"side": "A", "delta": 1})
    assert final.json()["status"] == "completed"
    assert (final.json()["score_a"], final.json()["score_b"]) == (16, 14)
    assert final.json()["winner_team"] == "A"

    updates = [c.args[2] for c in publish_mock.await_args_list if c.args[1] == "match.scoreUpdated"]
    assert updates and all(update["serve"] is None for update in updates)
    records = await db_session.execute(
        select(ScoreServeRecord).where(ScoreServeRecord.match_id == uuid.UUID(match_id))
    )
    assert records.scalars().all() == []

    # The creator is a guest member of the group, so their guest token reads
    # the group's match records (FR-025: score-only blocks yes, serve and
    # landing blocks no).
    detail = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": created["guest_session_token"]},
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["serve_stats"] is None
    assert body["landing_distribution"] == []
    assert body["ending_stats"] is None
    assert body["clutch_stats"] is not None
    assert body["momentum_stats"] is not None
    assert body["sport"]["sport_key"] == "table_tennis"
    assert body["sections"] == [{"kind": "net_rally.match_detail", "title_key": None, "data": None}]


async def test_shot_placement_is_refused(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court, match_id = await _table_tennis_match(
        client, db_session, valid_turnstile_token
    )
    url = f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}"
    point = (await client.post(f"{url}/score", json={"side": "A", "delta": 1})).json()
    response = await client.post(
        f"{url}/shot-placement", json={"score_event_id": point["score_event_id"]}
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "MODULE_NOT_SUPPORTED"
