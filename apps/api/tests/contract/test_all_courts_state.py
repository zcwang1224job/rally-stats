"""Contract test for GET /groups/by-all-courts-token/{token}/state per
contracts/scoring-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_get_all_courts_state_returns_all_courts(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "All Courts State Contract",
                "max_members": 8,
                "match_mode": "singles",
                "scheduling_mechanism": "fair_rotation",
                "creator_nickname": "阿全",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "2號場"})

    for i in range(7):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()
    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    admin_view = (
        await client.get(f"/groups/{group_id}/admin", headers=headers)
    ).json()
    all_courts_token = admin_view["all_courts_control_panel_token"]

    response = await client.get(f"/groups/by-all-courts-token/{all_courts_token}/state")

    assert response.status_code == 200
    body = response.json()
    assert body["group_id"] == group_id
    assert body["round_number"] == 1
    assert len(body["courts"]) == 2
    for court_state in body["courts"]:
        assert court_state["current_match"] is not None
        assert court_state["current_match"]["score_a"] == 0


async def test_get_all_courts_state_invalid_token(client: AsyncClient) -> None:
    response = await client.get(f"/groups/by-all-courts-token/{uuid.uuid4()}/state")
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"
