"""Integration test: a user plays as a Guest, later registers and joins the
same group again as a Member -> their member match records never include
the Guest-era match, even though it's the "same person" (005-member-view
US5, research.md #9)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match

pytestmark = pytest.mark.asyncio


async def test_guest_era_matches_excluded_after_later_registration(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Guest To Member Flow",
            "max_members": 6,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "P0",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    court_response = await client.post(
        f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"}
    )
    court_id = court_response.json()["court_id"]

    guest = (await client.post(f"/groups/{group_id}/join", json={"nickname": "小美"})).json()

    p0_id_result = await db_session.execute(
        text("SELECT id FROM roster_entries WHERE group_id = :gid AND nickname = 'P0'"),
        {"gid": group_id},
    )
    p0_id = str(p0_id_result.scalar_one())
    guest_id = guest["roster_entry_id"]

    assign = await client.post(
        f"/courts/{court_id}/manual-assign",
        headers=headers,
        json={"participant_ids": [p0_id, guest_id], "teams": {p0_id: "A", guest_id: "B"}},
    )
    match_id = assign.json()["match_id"]

    match_result = await db_session.execute(select(Match).where(Match.id == uuid.UUID(match_id)))
    match = match_result.scalar_one()
    match.status = "completed"
    match.winner_team = "B"
    await db_session.commit()

    # The Guest now registers as a Member and logs in.
    register_response = await client.post(
        "/auth/register",
        json={
            "email": "was-a-guest@example.com",
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert register_response.status_code == 201
    login_response = await client.post(
        "/auth/login", json={"email": "was-a-guest@example.com", "password": "abc12345"}
    )
    access_token = login_response.json()["access_token"]
    member_headers = {"Authorization": f"Bearer {access_token}"}

    matches_response = await client.get(
        "/members/me/match-records", headers=member_headers
    )
    assert matches_response.status_code == 200
    body = matches_response.json()
    assert body["matches"] == []
    assert body["total_matches"] == 0
