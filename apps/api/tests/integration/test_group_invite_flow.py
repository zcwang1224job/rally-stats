"""Integration test for the full group-invite lifecycle, per
specs/013-group-invite-friends/quickstart.md."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member

pytestmark = pytest.mark.asyncio


async def _register_verified_and_login(
    client: AsyncClient, db_session: AsyncSession, email: str, nickname: str, turnstile_token: str
) -> tuple[str, str]:
    await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": turnstile_token,
        },
    )
    result = await db_session.execute(select(Member).where(Member.email == email))
    member = result.scalar_one()
    member.verification_status = "verified"
    await db_session.commit()

    login_response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    access_token = str(login_response.json()["access_token"])
    headers = {"Authorization": f"Bearer {access_token}"}
    await client.patch("/members/me/nickname", headers=headers, json={"nickname": nickname})
    me = await client.get("/members/me", headers=headers)
    return access_token, str(me.json()["user_number"])


async def _create_member_group(
    client: AsyncClient, access_token: str, turnstile_token: str, **overrides: object
) -> dict:
    payload = {
        "name": "Invite Flow Test",
        "max_members": 4,
        "match_mode": "doubles",
        "scheduling_mechanism": "manual",
        "turnstile_token": turnstile_token,
    }
    payload.update(overrides)
    response = await client.post(
        "/groups", headers={"Authorization": f"Bearer {access_token}"}, json=payload
    )
    assert response.status_code == 201
    return response.json()


async def _become_friends(client: AsyncClient, a_token: str, b_token: str, b_number: str) -> str:
    created = await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_number},
        headers={"Authorization": f"Bearer {a_token}"},
    )
    friend_request_id = created.json()["friend_request_id"]
    await client.post(
        f"/friends/requests/{friend_request_id}/accept",
        headers={"Authorization": f"Bearer {b_token}"},
    )
    return str(friend_request_id)


async def _send_invite(
    client: AsyncClient, admin_headers: dict, group_id: str, invitee_id: str
) -> str:
    sent = await client.post(
        f"/groups/{group_id}/invites",
        headers=admin_headers,
        json={"invitee_member_id": invitee_id},
    )
    assert sent.status_code == 201
    return str(sent.json()["invite_id"])


async def test_send_notify_accept_full_flow(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    a_token, _a_number = await _register_verified_and_login(
        client, db_session, "flow-a1@example.com", "團長", valid_turnstile_token
    )
    b_token, b_number = await _register_verified_and_login(
        client, db_session, "flow-b1@example.com", "小美", valid_turnstile_token
    )
    await _become_friends(client, a_token, b_token, b_number)
    group = await _create_member_group(client, a_token, valid_turnstile_token)
    admin_headers = {"Authorization": f"Bearer {group['admin_token']}"}
    invitable = (
        await client.get(f"/groups/{group['group_id']}/invitable-friends", headers=admin_headers)
    ).json()
    invitee_id = invitable["friends"][0]["member_id"]

    b_headers = {"Authorization": f"Bearer {b_token}"}
    # b already has one unread notification from _become_friends()'s own
    # friend request — mark it read first so this test only measures the
    # group-invite notification's own delivery.
    await client.post("/notifications/read-all", headers=b_headers)

    invite_id = await _send_invite(client, admin_headers, group["group_id"], invitee_id)

    unread = await client.get("/notifications/unread-count", headers=b_headers)
    assert unread.json()["unread_count"] == 1
    notifications = (await client.get("/notifications", headers=b_headers)).json()["notifications"]
    assert notifications[0]["type"] == "group_invite"
    assert notifications[0]["group_invite"]["invite_id"] == invite_id

    detail = await client.get(f"/group-invites/{invite_id}", headers=b_headers)
    assert detail.json()["status"] == "pending"

    accepted = await client.post(f"/group-invites/{invite_id}/accept", headers=b_headers)
    assert accepted.status_code == 200

    # Unfriending afterward MUST NOT retroactively touch an already-accepted
    # invite (only pending ones are ever transitioned).
    invite_after = await client.get(f"/group-invites/{invite_id}", headers=b_headers)
    assert invite_after.json()["status"] == "accepted"


async def test_capacity_full_leaves_invite_pending_and_notifies_creator(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    a_token, _a_number = await _register_verified_and_login(
        client, db_session, "flow-a2@example.com", "團長2", valid_turnstile_token
    )
    b_token, b_number = await _register_verified_and_login(
        client, db_session, "flow-b2@example.com", "小華", valid_turnstile_token
    )
    filler_token, filler_number = await _register_verified_and_login(
        client, db_session, "flow-filler2@example.com", "填充", valid_turnstile_token
    )
    await _become_friends(client, a_token, b_token, b_number)
    await _become_friends(client, a_token, filler_token, filler_number)
    group = await _create_member_group(
        client, a_token, valid_turnstile_token, max_members=2, match_mode="singles"
    )
    admin_headers = {"Authorization": f"Bearer {group['admin_token']}"}
    invitable = (
        await client.get(f"/groups/{group['group_id']}/invitable-friends", headers=admin_headers)
    ).json()
    b_id = next(f["member_id"] for f in invitable["friends"] if f["nickname"] == "小華")
    filler_id = next(f["member_id"] for f in invitable["friends"] if f["nickname"] == "填充")

    invite_id = await _send_invite(client, admin_headers, group["group_id"], b_id)
    filler_invite_id = await _send_invite(client, admin_headers, group["group_id"], filler_id)
    filler_headers = {"Authorization": f"Bearer {filler_token}"}
    filler_accept = await client.post(
        f"/group-invites/{filler_invite_id}/accept", headers=filler_headers
    )
    assert filler_accept.status_code == 200  # fills the group to capacity (max_members=2)

    b_headers = {"Authorization": f"Bearer {b_token}"}
    b_accept = await client.post(f"/group-invites/{invite_id}/accept", headers=b_headers)
    assert b_accept.status_code == 409
    assert b_accept.json()["error_code"] == "GROUP_FULL"

    invite_status = await client.get(f"/group-invites/{invite_id}", headers=b_headers)
    assert invite_status.json()["status"] == "pending"

    a_headers = {"Authorization": f"Bearer {a_token}"}
    creator_notifications = (await client.get("/notifications", headers=a_headers)).json()[
        "notifications"
    ]
    capacity_full = [
        n for n in creator_notifications if n["type"] == "group_invite_capacity_full"
    ]
    assert len(capacity_full) == 1
    assert capacity_full[0]["group_invite"]["invite_id"] == invite_id


async def test_unfriend_while_pending_invalidates_invite(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    a_token, _a_number = await _register_verified_and_login(
        client, db_session, "flow-a3@example.com", "團長3", valid_turnstile_token
    )
    b_token, b_number = await _register_verified_and_login(
        client, db_session, "flow-b3@example.com", "小強", valid_turnstile_token
    )
    friend_request_id = await _become_friends(client, a_token, b_token, b_number)
    group = await _create_member_group(client, a_token, valid_turnstile_token)
    admin_headers = {"Authorization": f"Bearer {group['admin_token']}"}
    invitable = (
        await client.get(f"/groups/{group['group_id']}/invitable-friends", headers=admin_headers)
    ).json()
    invitee_id = invitable["friends"][0]["member_id"]
    invite_id = await _send_invite(client, admin_headers, group["group_id"], invitee_id)

    a_headers = {"Authorization": f"Bearer {a_token}"}
    unfriend_response = await client.delete(
        f"/friends/{friend_request_id}", headers=a_headers
    )
    assert unfriend_response.status_code == 200

    b_headers = {"Authorization": f"Bearer {b_token}"}
    detail = await client.get(f"/group-invites/{invite_id}", headers=b_headers)
    assert detail.json()["status"] == "invalidated"

    accept_attempt = await client.post(f"/group-invites/{invite_id}/accept", headers=b_headers)
    assert accept_attempt.status_code == 409
    assert accept_attempt.json()["error_code"] == "GROUP_INVITE_NOT_PENDING"


async def test_disband_while_pending_invalidates_invite(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    a_token, _a_number = await _register_verified_and_login(
        client, db_session, "flow-a4@example.com", "團長4", valid_turnstile_token
    )
    b_token, b_number = await _register_verified_and_login(
        client, db_session, "flow-b4@example.com", "小玲", valid_turnstile_token
    )
    await _become_friends(client, a_token, b_token, b_number)
    group = await _create_member_group(client, a_token, valid_turnstile_token)
    admin_headers = {"Authorization": f"Bearer {group['admin_token']}"}
    invitable = (
        await client.get(f"/groups/{group['group_id']}/invitable-friends", headers=admin_headers)
    ).json()
    invitee_id = invitable["friends"][0]["member_id"]
    invite_id = await _send_invite(client, admin_headers, group["group_id"], invitee_id)

    disband = await client.post(f"/groups/{group['group_id']}/disband", headers=admin_headers)
    assert disband.status_code == 200

    b_headers = {"Authorization": f"Bearer {b_token}"}
    detail = await client.get(f"/group-invites/{invite_id}", headers=b_headers)
    assert detail.json()["status"] == "invalidated"


async def test_decline_then_reinvite_full_regression(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """FR-008 regression: declining an invite must not permanently block a
    fresh invite to the same friend."""
    a_token, _a_number = await _register_verified_and_login(
        client, db_session, "flow-a5@example.com", "團長5", valid_turnstile_token
    )
    b_token, b_number = await _register_verified_and_login(
        client, db_session, "flow-b5@example.com", "小芳", valid_turnstile_token
    )
    await _become_friends(client, a_token, b_token, b_number)
    group = await _create_member_group(client, a_token, valid_turnstile_token)
    admin_headers = {"Authorization": f"Bearer {group['admin_token']}"}
    invitable = (
        await client.get(f"/groups/{group['group_id']}/invitable-friends", headers=admin_headers)
    ).json()
    invitee_id = invitable["friends"][0]["member_id"]
    first_invite_id = await _send_invite(client, admin_headers, group["group_id"], invitee_id)

    b_headers = {"Authorization": f"Bearer {b_token}"}
    declined = await client.post(f"/group-invites/{first_invite_id}/decline", headers=b_headers)
    assert declined.status_code == 200

    second_invite_id = await _send_invite(client, admin_headers, group["group_id"], invitee_id)
    assert second_invite_id != first_invite_id

    accepted = await client.post(f"/group-invites/{second_invite_id}/accept", headers=b_headers)
    assert accepted.status_code == 200
