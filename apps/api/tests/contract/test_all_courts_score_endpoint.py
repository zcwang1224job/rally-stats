"""Contract test for
POST /groups/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}/score|end
per contracts/scoring-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_group_with_two_active_matches(
    client: AsyncClient, session: AsyncSession, token: str
) -> tuple[str, str, dict, dict]:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "All Courts Score Contract",
                "max_members": 8,
                "match_mode": "singles",
                "scheduling_mechanism": "fair_rotation",
                "creator_nickname": "阿聰",
                "turnstile_token": token,
            },
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    court1 = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()
    court2 = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "2號場"})
    ).json()

    for i in range(7):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await session.commit()
    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    admin_view = (await client.get(f"/groups/{group_id}/admin", headers=headers)).json()
    all_courts_token = admin_view["all_courts_control_panel_token"]

    return group_id, all_courts_token, court1, court2


async def test_all_courts_score_endpoint_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _group_id, all_courts_token, court1, _court2 = await _create_group_with_two_active_matches(
        client, db_session, valid_turnstile_token
    )
    state = (
        await client.get(f"/groups/by-all-courts-token/{all_courts_token}/state")
    ).json()
    match1_id = next(
        c["current_match"]["match_id"]
        for c in state["courts"]
        if c["court_id"] == court1["court_id"]
    )

    response = await client.post(
        f"/groups/by-all-courts-token/{all_courts_token}/courts/{court1['court_id']}/"
        f"matches/{match1_id}/score",
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["score_a"] == 1


async def test_all_courts_end_match_endpoint_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    _group_id, all_courts_token, court1, _court2 = await _create_group_with_two_active_matches(
        client, db_session, valid_turnstile_token
    )
    state = (
        await client.get(f"/groups/by-all-courts-token/{all_courts_token}/state")
    ).json()
    match1_id = next(
        c["current_match"]["match_id"]
        for c in state["courts"]
        if c["court_id"] == court1["court_id"]
    )

    response = await client.post(
        f"/groups/by-all-courts-token/{all_courts_token}/courts/{court1['court_id']}/"
        f"matches/{match1_id}/end"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["status"] == "abandoned"


async def test_all_courts_score_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        f"/groups/by-all-courts-token/{uuid.uuid4()}/courts/{uuid.uuid4()}/"
        f"matches/{uuid.uuid4()}/score",
        json={"side": "A", "delta": 1},
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"
