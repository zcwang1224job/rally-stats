"""Integration test: create → RosterEntry auto-created → Guest Session Token
issued → current_member_count=1 (spec US1 acceptance scenarios 1, 3)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.roster.models import RosterEntry

pytestmark = pytest.mark.asyncio


async def test_anonymous_creation_produces_creator_roster_entry(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    response = await client.post(
        "/groups",
        json={
            "name": "Integration Test Group",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "小華",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 201
    body = response.json()

    result = await db_session.execute(
        select(RosterEntry).where(RosterEntry.id == body["roster_entry_id"])
    )
    roster_entry = result.scalar_one()
    assert roster_entry.is_creator is True
    assert roster_entry.status == "active"
    assert roster_entry.nickname == "小華"
    assert roster_entry.guest_session_token == body["guest_session_token"]

    public = await client.get(f"/groups/{body['group_id']}")
    assert public.json()["current_member_count"] == 1
