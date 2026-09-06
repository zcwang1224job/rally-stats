"""Contract test for GET /groups/{group_id}/member-schedule/round-matches —
the member-view equivalent of the admin-only 本輪賽程清單 (011-round-robin-
scheduling), gated by roster membership instead of the admin token."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_member_round_matches_lists_full_pregenerated_schedule(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Member Round Matches Contract",
                "max_members": 8,
                "match_mode": "singles",
                "scheduling_mechanism": "fair_rotation",
                "creator_nickname": "阿正",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    group_id = created["group_id"]
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}

    await client.post(f"/groups/{group_id}/courts", headers=admin_headers, json={"name": "1號場"})

    for i in range(4):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    await client.post(f"/groups/{group_id}/next-round", headers=admin_headers)

    join_response = await client.post(f"/groups/{group_id}/join", json={"nickname": "旁觀者"})
    guest_token = join_response.json()["guest_session_token"]

    response = await client.get(
        f"/groups/{group_id}/member-schedule/round-matches",
        params={"guest_session_token": guest_token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["round_number"] == 1
    assert len(body["matches"]) == 10  # C(5,2)
    for match in body["matches"]:
        assert len(match["participants"]) == 2


async def test_member_round_matches_without_token_returns_membership_required(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Member Round Matches No Auth",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿正",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()

    response = await client.get(
        f"/groups/{created['group_id']}/member-schedule/round-matches"
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "MEMBERSHIP_REQUIRED"
