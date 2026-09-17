"""Contract test for GET /members/me/match-records/{match_id} per
contracts/match-record-detail-api.md (016-match-score-timeline) — shared by
the member's cross-group match-history list and the "我的團→歷史" list,
both of which use the "ever a member" access boundary (research.md #1)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_unverified(session: AsyncSession, email: str) -> Member:
    """For test cases that never need to join/act as this member — just
    authenticate — `require_member` (unlike `require_verified_member`)
    doesn't care about verification status, per existing convention."""
    return await register(session, email, "abc12345")


async def _login(client: AsyncClient, email: str, password: str = "abc12345") -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    return str(response.json()["access_token"])


async def _register_verified_and_login(
    client: AsyncClient, session: AsyncSession, email: str
) -> str:
    """Registers via the real endpoint (not the `register()` service
    shortcut) then flips verification status directly in the DB, matching
    `test_group_match_records.py`'s `_join_as_logged_in_member` — needed
    here because `PATCH /members/me/nickname` and joining a group both
    require a verified member."""
    await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": "unused",
        },
    )
    result = await session.execute(select(Member).where(Member.email == email))
    member = result.scalar_one()
    member.verification_status = "verified"
    await session.commit()
    return await _login(client, email)


async def _create_group_with_member_in_active_match(
    client: AsyncClient,
    db_session: AsyncSession,
    turnstile_token: str,
    member_email: str,
    *,
    detailed_scoring_enabled: bool = False,
) -> tuple[dict, dict, str, str]:
    """Creates a group (guest creator), joins `member_email` as a logged-in
    Member, generates a singles match between the two via fair_rotation,
    and plays it out to completion via the real control-panel scoring
    endpoint. Returns (created group, court, member's access_token,
    member's roster_entry_id) — the match itself is fetched separately via
    `_get_match_id()`."""
    group_response = await client.post(
        "/groups",
        json={
            "name": "Member Match Detail Contract",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "scoring_mode": "custom",
            "custom_scoring": {"target_score": 3, "deuce_threshold": 2, "cap_score": 5},
            "creator_nickname": "阿翔",
            "turnstile_token": turnstile_token,
        },
    )
    created = group_response.json()
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    # 021-group-creation-defaults FR-006: the group already has one
    # auto-created "球場一" court — use that instead of adding a second one,
    # so round generation has exactly one court to assign this test's single
    # match to (a second court would otherwise compete for it).
    courts_response = await client.get(
        f"/groups/{created['group_id']}/courts", headers=admin_headers
    )
    court = courts_response.json()["courts"][0]

    access_token = await _register_verified_and_login(client, db_session, member_email)
    member_headers = {"Authorization": f"Bearer {access_token}"}
    await client.patch(
        "/members/me/nickname", headers=member_headers, json={"nickname": "會員小張"}
    )
    join_response = await client.post(
        f"/groups/{created['group_id']}/join", headers=member_headers, json={}
    )
    roster_entry_id = join_response.json()["roster_entry_id"]

    if detailed_scoring_enabled:
        # 032-match-record-scoring-stats: MUST be set BEFORE next-round pulls
        # a match onto the court — matches.detailed_scoring_enabled is a
        # snapshot taken at creation time (031-shot-placement-scoring).
        await db_session.execute(
            text("UPDATE groups SET detailed_scoring_enabled = true WHERE id = :id"),
            {"id": created["group_id"]},
        )
        await db_session.commit()
        db_session.expire_all()

    await client.post(f"/groups/{created['group_id']}/next-round", headers=admin_headers)

    return created, court, access_token, roster_entry_id


async def _get_match_id(client: AsyncClient, court: dict) -> str:
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id: str = state.json()["current_match"]["match_id"]
    return match_id


async def _complete_match(client: AsyncClient, court: dict, match_id: str) -> None:
    for _ in range(3):
        response = await client.post(
            f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
            json={"side": "A", "delta": 1},
        )
        assert response.status_code == 200


