"""Contract test for GET /groups/{group_id}/partnerships and
PATCH /groups/{group_id}/partnerships per contracts/schedule-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_fixed_partner_group(
    client: AsyncClient, session: AsyncSession, token: str
) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Partnerships Contract",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fixed_partner",
            "creator_nickname": "阿修",
            "turnstile_token": token,
        },
    )
    created = response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    for i in range(3):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": created["group_id"], "nickname": f"P{i}"},
        )
    await session.commit()
    # Switching scheduling_mechanism (even to the same value) triggers no
    # auto-pair; instead we PATCH via edit_group to a no-op change that
    # still re-runs the mechanism-switch side effect deliberately, OR simply
    # rely on this group already being created as fixed_partner (create_group
    # does not auto-pair). Use PATCH to itself to trigger auto-pairing.
    await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "scheduling_mechanism": "manual"},
    )
    await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 1, "scheduling_mechanism": "fixed_partner"},
    )
    return created


async def test_get_partnerships_lists_auto_paired_members(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_fixed_partner_group(client, db_session, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    assert response.status_code == 200
    body = response.json()
    # Creator + 3 seeded = 4 members -> 2 partnerships, 0 unpaired.
    assert len(body["partnerships"]) == 2
    assert len(body["unpaired"]) == 0


async def test_get_partnerships_rejected_outside_fixed_partner_mode(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await client.post(
        "/groups",
        json={
            "name": "Non Fixed Partner",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿典",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    partnerships_response = await client.get(
        f"/groups/{created['group_id']}/partnerships", headers=headers
    )
    assert partnerships_response.status_code == 409
    assert partnerships_response.json()["error_code"] == "SCHEDULING_MECHANISM_MISMATCH"


async def test_delete_partnership_dissolves_the_last_remaining_pair(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """The reported edge case: with only two active members left, already
    partnered with each other, `PATCH .../partnerships` (swap) has no third
    person to swap with and can never make them unpaired. The dedicated
    `DELETE` endpoint must."""
    response = await client.post(
        "/groups",
        json={
            "name": "Dissolve Last Pair",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "fixed_partner",
            "creator_nickname": "阿寬",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await db_session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, :nickname, 'active', false)"
        ),
        {"id": str(uuid.uuid4()), "group_id": created["group_id"], "nickname": "P1"},
    )
    await db_session.commit()
    # Trigger the mechanism-switch side effect to auto-pair the two members.
    await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "scheduling_mechanism": "manual"},
    )
    await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 1, "scheduling_mechanism": "fixed_partner"},
    )

    before = (
        await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    ).json()
    assert len(before["partnerships"]) == 1
    player_a_id = before["partnerships"][0]["player_a"]["roster_entry_id"]

    response = await client.delete(
        f"/groups/{created['group_id']}/partnerships/{player_a_id}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["partnerships"] == []
    assert len(body["unpaired"]) == 2

    # Dissolving again (no partnership left for this member) is a 404.
    repeat = await client.delete(
        f"/groups/{created['group_id']}/partnerships/{player_a_id}", headers=headers
    )
    assert repeat.status_code == 404
    assert repeat.json()["error_code"] == "PARTNERSHIP_NOT_FOUND"


async def test_patch_partnerships_reassigns(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_fixed_partner_group(client, db_session, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    before = (
        await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    ).json()
    player_a = before["partnerships"][0]["player_a"]["roster_entry_id"]
    player_b = before["partnerships"][1]["player_a"]["roster_entry_id"]

    response = await client.patch(
        f"/groups/{created['group_id']}/partnerships",
        headers=headers,
        json={"player_a_id": player_a, "player_b_id": player_b},
    )
    assert response.status_code == 200
    body = response.json()
    reassigned_pairs = [
        {p["player_a"]["roster_entry_id"], p["player_b"]["roster_entry_id"]}
        for p in body["partnerships"]
    ]
    assert {player_a, player_b} in reassigned_pairs
