"""Integration test: a logged-in member re-enters an already-joined group
via its join link -> directly signaled as already_joined, no password
re-verification or capacity re-check (US6, FR-020a)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def test_member_rejoin_via_link_short_circuits(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    create_response = await client.post(
        "/groups",
        json={
            "name": "Member Rejoin Group",
            "password": "letmein1",
            "max_members": 2,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = create_response.json()
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    admin_view = (
        await client.get(f"/groups/{created['group_id']}/admin", headers=admin_headers)
    ).json()
    join_link_token = admin_view["join_link_token"]

    member = await register(db_session, "rejoin@example.com", "abc12345")
    member.verification_status = "verified"
    member.nickname = "會員阿華"
    await db_session.commit()
    login_response = await client.post(
        "/auth/login", json={"email": "rejoin@example.com", "password": "abc12345"}
    )
    access_token = login_response.json()["access_token"]
    member_headers = {"Authorization": f"Bearer {access_token}"}

    first_preview = await client.get(f"/join/{join_link_token}", headers=member_headers)
    assert first_preview.json()["already_joined"] is False

    join_response = await client.post(
        f"/groups/{created['group_id']}/join",
        headers=member_headers,
        json={"password": "letmein1"},
    )
    assert join_response.status_code == 201
    roster_entry_id = join_response.json()["roster_entry_id"]

    # The group is now full (max_members=2: creator + this member) — if
    # FR-020a's short-circuit correctly runs BEFORE the capacity/password
    # checks, re-entering still succeeds despite the group being full and
    # despite no password being supplied this time.
    second_preview = await client.get(f"/join/{join_link_token}", headers=member_headers)
    second_preview_body = second_preview.json()
    assert second_preview_body["already_joined"] is True
    assert second_preview_body["roster_entry_id"] == roster_entry_id

    second_join_response = await client.post(
        f"/groups/{created['group_id']}/join", headers=member_headers, json={}
    )
    assert second_join_response.status_code == 201
    assert second_join_response.json()["created_new"] is False
    assert second_join_response.json()["roster_entry_id"] == roster_entry_id
