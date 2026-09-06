"""Integration test: fixed_partner's team round-robin under both partner
sources, and that toggling between them preserves the manual pairing
untouched (011-round-robin-scheduling quickstart.md scenarios 2-4)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_PARTNERSHIPS_QUERY = text(
    "SELECT player_a_id, player_b_id FROM partnerships "
    "WHERE group_id = :gid ORDER BY id"
)


async def _partnerships(session: AsyncSession, group_id: str) -> list:
    return (await session.execute(_PARTNERSHIPS_QUERY, {"gid": group_id})).all()


async def _match_count(session: AsyncSession, group_id: str, round_number: int) -> int:
    result = await session.execute(
        text("SELECT COUNT(*) FROM matches WHERE group_id = :gid AND round_number = :rn"),
        {"gid": group_id, "rn": round_number},
    )
    return result.scalar_one()


async def test_fixed_partner_manual_then_auto_then_back_to_manual(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Fixed Partner Round Robin Flow",
                "max_members": 8,
                "match_mode": "doubles",
                "scheduling_mechanism": "fixed_partner",
                "creator_nickname": "阿修",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

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

    # Trigger the existing join-order auto-pair fallback so "manual" source
    # starts out with a real, deterministic set of 4 partnerships.
    await client.patch(
        f"/groups/{group_id}",
        headers=headers,
        json={"expected_version": 0, "scheduling_mechanism": "manual"},
    )
    await client.patch(
        f"/groups/{group_id}",
        headers=headers,
        json={"expected_version": 1, "scheduling_mechanism": "fixed_partner"},
    )

    original_partnerships = await _partnerships(db_session, group_id)
    assert len(original_partnerships) == 4

    # Manual source: round-robin over the 4 manually-configured teams.
    manual_round = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert manual_round.status_code == 200
    assert await _match_count(db_session, group_id, 1) == 6  # C(4,2)

    # Switch to auto — partnerships table MUST be untouched.
    switch_to_auto = await client.patch(
        f"/groups/{group_id}",
        headers=headers,
        json={"expected_version": 2, "partner_source": "auto"},
    )
    assert switch_to_auto.json()["group"]["partner_source"] == "auto"
    assert await _partnerships(db_session, group_id) == original_partnerships

    auto_round = await client.post(f"/groups/{group_id}/next-round", headers=headers)
    assert auto_round.status_code == 200
    assert await _match_count(db_session, group_id, 2) == 6
    assert await _partnerships(db_session, group_id) == original_partnerships

    # Switch back to manual — the original pairing is restored, unedited.
    switch_back = await client.patch(
        f"/groups/{group_id}",
        headers=headers,
        json={"expected_version": 3, "partner_source": "manual"},
    )
    assert switch_back.json()["group"]["partner_source"] == "manual"
    assert await _partnerships(db_session, group_id) == original_partnerships
