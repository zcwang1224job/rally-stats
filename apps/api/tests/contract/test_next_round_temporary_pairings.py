"""Contract test for POST /groups/{group_id}/next-round's optional
`temporary_pairings` body field (017-fixed-partner-autofill,
contracts/fixed-partner-autofill-api.md)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_manual_fixed_partner_group_with_court(
    client: AsyncClient, session: AsyncSession, token: str, extra_members: int = 3
) -> dict:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Next Round Temp Pairings",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fixed_partner",
            "creator_nickname": "阿仁",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "1號場"}
    )

    for i in range(extra_members):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": created["group_id"], "nickname": f"P{i}"},
        )
    await session.commit()
    # partner_source defaults to "manual"; fixed_partner auto-pairing on
    # creation only pairs by join order, so with 4 total members two formal
    # partnerships already exist. Clear them so the round is fully unpaired.
    await session.execute(
        text("DELETE FROM partnerships WHERE group_id = :group_id"),
        {"group_id": created["group_id"]},
    )
    await session.commit()
    return created


async def test_omitted_temporary_pairings_behaves_like_before(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_manual_fixed_partner_group_with_court(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["current_round_number"] == 1


async def test_valid_temporary_pairings_are_used(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_manual_fixed_partner_group_with_court(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    unpaired = (
        await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    ).json()["unpaired"]
    assert len(unpaired) == 4
    ids = [entry["roster_entry_id"] for entry in unpaired]

    response = await client.post(
        f"/groups/{created['group_id']}/next-round",
        headers=headers,
        json={
            "temporary_pairings": [
                {"player_a_id": ids[0], "player_b_id": ids[1]},
                {"player_a_id": ids[2], "player_b_id": ids[3]},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_round_number"] == 1

    # The temporary pairing MUST NOT leak into the formal partnerships list.
    after = (
        await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    ).json()
    assert after["partnerships"] == []
    assert len(after["unpaired"]) == 4


async def test_partially_stale_temporary_pairings_do_not_fail_the_request(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_manual_fixed_partner_group_with_court(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    unpaired = (
        await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    ).json()["unpaired"]
    ids = [entry["roster_entry_id"] for entry in unpaired]

    # Make one of them formally paired in the meantime — this pairing is
    # now stale for the request below.
    await client.patch(
        f"/groups/{created['group_id']}/partnerships",
        headers=headers,
        json={"player_a_id": ids[0], "player_b_id": ids[1]},
    )

    response = await client.post(
        f"/groups/{created['group_id']}/next-round",
        headers=headers,
        json={
            "temporary_pairings": [
                {"player_a_id": ids[0], "player_b_id": ids[2]},
                {"player_a_id": ids[1], "player_b_id": ids[3]},
            ]
        },
    )
    # Stale entries are silently discarded + autofilled — MUST NOT fail the
    # whole "force-end round" request.
    assert response.status_code == 200
