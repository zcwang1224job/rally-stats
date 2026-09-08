"""Integration test for 014-member-groups-history, per
specs/014-member-groups-history/quickstart.md: join → play a match → leave
→ still able to view group history; never-a-member rejected; existing
忘記管理PIN碼 flow unaffected by the "我的團" list expansion."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match

pytestmark = pytest.mark.asyncio


async def _register_verified_and_login(
    client: AsyncClient, db_session: AsyncSession, email: str, nickname: str, turnstile_token: str
) -> str:
    await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": turnstile_token,
        },
    )
    from app.domains.member.models import Member

    result = await db_session.execute(select(Member).where(Member.email == email))
    member = result.scalar_one()
    member.verification_status = "verified"
    await db_session.commit()

    login_response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    access_token = str(login_response.json()["access_token"])
    headers = {"Authorization": f"Bearer {access_token}"}
    await client.patch("/members/me/nickname", headers=headers, json={"nickname": nickname})
    return access_token


async def test_join_play_leave_still_views_history_stranger_rejected(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    a_token = await _register_verified_and_login(
        client, db_session, "history-flow-a1@example.com", "團長", valid_turnstile_token
    )
    b_token = await _register_verified_and_login(
        client, db_session, "history-flow-b1@example.com", "團員", valid_turnstile_token
    )
    c_token = await _register_verified_and_login(
        client, db_session, "history-flow-c1@example.com", "陌生人", valid_turnstile_token
    )
    a_headers = {"Authorization": f"Bearer {a_token}"}

    group_response = await client.post(
        "/groups",
        headers=a_headers,
        json={
            "name": "History Flow Group",
            "max_members": 6,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    group_id = created["group_id"]
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}

    court = (
        await client.post(
            f"/groups/{group_id}/courts", headers=admin_headers, json={"name": "1號場"}
        )
    ).json()

    b_headers = {"Authorization": f"Bearer {b_token}"}
    join_response = await client.post(f"/groups/{group_id}/join", headers=b_headers, json={})
    assert join_response.status_code == 201
    b_roster_entry_id = join_response.json()["roster_entry_id"]

    a_roster_result = await db_session.execute(
        text("SELECT id FROM roster_entries WHERE group_id = :gid AND is_creator = true"),
        {"gid": group_id},
    )
    a_roster_entry_id = str(a_roster_result.scalar_one())

    assign = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=admin_headers,
        json={
            "participant_ids": [a_roster_entry_id, b_roster_entry_id],
            "teams": {a_roster_entry_id: "A", b_roster_entry_id: "B"},
        },
    )
    match_id = assign.json()["match_id"]
    match_result = await db_session.execute(select(Match).where(Match.id == uuid.UUID(match_id)))
    match = match_result.scalar_one()
    match.status = "completed"
    match.winner_team = "B"
    await db_session.commit()

    leave_response = await client.post(
        f"/groups/{group_id}/roster/{b_roster_entry_id}/leave",
        headers=b_headers,
        json={},
    )
    assert leave_response.status_code == 201

    history = await client.get(
        f"/members/me/groups/{group_id}/history", headers=b_headers
    )
    assert history.status_code == 200
    body = history.json()
    assert len(body["matches"]) == 1
    assert body["my_stats"]["total_matches"] == 1
    assert body["my_stats"]["total_wins"] == 1
    assert body["my_stats"]["win_rate"] == 1.0

    b_my_groups = (
        await client.get("/members/me/groups", headers=b_headers)
    ).json()["groups"]
    assert b_my_groups[0]["member_status"] == "left"

    c_headers = {"Authorization": f"Bearer {c_token}"}
    stranger_attempt = await client.get(
        f"/members/me/groups/{group_id}/history", headers=c_headers
    )
    assert stranger_attempt.status_code == 403
    assert stranger_attempt.json()["error_code"] == "GROUP_MEMBERSHIP_NEVER_HELD"


async def test_forgot_admin_pin_unaffected_by_expanded_my_groups_list(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    a_token = await _register_verified_and_login(
        client, db_session, "history-flow-a2@example.com", "團長2", valid_turnstile_token
    )
    b_token = await _register_verified_and_login(
        client, db_session, "history-flow-b2@example.com", "團員2", valid_turnstile_token
    )
    a_headers = {"Authorization": f"Bearer {a_token}"}

    group_response = await client.post(
        "/groups",
        headers=a_headers,
        json={
            "name": "Forgot Pin Regression Group",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    group_id = created["group_id"]

    b_headers = {"Authorization": f"Bearer {b_token}"}
    await client.post(f"/groups/{group_id}/join", headers=b_headers, json={})

    # The list now includes B too (as a non-creator) — must not disturb A's
    # own "忘記管理PIN碼" entry or capability.
    a_groups = (await client.get("/members/me/groups", headers=a_headers)).json()["groups"]
    assert len(a_groups) == 1
    assert a_groups[0]["is_creator"] is True

    forgot_response = await client.post(
        f"/groups/{group_id}/forgot-admin-pin", headers=a_headers
    )
    assert forgot_response.status_code == 200
    body = forgot_response.json()
    assert body["admin_pin"] != created["admin_pin"]

    b_groups = (await client.get("/members/me/groups", headers=b_headers)).json()["groups"]
    assert len(b_groups) == 1
    assert b_groups[0]["is_creator"] is False

    b_forgot_attempt = await client.post(
        f"/groups/{group_id}/forgot-admin-pin", headers=b_headers
    )
    assert b_forgot_attempt.status_code == 403
    assert b_forgot_attempt.json()["error_code"] == "NOT_GROUP_CREATOR"
