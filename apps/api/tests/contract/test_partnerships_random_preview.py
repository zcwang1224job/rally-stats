"""Contract test for POST /groups/{group_id}/partnerships/random-preview
(017-fixed-partner-autofill, contracts/fixed-partner-autofill-api.md)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_group(
    client: AsyncClient,
    session: AsyncSession,
    token: str,
    *,
    scheduling_mechanism: str = "fixed_partner",
    extra_members: int = 3,
) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Random Preview Contract",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": scheduling_mechanism,
            "creator_nickname": "阿翔",
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


async def test_preview_returns_pairings_covering_all_unpaired_members(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, db_session, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/partnerships/random-preview", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    # Creator + 3 seeded = 4 unpaired members -> 2 pairings.
    assert len(body["pairings"]) == 2
    covered_ids = {
        pairing[key]["roster_entry_id"]
        for pairing in body["pairings"]
        for key in ("player_a", "player_b")
    }
    assert len(covered_ids) == 4


async def test_preview_never_writes_to_partnerships(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, db_session, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    await client.post(f"/groups/{created['group_id']}/partnerships/random-preview", headers=headers)

    partnerships = (
        await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    ).json()
    assert partnerships["partnerships"] == []


async def test_preview_rejected_outside_fixed_partner_mode(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(
        client, db_session, valid_turnstile_token, scheduling_mechanism="fair_rotation"
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/partnerships/random-preview", headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "SCHEDULING_MECHANISM_MISMATCH"


async def test_preview_rejected_when_partner_source_is_auto(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, db_session, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "partner_source": "auto"},
    )

    response = await client.post(
        f"/groups/{created['group_id']}/partnerships/random-preview", headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "PARTNER_SOURCE_MISMATCH"


async def test_preview_requires_admin_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, db_session, valid_turnstile_token)
    response = await client.post(f"/groups/{created['group_id']}/partnerships/random-preview")
    assert response.status_code == 401