async def test_success_with_bearer_token(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, access_token, _roster_entry_id = (
        await _create_group_with_member_in_active_match(
            client, db_session, valid_turnstile_token, "matchdetail-b@example.com"
        )
    )
    match_id = await _get_match_id(client, court)
    await _complete_match(client, court, match_id)

    response = await client.get(
        f"/members/me/match-records/{match_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["match_id"] == match_id
    assert body["record_completeness"] == "complete"
    assert len(body["events"]) == 3
    # 033-match-record-derived-stats: same shared builder, same new fields.
    assert body["serve_stats"]["excluded_points"] >= 1
    assert len(body["momentum_stats"]["longest_runs"]) == 2
    assert body["tempo_stats"]["counted_points"] == 3
    assert body["landing_distribution"] == []
    # 034-clutch-points-player-dashboard: same shared builder again.
    clutch = body["clutch_stats"]
    assert [m["team"] for m in clutch["match_points"]] == ["A", "B"]
    winner = clutch["match_points"][0]
    assert winner["held"] >= 1 and winner["converted_on"] == winner["held"]
    assert clutch["match_points"][1]["converted_on"] is None
    assert clutch["comeback"] is None  # A won 3:0


async def test_requires_login(client: AsyncClient) -> None:
    import uuid

    response = await client.get(f"/members/me/match-records/{uuid.uuid4()}")

    assert response.status_code == 401
    assert response.json()["error_code"] == "MEMBER_TOKEN_INVALID"


async def test_still_accessible_after_leaving_group(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, access_token, roster_entry_id = await _create_group_with_member_in_active_match(
        client, db_session, valid_turnstile_token, "matchdetail-left@example.com"
    )
    match_id = await _get_match_id(client, court)
    await _complete_match(client, court, match_id)
    member_headers = {"Authorization": f"Bearer {access_token}"}

    leave_response = await client.post(
        f"/groups/{created['group_id']}/roster/{roster_entry_id}/leave",
        headers=member_headers,
        json={},
    )
    assert leave_response.status_code == 201

    response = await client.get(
        f"/members/me/match-records/{match_id}", headers=member_headers
    )

    assert response.status_code == 200
    assert response.json()["record_completeness"] == "complete"


async def test_never_a_member_returns_group_membership_never_held(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, _access_token, _roster_entry_id = (
        await _create_group_with_member_in_active_match(
            client, db_session, valid_turnstile_token, "matchdetail-participant@example.com"
        )
    )
    match_id = await _get_match_id(client, court)
    await _complete_match(client, court, match_id)

    await _register_unverified(db_session, "matchdetail-outsider@example.com")
    outsider_token = await _login(client, "matchdetail-outsider@example.com")

    response = await client.get(
        f"/members/me/match-records/{match_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "GROUP_MEMBERSHIP_NEVER_HELD"


async def test_shot_placement_detail_is_included_via_member_endpoint(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """032-match-record-scoring-stats: confirms build_match_record_detail()'s
    extension applies automatically to this endpoint too — no per-endpoint
    changes were made (plan.md's whole point)."""
    created, court, access_token, _roster_entry_id = (
        await _create_group_with_member_in_active_match(
            client, db_session, valid_turnstile_token,
            "matchdetail-shotplacement@example.com", detailed_scoring_enabled=True,
        )
    )
    match_id = await _get_match_id(client, court)
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    team_a_id = next(
        p["roster_entry_id"]
        for p in state.json()["current_match"]["participants"]
        if p["team"] == "A"
    )

    score_1 = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )
    await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/shot-placement",
        json={"score_event_id": score_1.json()["score_event_id"], "roster_entry_id": team_a_id},
    )
    for _ in range(2):
        await client.post(
            f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
            json={"side": "A", "delta": 1},
        )

    response = await client.get(
        f"/members/me/match-records/{match_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["events"][0]["detail"]["scoring_roster_entry_id"] == team_a_id
    assert body["events"][1]["detail"] is None
    stats_by_id = {s["roster_entry_id"]: s for s in body["player_stats"]}
    assert stats_by_id[team_a_id]["scored_count"] == 1
