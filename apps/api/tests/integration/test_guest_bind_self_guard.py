"""028-guest-stats-binding: a 團長 MUST NOT bind a guest identity from
their own group to their own account.

The 團長 holds every guest link their group issues — the 輪替名單 share
panel prints each one, and they can regenerate any of them — so the
one-click bind path (FR-012) was reachable for their own account. Binding
succeeded, leaving one account with two `active` roster entries in one
rotation roster, and from there `active_roster_entry_for_member()`'s
`scalar_one_or_none()` raised `MultipleResultsFound`: every member-view
endpoint 500'd for the 團長 in their own group.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import EmailVerificationToken, Member

pytestmark = pytest.mark.asyncio


async def _verified_member_headers(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    email: str,
    nickname: str,
) -> dict[str, str]:
    password = "abc12345"
    register = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "confirm_password": password,
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert register.status_code == 201, register.text

    member = (await db_session.execute(select(Member).where(Member.email == email))).scalar_one()
    token_row = (
        await db_session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
        )
    ).scalar_one()
    verify = await client.get(f"/auth/verify-email/{token_row.token}")
    assert verify.status_code == 200, verify.text

    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    nick = await client.patch(
        "/members/me/nickname", json={"nickname": nickname}, headers=headers
    )
    assert nick.status_code == 200, nick.text
    return headers


async def test_group_owner_cannot_bind_a_guest_from_their_own_group(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    headers = await _verified_member_headers(
        client, db_session, valid_turnstile_token, "owner-binds@example.com", "團長本人"
    )
    created = await client.post(
        "/groups",
        json={
            "name": "Self Bind Guard Group",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "團長本人",
            "turnstile_token": valid_turnstile_token,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    group_id = created.json()["group_id"]

    guest = await client.post(f"/groups/{group_id}/join", json={"nickname": "訪客小美"})
    assert guest.status_code == 201, guest.text
    guest_token = guest.json()["guest_session_token"]

    bind = await client.post(
        f"/groups/guest-token/{guest_token}/bind", json={}, headers=headers
    )
    assert bind.status_code == 409, bind.text
    assert bind.json()["error_code"] == "MEMBER_ALREADY_IN_GROUP"

    # The guest identity is untouched, so the real 訪客 can still claim it.
    status = await client.get(f"/groups/guest-token/{guest_token}/binding-status")
    assert status.status_code == 200, status.text
    assert status.json()["already_bound"] is False

    # And the 團長's own member-view endpoints still work — the regression
    # that made this more than a cosmetic oddity.
    schedule = await client.get(f"/groups/{group_id}/member-schedule", headers=headers)
    assert schedule.status_code == 200, schedule.text
    preview = await client.get(f"/groups/{group_id}", headers=headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()["already_joined"] is True
    listing = await client.get("/groups", headers=headers)
    assert listing.status_code == 200, listing.text


async def test_a_member_not_on_this_roster_can_still_bind(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """The guard is about THIS group's roster only — 028's core flow (a
    logged-in visitor claiming their own guest record) must still work."""
    owner_headers = await _verified_member_headers(
        client, db_session, valid_turnstile_token, "owner-other@example.com", "團長本人"
    )
    created = await client.post(
        "/groups",
        json={
            "name": "Outsider Bind Group",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "團長本人",
            "turnstile_token": valid_turnstile_token,
        },
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    group_id = created.json()["group_id"]

    guest = await client.post(f"/groups/{group_id}/join", json={"nickname": "訪客小美"})
    assert guest.status_code == 201, guest.text
    guest_token = guest.json()["guest_session_token"]

    visitor_headers = await _verified_member_headers(
        client, db_session, valid_turnstile_token, "visitor@example.com", "小美"
    )
    bind = await client.post(
        f"/groups/guest-token/{guest_token}/bind", json={}, headers=visitor_headers
    )
    assert bind.status_code == 200, bind.text
    assert bind.json()["bound"] is True
