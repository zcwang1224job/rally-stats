"""Contract test for POST /courts/by-token/{token}/matches/{match_id}/score
per contracts/scoring-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_group_with_active_match(
    client: AsyncClient, session: AsyncSession, token: str
) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Score Endpoint Contract",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿翔",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    court_response = await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "1號場"}
    )
    court = court_response.json()

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


async def test_score_via_control_panel_token_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["score_a"] == 1
    assert body["status"] == "in_progress"


async def test_score_via_scoreboard_token_rejected(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    response = await client.post(
        f"/courts/by-token/{court['scoreboard_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


async def test_score_unknown_match_id_returns_match_not_found(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{uuid.uuid4()}/score",
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "MATCH_NOT_FOUND"


async def test_score_invalid_delta_rejected(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 2},
    )

    assert response.status_code == 422


async def test_score_terminal_match_is_noop_200(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/end",
    )

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is False
    assert body["status"] == "abandoned"
