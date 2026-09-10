"""Contract test for POST /courts/by-token/{token}/matches/{match_id}/end
per contracts/scoring-api.md."""

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
            "name": "End Match Endpoint Contract",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": scheduling_mechanism,
            "creator_nickname": "阿豪",
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

    if scheduling_mechanism == "manual":
        for i in range(3):
            await session.execute(
                text(
                    "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                    "VALUES (:id, :group_id, :nickname, 'active', false)"
                ),
                {"id": str(uuid.uuid4()), "group_id": created["group_id"], "nickname": f"P{i}"},
            )
        await session.commit()
        roster = await session.execute(
            text("SELECT id FROM roster_entries WHERE group_id = :gid ORDER BY joined_at"),
            {"gid": created["group_id"]},
        )
        ids = [str(row[0]) for row in roster.all()]
        await client.post(
            f"/courts/{court['court_id']}/manual-assign",
            headers=headers,
            json={"participant_ids": ids[:2], "teams": {ids[0]: "A", ids[1]: "B"}},
        )
    else:
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, 'P0', 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": created["group_id"]},
        )
        await session.commit()
        await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)

    return created, court


async def _get_match_id(client: AsyncClient, court: dict) -> str:
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id: str = state.json()["current_match"]["match_id"]
    return match_id


async def test_end_match_via_control_panel_token_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/end"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["status"] == "abandoned"
    assert body["winner_team"] is None


async def test_end_match_via_scoreboard_token_rejected(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    response = await client.post(
        f"/courts/by-token/{court['scoreboard_token']}/matches/{match_id}/end"
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


async def test_end_match_already_abandoned_is_noop_200(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    first = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/end"
    )
    assert first.json()["applied"] is True

    second = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/end"
    )
    assert second.status_code == 200
    assert second.json()["applied"] is False
    assert second.json()["status"] == "abandoned"


async def test_end_match_manual_mode_shows_waiting_for_admin(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, scheduling_mechanism="manual"
    )
    match_id = await _get_match_id(client, court)

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/end"
    )
    assert response.json()["applied"] is True

    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    body = state.json()
    assert body["current_match"] is None
    assert body["waiting_reason"] == "manual_assignment"
