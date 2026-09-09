"""Integration test: 017-fixed-partner-autofill end-to-end flows per
quickstart.md scenarios 1, 2, 3, 5, 6."""

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
            "name": "Fixed Partner Autofill Flow",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fixed_partner",
            "creator_nickname": "阿凱",
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
    await session.execute(
        text("DELETE FROM partnerships WHERE group_id = :group_id"),
        {"group_id": created["group_id"]},
    )
    await session.commit()
    return created


async def test_scenario1_no_manual_pairing_still_covers_everyone(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_manual_fixed_partner_group_with_court(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)
    assert response.status_code == 200

    matches = (
        await client.get(f"/groups/{created['group_id']}/schedule/matches", headers=headers)
    ).json()["matches"]
    covered = {p["roster_entry_id"] for m in matches for p in m["participants"]}
    assert len(covered) == 4


async def test_scenario2_partial_manual_pairing_autofills_the_rest(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_manual_fixed_partner_group_with_court(
        client, db_session, valid_turnstile_token, extra_members=7
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    unpaired = (
        await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    ).json()["unpaired"]
    ids = [entry["roster_entry_id"] for entry in unpaired]
    assert len(ids) == 8

    # Formally pair 2 of the 8; leave 6 unpaired.
    await client.patch(
        f"/groups/{created['group_id']}/partnerships",
        headers=headers,
        json={"player_a_id": ids[0], "player_b_id": ids[1]},
    )

    response = await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)
    assert response.status_code == 200

    matches = (
        await client.get(f"/groups/{created['group_id']}/schedule/matches", headers=headers)
    ).json()["matches"]
    covered = {p["roster_entry_id"] for m in matches for p in m["participants"]}
    assert covered == set(ids)

    after = (
        await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    ).json()
    assert len(after["partnerships"]) == 1
    reassigned_pair = {
        after["partnerships"][0]["player_a"]["roster_entry_id"],
        after["partnerships"][0]["player_b"]["roster_entry_id"],
    }
    assert reassigned_pair == {ids[0], ids[1]}


async def test_scenario3_preview_then_adjusted_result_is_adopted_verbatim(
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

    preview = await client.post(
        f"/groups/{created['group_id']}/partnerships/random-preview", headers=headers
    )
    assert preview.status_code == 200
    assert len(preview.json()["pairings"]) == 2

    # Manager adjusts to a specific chosen combination (regardless of what
    # the random preview came back with).
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

    matches = (
        await client.get(f"/groups/{created['group_id']}/schedule/matches", headers=headers)
    ).json()["matches"]
    teams = set()
    for m in matches:
        team_a = frozenset(p["roster_entry_id"] for p in m["participants"] if p["team"] == "A")
        team_b = frozenset(p["roster_entry_id"] for p in m["participants"] if p["team"] == "B")
        teams.add(team_a)
        teams.add(team_b)
    assert frozenset({ids[0], ids[1]}) in teams
    assert frozenset({ids[2], ids[3]}) in teams

    after = (
        await client.get(f"/groups/{created['group_id']}/partnerships", headers=headers)
    ).json()
    assert after["partnerships"] == []


async def test_scenario5_auto_partner_source_unaffected(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_manual_fixed_partner_group_with_court(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "partner_source": "auto"},
    )

    preview_response = await client.post(
        f"/groups/{created['group_id']}/partnerships/random-preview", headers=headers
    )
    assert preview_response.status_code == 409
    assert preview_response.json()["error_code"] == "PARTNER_SOURCE_MISMATCH"

    next_round_response = await client.post(
        f"/groups/{created['group_id']}/next-round",
        headers=headers,
        json={
            "temporary_pairings": [
                {"player_a_id": str(uuid.uuid4()), "player_b_id": str(uuid.uuid4())}
            ]
        },
    )
    assert next_round_response.status_code == 200


async def test_scenario6_stale_temporary_pairing_is_revalidated(
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

    preview = await client.post(
        f"/groups/{created['group_id']}/partnerships/random-preview", headers=headers
    )
    stale_pairings = preview.json()["pairings"]

    # One of the previewed pair's members becomes formally paired with
    # someone else before "next round" is actually called.
    first_pair = stale_pairings[0]
    remaining = [i for i in ids if i not in (
        first_pair["player_a"]["roster_entry_id"],
        first_pair["player_b"]["roster_entry_id"],
    )]
    await client.patch(
        f"/groups/{created['group_id']}/partnerships",
        headers=headers,
        json={
            "player_a_id": first_pair["player_a"]["roster_entry_id"],
            "player_b_id": remaining[0],
        },
    )

    response = await client.post(
        f"/groups/{created['group_id']}/next-round",
        headers=headers,
        json={
            "temporary_pairings": [
                {
                    "player_a_id": p["player_a"]["roster_entry_id"],
                    "player_b_id": p["player_b"]["roster_entry_id"],
                }
                for p in stale_pairings
            ]
        },
    )
    assert response.status_code == 200

    matches = (
        await client.get(f"/groups/{created['group_id']}/schedule/matches", headers=headers)
    ).json()["matches"]
    covered = {p["roster_entry_id"] for m in matches for p in m["participants"]}
    assert covered == set(ids)
