"""043 T027 (research Decision 8, FR-022): moving badminton's serve logic
into the net_rally plugin must not change what a +1 / -1 publishes or
returns. Pins the full `match.scoreUpdated` payload shape and the response
body shape for a badminton match."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _badminton_match(
    client: AsyncClient, db_session: AsyncSession, token: str
) -> tuple[str, str]:
    """A manual-scheduling badminton doubles match put straight onto a court
    (the same setup as test_scoring_flow.py)."""
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Payload Pin",
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
    assign = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=headers,
        json={"participant_ids": roster_ids, "teams": teams},
    )
    assert assign.status_code == 201, assign.text
    return court["control_panel_token"], assign.json()["match_id"]


@pytest.mark.asyncio
async def test_badminton_score_payloads_keep_their_shape(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.domains.schedule.service.publish", publish_mock)
    token, match_id = await _badminton_match(client, db_session, valid_turnstile_token)
    url = f"/courts/by-token/{token}/matches/{match_id}/score"

    plus = await client.post(url, json={"side": "A", "delta": 1})
    assert plus.status_code == 200
    assert set(plus.json()) == {
        "applied", "match_id", "status", "score_a", "score_b", "winner_team",
        "score_event_id", "serve",
    }
    assert plus.json()["serve"] is not None

    minus = await client.post(url, json={"side": "A", "delta": -1})
    assert minus.status_code == 200
    assert set(minus.json()) == set(plus.json())
    assert minus.json()["serve"] is not None

    updates = [c.args[2] for c in publish_mock.await_args_list if c.args[1] == "match.scoreUpdated"]
    assert len(updates) == 2
    for payload in updates:
        assert set(payload) == {"match_id", "score_a", "score_b", "serve", "sport_state"}
        assert payload["serve"] is not None
        assert payload["sport_state"] is None
