"""Contract tests for 037-rest-ready-toggle contracts/rest-state-api.md:
PUT /groups/{group_id}/roster/{roster_entry_id}/rest-state (the player's
own) and PUT /groups/{group_id}/members/{roster_entry_id}/rest-state (an
admin's), plus the rest fields on the schedule responses."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member

pytestmark = pytest.mark.asyncio


async def _create_group(client: AsyncClient, token: str, **overrides: object) -> dict:
    body = {
        "name": "Rest State Contract",
        "max_members": 12,
        "match_mode": "singles",
        "scheduling_mechanism": "manual",
        "creator_nickname": "阿正",
        "turnstile_token": token,
        **overrides,
    }
    response = await client.post("/groups", json=body)
    assert response.status_code == 201
    return response.json()


async def _join_guest(client: AsyncClient, group_id: str, nickname: str) -> dict:
    response = await client.post(f"/groups/{group_id}/join", json={"nickname": nickname})
    assert response.status_code == 201
    return response.json()


async def _login_member(
    client: AsyncClient, db_session: AsyncSession, email: str, token: str
) -> dict[str, str]:
    await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": token,
        },
    )
    member = (await db_session.execute(select(Member).where(Member.email == email))).scalar_one()
    member.verification_status = "verified"
    await db_session.commit()
    login = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    await client.patch("/members/me/nickname", headers=headers, json={"nickname": email[:8]})
    return headers


def _own_url(group_id: str, roster_entry_id: str) -> str:
    return f"/groups/{group_id}/roster/{roster_entry_id}/rest-state"


def _admin_url(group_id: str, roster_entry_id: str) -> str:
    return f"/groups/{group_id}/members/{roster_entry_id}/rest-state"


async def test_a_guest_rests_and_comes_back(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    joined = await _join_guest(client, created["group_id"], "小美")
    url = _own_url(created["group_id"], joined["roster_entry_id"])
    token = joined["guest_session_token"]

    response = await client.put(url, json={"resting": True, "guest_session_token": token})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "roster_entry_id",
        "resting",
        "resting_since",
        "currently_playing",
        "changed",
    }
    assert body["roster_entry_id"] == joined["roster_entry_id"]
    assert body["resting"] is True
    assert body["resting_since"] is not None
    assert body["currently_playing"] is False
    assert body["changed"] is True

    back = await client.put(url, json={"resting": False, "guest_session_token": token})
    assert back.status_code == 200
    assert back.json()["resting"] is False
    assert back.json()["resting_since"] is None


async def test_a_member_rests_on_their_own(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = await _login_member(client, db_session, "rest-a@example.com", valid_turnstile_token)
    joined = await client.post(f"/groups/{created['group_id']}/join", headers=headers, json={})
    roster_entry_id = joined.json()["roster_entry_id"]

    response = await client.put(
        _own_url(created["group_id"], roster_entry_id), headers=headers, json={"resting": True}
    )
    assert response.status_code == 200
    assert response.json()["resting"] is True


async def test_every_refusal_looks_the_same(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """FR-004: someone who can't prove ownership learns nothing — not even
    whether the entry exists."""
    created = await _create_group(client, valid_turnstile_token)
    group_id = created["group_id"]
    target = await _join_guest(client, group_id, "小美")
    other_guest = await _join_guest(client, group_id, "小華")
    departed = await _join_guest(client, group_id, "小明")
    await client.post(
        f"/groups/{group_id}/roster/{departed['roster_entry_id']}/leave",
        json={"guest_session_token": departed["guest_session_token"]},
    )
    elsewhere = await _create_group(client, valid_turnstile_token, name="Elsewhere")
    stranger = await _join_guest(client, elsewhere["group_id"], "路人")
    other_member = await _login_member(
        client, db_session, "rest-b@example.com", valid_turnstile_token
    )
    await client.post(f"/groups/{group_id}/join", headers=other_member, json={})

    target_url = _own_url(group_id, target["roster_entry_id"])
    attempts = [
        client.put(target_url, headers=other_member, json={"resting": True}),
        client.put(
            target_url,
            json={"resting": True, "guest_session_token": other_guest["guest_session_token"]},
        ),
        client.put(target_url, json={"resting": True}),
        client.put(
            _own_url(group_id, departed["roster_entry_id"]),
            json={"resting": True, "guest_session_token": departed["guest_session_token"]},
        ),
        client.put(
            _own_url(group_id, stranger["roster_entry_id"]),
            json={"resting": True, "guest_session_token": stranger["guest_session_token"]},
        ),
        client.put(
            _own_url(group_id, str(uuid.uuid4())),
            json={"resting": True, "guest_session_token": target["guest_session_token"]},
        ),
    ]
    responses = [await attempt for attempt in attempts]

    assert {r.status_code for r in responses} == {404}
    bodies = [r.json() for r in responses]
    assert bodies[0] == {"error_code": "ROSTER_ENTRY_NOT_FOUND", "detail": {}}
    assert all(body == bodies[0] for body in bodies)


async def test_a_guest_token_decides_over_a_member_login(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """Same precedence as leaving: with a token in the body, only the token
    counts — the caller's own login doesn't rescue a wrong one."""
    created = await _create_group(client, valid_turnstile_token)
    headers = await _login_member(client, db_session, "rest-c@example.com", valid_turnstile_token)
    joined = await client.post(f"/groups/{created['group_id']}/join", headers=headers, json={})

    response = await client.put(
        _own_url(created["group_id"], joined.json()["roster_entry_id"]),
        headers=headers,
        json={"resting": True, "guest_session_token": "not-the-right-token"},
    )
    assert response.status_code == 404


async def test_repeating_a_request_changes_nothing(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    joined = await _join_guest(client, created["group_id"], "小美")
    url = _own_url(created["group_id"], joined["roster_entry_id"])
    payload = {"resting": True, "guest_session_token": joined["guest_session_token"]}

    first = (await client.put(url, json=payload)).json()
    second = await client.put(url, json=payload)

    assert second.status_code == 200
    assert second.json()["changed"] is False
    assert second.json()["resting_since"] == first["resting_since"]


async def test_a_disbanded_group_refuses(client: AsyncClient, valid_turnstile_token: str) -> None:
    created = await _create_group(client, valid_turnstile_token)
    joined = await _join_guest(client, created["group_id"], "小美")
    await client.post(
        f"/groups/{created['group_id']}/disband",
        headers={"Authorization": f"Bearer {created['admin_token']}"},
    )

    response = await client.put(
        _own_url(created["group_id"], joined["roster_entry_id"]),
        json={"resting": True, "guest_session_token": joined["guest_session_token"]},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "GROUP_DISBANDED"


async def test_schedules_keep_resting_players_on_the_roster(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    group_id = created["group_id"]
    resting = await _join_guest(client, group_id, "小美")
    ready = await _join_guest(client, group_id, "小華")
    await client.put(
        _own_url(group_id, resting["roster_entry_id"]),
        json={"resting": True, "guest_session_token": resting["guest_session_token"]},
    )

    member_view = await client.get(
        f"/groups/{group_id}/member-schedule",
        params={"guest_session_token": ready["guest_session_token"]},
    )
    admin_view = await client.get(
        f"/groups/{group_id}/schedule",
        headers={"Authorization": f"Bearer {created['admin_token']}"},
    )

    for response in (member_view, admin_view):
        assert response.status_code == 200
        rows = {row["roster_entry_id"]: row for row in response.json()["roster"]}
        assert rows[resting["roster_entry_id"]]["resting"] is True
        assert rows[resting["roster_entry_id"]]["resting_since"] is not None
        assert rows[ready["roster_entry_id"]]["resting"] is False
        assert rows[ready["roster_entry_id"]]["resting_since"] is None
        assert all("partner_roster_entry_id" in row for row in rows.values())
