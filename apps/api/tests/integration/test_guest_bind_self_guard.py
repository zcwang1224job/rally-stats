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


async def test_binding_status_flags_a_caller_already_on_the_roster(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """`already_in_group` is what lets the frontend leave the binding entry
    point out entirely for the 團長, rather than render a button whose only
    possible outcome is `MEMBER_ALREADY_IN_GROUP`."""
    owner_headers = await _verified_member_headers(
        client, db_session, valid_turnstile_token, "status-owner@example.com", "團長本人"
    )
    created = await client.post(
        "/groups",
        json={
            "name": "Binding Status Group",
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
    token = guest.json()["guest_session_token"]

    as_owner = await client.get(
        f"/groups/guest-token/{token}/binding-status", headers=owner_headers
    )
    assert as_owner.status_code == 200, as_owner.text
    assert as_owner.json()["already_in_group"] is True
    assert as_owner.json()["already_bound"] is False

    # The endpoint stays public, and the normal 訪客 case is anonymous.
    anonymous = await client.get(f"/groups/guest-token/{token}/binding-status")
    assert anonymous.status_code == 200, anonymous.text
    assert anonymous.json()["already_in_group"] is False

    # A logged-in member who is NOT on this roster still gets the entry point.
    outsider_headers = await _verified_member_headers(
        client, db_session, valid_turnstile_token, "status-outsider@example.com", "路人"
    )
    as_outsider = await client.get(
        f"/groups/guest-token/{token}/binding-status", headers=outsider_headers
    )
    assert as_outsider.status_code == 200, as_outsider.text
    assert as_outsider.json()["already_in_group"] is False
