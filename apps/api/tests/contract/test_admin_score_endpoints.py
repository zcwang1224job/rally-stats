"""Contract test for the admin-authenticated
POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/score|end
per contracts/scoring-api.md (research.md #10)."""

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
            "name": "Admin Score Endpoint Contract",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿義",
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
    await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)

    return created, court


async def _get_match_id(client: AsyncClient, court: dict) -> str:
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id: str = state.json()["current_match"]["match_id"]
    return match_id


async def test_admin_score_requires_admin_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    response = await client.post(
        f"/groups/{created['group_id']}/courts/{court['court_id']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 401


async def test_admin_score_with_valid_token_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/courts/{court['court_id']}/matches/{match_id}/score",
        headers=headers,
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["score_a"] == 1


async def test_admin_end_match_requires_admin_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    response = await client.post(
        f"/groups/{created['group_id']}/courts/{court['court_id']}/matches/{match_id}/end"
    )

    assert response.status_code == 401


async def test_admin_end_match_with_valid_token_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/courts/{court['court_id']}/matches/{match_id}/end",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["status"] == "abandoned"


async def test_admin_score_rejects_court_from_different_group(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)

    other_group_response = await client.post(
        "/groups",
        json={
            "name": "Other Group",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    other_created = other_group_response.json()
    other_headers = {"Authorization": f"Bearer {other_created['admin_token']}"}

    response = await client.post(
        f"/groups/{other_created['group_id']}/courts/{court['court_id']}/matches/{match_id}/score",
        headers=other_headers,
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "ADMIN_TOKEN_INVALID"
