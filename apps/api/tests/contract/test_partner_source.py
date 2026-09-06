"""Contract test for PATCH /groups/{group_id}'s new `partner_source` field
and POST /groups/{group_id}/next-round's new
FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT error
(011-round-robin-scheduling contracts/schedule-api-amendments.md)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_fixed_partner_group(
    client: AsyncClient, session: AsyncSession, token: str, extra_members: int
) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Partner Source Contract",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fixed_partner",
            "creator_nickname": "阿修",
            "turnstile_token": token,
        },
    )
    created = response.json()
    for i in range(extra_members):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": created["group_id"], "nickname": f"P{i}"},
        )
    await session.commit()
    return created


async def test_patch_group_toggles_partner_source(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_fixed_partner_group(client, db_session, valid_turnstile_token, 3)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "partner_source": "auto"},
    )
    assert response.status_code == 200
    assert response.json()["group"]["partner_source"] == "auto"

    response2 = await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 1, "partner_source": "manual"},
    )
    assert response2.status_code == 200
    assert response2.json()["group"]["partner_source"] == "manual"


async def test_next_round_rejects_odd_headcount_for_fixed_partner(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_fixed_partner_group(client, db_session, valid_turnstile_token, 2)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "1號場"}
    )

    # 1 (creator) + 2 seeded = 3 active members -> odd.
    response = await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)

    assert response.status_code == 400
    assert response.json()["error_code"] == "FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT"
