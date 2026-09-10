"""Contract test for GET /courts/by-token/{token}/state per
contracts/scoring-api.md."""

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
