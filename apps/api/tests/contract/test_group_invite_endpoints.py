"""Contract tests for the group_invite endpoints, per
specs/013-group-invite-friends/contracts/group-invite-api.md."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member

pytestmark = pytest.mark.asyncio


async def _register_verified_and_login(
    client: AsyncClient, db_session: AsyncSession, email: str, nickname: str, turnstile_token: str
) -> tuple[str, str]:
    """Returns (access_token, user_number)."""
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
        "name": "Invite Contract Test",
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


async def _become_friends(client: AsyncClient, a_token: str, b_token: str, b_number: str) -> None:
    created = await client.post(
        "/friends/requests",
        json={"addressee_user_number": b_number},
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert created.status_code == 201
    friend_request_id = created.json()["friend_request_id"]
    accepted = await client.post(
        f"/friends/requests/{friend_request_id}/accept",
        headers={"Authorization": f"Bearer {b_token}"},
    )
    assert accepted.status_code == 200


async def test_invitable_friends_requires_admin_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await client.get("/groups/00000000-0000-0000-0000-000000000000/invitable-friends")
    assert response.status_code == 401


async def test_invitable_friends_rejects_anonymous_group(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await client.post(
        "/groups",
        json={
            "name": "Anon Invite Contract",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "匿名",
            "turnstile_token": valid_turnstile_token,
        },
    )
    body = created.json()
    headers = {"Authorization": f"Bearer {body['admin_token']}"}

    response = await client.get(f"/groups/{body['group_id']}/invitable-friends", headers=headers)
    assert response.status_code == 403
    assert response.json()["error_code"] == "GROUP_NOT_MEMBER_CREATED"


async def test_send_invite_full_lifecycle_via_invitable_friends(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    a_token, _a_number = await _register_verified_and_login(
        client, db_session, "inv-contract-a@example.com", "團長", valid_turnstile_token
    )
    b_token, b_number = await _register_verified_and_login(
        client, db_session, "inv-contract-b@example.com", "好友B", valid_turnstile_token
    )
    await _become_friends(client, a_token, b_token, b_number)
    group = await _create_member_group(client, a_token, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {group['admin_token']}"}

    invitable_before = await client.get(
        f"/groups/{group['group_id']}/invitable-friends", headers=headers
    )
    assert invitable_before.status_code == 200
    friend_row = next(
        f for f in invitable_before.json()["friends"] if f["nickname"] == "好友B"
    )
    assert friend_row["invite_status"] == "not_invited"

    sent = await client.post(
        f"/groups/{group['group_id']}/invites",
        headers=headers,
        json={"invitee_member_id": friend_row["member_id"]},
    )
    assert sent.status_code == 201
    assert sent.json()["status"] == "pending"

    duplicate = await client.post(
        f"/groups/{group['group_id']}/invites",
        headers=headers,
        json={"invitee_member_id": friend_row["member_id"]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error_code"] == "INVITE_ALREADY_PENDING"

    invitable_after = await client.get(
        f"/groups/{group['group_id']}/invitable-friends", headers=headers
    )
    friend_row_after = next(
        f for f in invitable_after.json()["friends"] if f["nickname"] == "好友B"
    )
    assert friend_row_after["invite_status"] == "pending"


async def test_get_invite_detail_and_decline(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    a_token, _a_number = await _register_verified_and_login(
        client, db_session, "inv-contract-c@example.com", "團長C", valid_turnstile_token
    )
    b_token, b_number = await _register_verified_and_login(
        client, db_session, "inv-contract-d@example.com", "好友D", valid_turnstile_token
    )
    await _become_friends(client, a_token, b_token, b_number)
    group = await _create_member_group(client, a_token, valid_turnstile_token)
    admin_headers = {"Authorization": f"Bearer {group['admin_token']}"}
    invitable = (
        await client.get(f"/groups/{group['group_id']}/invitable-friends", headers=admin_headers)
    ).json()
    invitee_id = invitable["friends"][0]["member_id"]
    sent = await client.post(
        f"/groups/{group['group_id']}/invites",
        headers=admin_headers,
        json={"invitee_member_id": invitee_id},
    )
    invite_id = sent.json()["invite_id"]
    b_headers = {"Authorization": f"Bearer {b_token}"}

    detail = await client.get(f"/group-invites/{invite_id}", headers=b_headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "pending"
    assert detail.json()["group_id"] == group["group_id"]
    assert detail.json()["group_name"] == "Invite Contract Test"
    assert detail.json()["inviter_nickname"] == "團長C"

    declined = await client.post(f"/group-invites/{invite_id}/decline", headers=b_headers)
    assert declined.status_code == 200
    assert declined.json()["status"] == "declined"

    detail_after = await client.get(f"/group-invites/{invite_id}", headers=b_headers)
    assert detail_after.json()["status"] == "declined"


async def test_accept_invite_skips_password_even_with_one_set(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    a_token, _a_number = await _register_verified_and_login(
        client, db_session, "inv-contract-e@example.com", "團長E", valid_turnstile_token
    )
    b_token, b_number = await _register_verified_and_login(
        client, db_session, "inv-contract-f@example.com", "好友F", valid_turnstile_token
    )
    await _become_friends(client, a_token, b_token, b_number)
    group = await _create_member_group(
        client, a_token, valid_turnstile_token, password="secretpw"
    )
    admin_headers = {"Authorization": f"Bearer {group['admin_token']}"}
    invitable = (
        await client.get(f"/groups/{group['group_id']}/invitable-friends", headers=admin_headers)
    ).json()
    invitee_id = invitable["friends"][0]["member_id"]
    sent = await client.post(
        f"/groups/{group['group_id']}/invites",
        headers=admin_headers,
        json={"invitee_member_id": invitee_id},
    )
    invite_id = sent.json()["invite_id"]
    b_headers = {"Authorization": f"Bearer {b_token}"}

    accepted = await client.post(f"/group-invites/{invite_id}/accept", headers=b_headers)
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["group_id"] == group["group_id"]
    assert body["nickname"] == "好友F"


async def test_group_invite_endpoints_require_login(client: AsyncClient) -> None:
    invite_id = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/group-invites/{invite_id}")).status_code == 401
    assert (await client.post(f"/group-invites/{invite_id}/accept")).status_code == 401
    assert (await client.post(f"/group-invites/{invite_id}/decline")).status_code == 401
