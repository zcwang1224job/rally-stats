"""Integration test: change nickname -> applies to new groups, existing
in-progress group's roster snapshot untouched -> change password -> current
device keeps working, other devices are invalidated (US3)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member.service import register
from app.domains.roster.models import RosterEntry

pytestmark = pytest.mark.asyncio


async def test_member_settings_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    member = await register(db_session, "settingsflow@example.com", "abc12345")
    member.verification_status = "verified"  # personal settings require verification (FR-009)
    await db_session.commit()

    group = Group(
        name="Settings Flow Group",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    roster_entry = RosterEntry(
        group_id=group.id, member_id=member.id, nickname="舊暱稱", status="active"
    )
    db_session.add(roster_entry)
    await db_session.commit()

    device_a_login = (
        await client.post(
            "/auth/login", json={"email": "settingsflow@example.com", "password": "abc12345"}
        )
    ).json()
    device_b_login = (
        await client.post(
            "/auth/login", json={"email": "settingsflow@example.com", "password": "abc12345"}
        )
    ).json()
    device_a_token = device_a_login["access_token"]
    device_b_token = device_b_login["access_token"]

    nickname_response = await client.patch(
        "/members/me/nickname",
        json={"nickname": "新暱稱"},
        headers={"Authorization": f"Bearer {device_a_token}"},
    )
    assert nickname_response.status_code == 200
    assert nickname_response.json()["nickname"] == "新暱稱"

    await db_session.refresh(roster_entry)
    assert roster_entry.nickname == "舊暱稱"

    password_response = await client.patch(
        "/members/me/password",
        json={
            "current_password": "abc12345",
            "new_password": "newpass123",
            "confirm_new_password": "newpass123",
        },
        headers={"Authorization": f"Bearer {device_a_token}"},
    )
    assert password_response.status_code == 200
    new_device_a_token = password_response.json()["access_token"]

    still_works_response = await client.get(
        "/members/me", headers={"Authorization": f"Bearer {new_device_a_token}"}
    )
    assert still_works_response.status_code == 200

    device_b_response = await client.get(
        "/members/me", headers={"Authorization": f"Bearer {device_b_token}"}
    )
    assert device_b_response.status_code == 401
    assert device_b_response.json()["error_code"] == "MEMBER_TOKEN_INVALID"
