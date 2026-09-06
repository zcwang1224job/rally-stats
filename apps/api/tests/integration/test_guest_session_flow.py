"""Integration test: Guest joins -> simulated page refresh (re-resolve the
Guest Session Token) -> correctly restored; the same token becomes invalid
once the group is disbanded, and separately once the Guest is kicked (US4)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import kick_member

pytestmark = pytest.mark.asyncio


async def _create_group(client: AsyncClient, valid_turnstile_token: str, name: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": name,
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    return response.json()


async def test_guest_session_restores_on_refresh(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token, "Guest Refresh Group")
    join_response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    guest_token = join_response.json()["guest_session_token"]

    restore_response = await client.get(f"/groups/by-guest-token/{guest_token}")
    assert restore_response.status_code == 200
    assert restore_response.json()["roster_entry_id"] == join_response.json()["roster_entry_id"]


async def test_guest_session_invalid_after_group_disbanded(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token, "Guest Disband Group")
    join_response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    guest_token = join_response.json()["guest_session_token"]

    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.post(f"/groups/{created['group_id']}/disband", headers=admin_headers)

    response = await client.get(f"/groups/by-guest-token/{guest_token}")
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


async def test_guest_session_invalid_after_kicked(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token, "Guest Kick Group")
    join_response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    guest_token = join_response.json()["guest_session_token"]
    roster_entry_id = join_response.json()["roster_entry_id"]

    group_result = await db_session.execute(
        select(Group).where(Group.id == created["group_id"])
    )
    group = group_result.scalar_one()
    entry_result = await db_session.execute(
        select(RosterEntry).where(RosterEntry.id == roster_entry_id)
    )
    entry = entry_result.scalar_one()
    await kick_member(db_session, group, entry)

    response = await client.get(f"/groups/by-guest-token/{guest_token}")
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"
