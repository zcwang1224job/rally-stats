"""Contract test for POST /groups/{group_id}/next-round (fair_rotation
happy path) per contracts/schedule-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_group_with_court(
    client: AsyncClient, session: AsyncSession, token: str
) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Next Round Contract",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿明",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    court_response = await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "1號場"}
    )
    court = court_response.json()

    # 004 (join-group) doesn't exist yet — seed roster entries directly.
    for i in range(3):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": created["group_id"], "nickname": f"P{i}"},
        )
    await session.commit()

    return created, court


async def test_next_round_generates_matches_and_starts_courts(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, _court = await _create_group_with_court(client, db_session, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/next-round", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_round_number"] == 1
    # Creator (auto-added by create_group) + 3 seeded members = exactly 4,
    # filling the one doubles court.
    current_match = body["courts"][0]["current_match"]
    assert current_match is not None
    assert current_match["status"] == "in_progress"
    assert len(current_match["participants"]) == 4
    assert body["courts"][0]["waiting_reason"] is None


async def test_next_round_requires_admin_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, _court = await _create_group_with_court(client, db_session, valid_turnstile_token)
    response = await client.post(f"/groups/{created['group_id']}/next-round")
    assert response.status_code == 401


async def test_next_round_without_courts_returns_no_courts_available(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "No Courts Group",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿德",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    # 021-group-creation-defaults FR-006: every group starts with one
    # auto-created "球場一" court — delete it to restore the "zero courts"
    # scenario this test exercises.
    default_court = (
        await client.get(f"/groups/{created['group_id']}/courts", headers=headers)
    ).json()["courts"][0]
    await client.delete(f"/courts/{default_court['court_id']}", headers=headers)

    response = await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)
    assert response.status_code == 400
    assert response.json()["error_code"] == "NO_COURTS_AVAILABLE"
