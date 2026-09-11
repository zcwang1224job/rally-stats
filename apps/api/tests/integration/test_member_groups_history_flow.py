"""Integration test for 014-member-groups-history, per
specs/014-member-groups-history/quickstart.md: join → play a match → leave
→ still able to view group history; never-a-member rejected; existing
忘記管理PIN碼 flow unaffected by the "我的團" list expansion.

019-group-final-standings additions (T010/T016/T017, per
specs/019-group-final-standings/quickstart.md): the same endpoint's new
`final_standings` field — full coverage on a disbanded group (US1), the
same section on a still-active group (US2), and the fully-empty/zero-record
case (US3)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match, MatchParticipant

pytestmark = pytest.mark.asyncio


async def _roster_entry_id(db_session: AsyncSession, group_id: str, nickname: str) -> str:
    result = await db_session.execute(
        text("SELECT id FROM roster_entries WHERE group_id = :gid AND nickname = :nickname"),
        {"gid": group_id, "nickname": nickname},
    )
    return str(result.scalar_one())


async def _make_completed_match(
    db_session: AsyncSession,
    group_id: str,
    *,
    winner_team: str,
    team_a: list[str],
    team_b: list[str],
    round_number: int = 1,
) -> None:
    match = Match(
        group_id=uuid.UUID(group_id),
        court_id=None,
        round_number=round_number,
        status="completed",
        winner_team=winner_team,
        score_a=11,
        score_b=5,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
    )
    db_session.add(match)
    await db_session.flush()
    for pid in team_a:
        db_session.add(
            MatchParticipant(match_id=match.id, roster_entry_id=uuid.UUID(pid), team="A")
        )
    for pid in team_b:
        db_session.add(
            MatchParticipant(match_id=match.id, roster_entry_id=uuid.UUID(pid), team="B")
        )
    await db_session.commit()


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


async def test_final_standings_covers_all_statuses_guest_and_is_self_after_disband(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """US1 (quickstart.md 情境 1): a disbanded group's final_standings MUST
    still list active/left/kicked participants (member or guest), rank them
    correctly, and remain viewable — by the creator AND by a member who has
    since left — without a permission error (FR-002/006/010, closing the
    G2 gap from /speckit-analyze: an ex-member's own access is re-asserted
    here, not just their appearance in the row list)."""
    a_token = await _register_verified_and_login(
        client, db_session, "final-standings-a1@example.com", "團長A", valid_turnstile_token
    )
    b_token = await _register_verified_and_login(
        client, db_session, "final-standings-b1@example.com", "團員B", valid_turnstile_token
    )
    a_headers = {"Authorization": f"Bearer {a_token}"}
    b_headers = {"Authorization": f"Bearer {b_token}"}

    group_response = await client.post(
        "/groups",
        headers=a_headers,
        json={
            "name": "Final Standings Group 1",
            "max_members": 6,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    group_id = created["group_id"]
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}

    await client.post(f"/groups/{group_id}/join", headers=b_headers, json={})
    c_join = await client.post(f"/groups/{group_id}/join", json={"nickname": "訪客C"})
    c_roster_entry_id = c_join.json()["roster_entry_id"]
    await client.post(f"/groups/{group_id}/join", json={"nickname": "訪客D"})

    a_id = await _roster_entry_id(db_session, group_id, "團長A")
    b_id = await _roster_entry_id(db_session, group_id, "團員B")

    # A beats B, A beats C, B beats C — A: 2W0L, B: 1W1L, C: 0W2L, D: no
    # matches at all.
    await _make_completed_match(db_session, group_id, winner_team="A", team_a=[a_id], team_b=[b_id])
    await _make_completed_match(
        db_session, group_id, winner_team="A", team_a=[a_id], team_b=[c_roster_entry_id]
    )
    await _make_completed_match(
        db_session, group_id, winner_team="A", team_a=[b_id], team_b=[c_roster_entry_id]
    )

    leave_response = await client.post(
        f"/groups/{group_id}/roster/{b_id}/leave", headers=b_headers, json={}
    )
    assert leave_response.status_code == 201

    kick_response = await client.delete(
        f"/groups/{group_id}/members/{c_roster_entry_id}", headers=admin_headers
    )
    assert kick_response.status_code == 200

    disband_response = await client.post(f"/groups/{group_id}/disband", headers=admin_headers)
    assert disband_response.status_code == 200

    a_view = (
        await client.get(f"/members/me/groups/{group_id}/history", headers=a_headers)
    ).json()
    rows = {row["roster_entry_id"]: row for row in a_view["final_standings"]}
    assert rows[a_id]["is_self"] is True
    assert rows[a_id]["rank"] == 1
    assert rows[a_id]["total_wins"] == 2
    assert rows[b_id]["is_self"] is False
    assert rows[b_id]["current_status"] == "left"
    assert rows[b_id]["total_wins"] == 1
    assert rows[c_roster_entry_id]["current_status"] == "kicked"
    assert rows[c_roster_entry_id]["total_matches"] == 2
    assert rows[c_roster_entry_id]["total_wins"] == 0
    d_row = next(row for row in a_view["final_standings"] if row["nickname"] == "訪客D")
    assert d_row["total_matches"] == 0  # never played — distinct from C's 0-win-2-loss record

    # An ex-member (left, before the group even disbanded) MUST still be
    # able to view the SAME final_standings, without a permission error —
    # FR-010/SC-003, and their own row now shows is_self.
    b_view_response = await client.get(
        f"/members/me/groups/{group_id}/history", headers=b_headers
    )
    assert b_view_response.status_code == 200
    b_rows = {row["roster_entry_id"]: row for row in b_view_response.json()["final_standings"]}
    assert b_rows[b_id]["is_self"] is True
    assert b_rows[a_id]["is_self"] is False


async def test_final_standings_merges_same_member_rejoin(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """US1 (quickstart.md 情境 3): a member who left and rejoined the same
    group MUST appear as exactly one final_standings row, with wins/losses
    summed across both stints (research.md #1)."""
    a_token = await _register_verified_and_login(
        client, db_session, "final-standings-a2@example.com", "團長E", valid_turnstile_token
    )
    f_token = await _register_verified_and_login(
        client, db_session, "final-standings-f2@example.com", "小華F", valid_turnstile_token
    )
    a_headers = {"Authorization": f"Bearer {a_token}"}
    f_headers = {"Authorization": f"Bearer {f_token}"}

    group_response = await client.post(
        "/groups",
        headers=a_headers,
        json={
            "name": "Final Standings Group 2",
            "max_members": 6,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "turnstile_token": valid_turnstile_token,
        },
    )
    group_id = group_response.json()["group_id"]

    first_join = await client.post(f"/groups/{group_id}/join", headers=f_headers, json={})
    first_stint_id = first_join.json()["roster_entry_id"]
    a_id = await _roster_entry_id(db_session, group_id, "團長E")
    await _make_completed_match(
        db_session, group_id, winner_team="B", team_a=[a_id], team_b=[first_stint_id]
    )

    leave_response = await client.post(
        f"/groups/{group_id}/roster/{first_stint_id}/leave", headers=f_headers, json={}
    )
    assert leave_response.status_code == 201

    second_join = await client.post(f"/groups/{group_id}/join", headers=f_headers, json={})
    second_stint_id = second_join.json()["roster_entry_id"]
    assert second_stint_id != first_stint_id
    await _make_completed_match(
        db_session, group_id, winner_team="B", team_a=[a_id], team_b=[second_stint_id]
    )

    a_view = (
        await client.get(f"/members/me/groups/{group_id}/history", headers=a_headers)
    ).json()
    f_rows = [row for row in a_view["final_standings"] if row["nickname"] == "小華F"]
    assert len(f_rows) == 1
    assert f_rows[0]["total_wins"] == 2
    assert f_rows[0]["total_matches"] == 2
    assert f_rows[0]["current_status"] == "active"
    assert f_rows[0]["roster_entry_id"] == second_stint_id


async def test_final_standings_excludes_abandoned_and_ranks_fixed_partner_individually(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """US1 (quickstart.md 情境 4): an abandoned match MUST NOT count, and a
    fixed_partner group still ranks each of the 4 players individually
    (FR-003/FR-009) — integration-level coverage of what T001(e)/(f) already
    verify at the unit level."""
    a_token = await _register_verified_and_login(
        client, db_session, "final-standings-a3@example.com", "團長G", valid_turnstile_token
    )
    a_headers = {"Authorization": f"Bearer {a_token}"}
    group_response = await client.post(
        "/groups",
        headers=a_headers,
        json={
            "name": "Final Standings Group 3",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fixed_partner",
            "turnstile_token": valid_turnstile_token,
        },
    )
    group_id = group_response.json()["group_id"]

    p1 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P1"})).json()
    p2 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P2"})).json()
    p3 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P3"})).json()
    a_id = await _roster_entry_id(db_session, group_id, "團長G")

    await _make_completed_match(
        db_session, group_id,
        winner_team="A", team_a=[a_id, p1["roster_entry_id"]],
        team_b=[p2["roster_entry_id"], p3["roster_entry_id"]],
    )
    abandoned_match = Match(
        group_id=uuid.UUID(group_id), court_id=None, round_number=1, status="abandoned",
        winner_team=None, target_score=21, deuce_threshold=20, cap_score=30,
    )
    db_session.add(abandoned_match)
    await db_session.flush()
    db_session.add(
        MatchParticipant(match_id=abandoned_match.id, roster_entry_id=uuid.UUID(a_id), team="A")
    )
    db_session.add(
        MatchParticipant(
            match_id=abandoned_match.id,
            roster_entry_id=uuid.UUID(p2["roster_entry_id"]),
            team="B",
        )
    )
    await db_session.commit()

    a_view = (
        await client.get(f"/members/me/groups/{group_id}/history", headers=a_headers)
    ).json()
    rows = {row["roster_entry_id"]: row for row in a_view["final_standings"]}
    # Each of the 4 players is scored individually — never merged as a pair.
    assert rows[a_id]["total_wins"] == 1
    assert rows[p1["roster_entry_id"]]["total_wins"] == 1
    assert rows[p2["roster_entry_id"]]["total_losses"] == 1
    assert rows[p3["roster_entry_id"]]["total_losses"] == 1
    # The abandoned match added a 2nd participation for A and P2 — MUST NOT
    # be counted (still 1 total match each, from the completed match only).
    assert rows[a_id]["total_matches"] == 1
    assert rows[p2["roster_entry_id"]]["total_matches"] == 1


async def test_final_standings_stable_across_repeated_calls(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """US1 (quickstart.md 情境 1 步驟 5, FR-005/SC-005): calling the history
    endpoint repeatedly against unchanged data MUST return identical
    final_standings ordering every time — closing the G1 gap from
    /speckit-analyze."""
    a_token = await _register_verified_and_login(
        client, db_session, "final-standings-a4@example.com", "團長H", valid_turnstile_token
    )
    a_headers = {"Authorization": f"Bearer {a_token}"}
    group_response = await client.post(
        "/groups",
        headers=a_headers,
        json={
            "name": "Final Standings Group 4",
            "max_members": 6,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "turnstile_token": valid_turnstile_token,
        },
    )
    group_id = group_response.json()["group_id"]
    p1 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P1"})).json()
    await client.post(f"/groups/{group_id}/join", json={"nickname": "P2"})
    a_id = await _roster_entry_id(db_session, group_id, "團長H")
    # A: 1 win, P1/P2: tied at 0 wins each — the tie is the interesting case.
    await _make_completed_match(
        db_session, group_id, winner_team="A", team_a=[a_id], team_b=[p1["roster_entry_id"]]
    )

    responses = []
    for _ in range(3):
        response = await client.get(
            f"/members/me/groups/{group_id}/history", headers=a_headers
        )
        responses.append(response.json()["final_standings"])

    first = responses[0]
    for other in responses[1:]:
        assert other == first
    assert len(first) == 3
    assert first[0]["rank"] == 1


async def test_final_standings_shown_for_still_active_group(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """US2 (quickstart.md 情境 2, FR-012): a group that has NOT been
    disbanded shows the exact same final_standings section, reflecting the
    累計 as of the current call — no conditional branch on group status."""
    a_token = await _register_verified_and_login(
        client, db_session, "final-standings-a5@example.com", "團長I", valid_turnstile_token
    )
    a_headers = {"Authorization": f"Bearer {a_token}"}
    group_response = await client.post(
        "/groups",
        headers=a_headers,
        json={
            "name": "Final Standings Group 5",
            "max_members": 6,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "turnstile_token": valid_turnstile_token,
        },
    )
    group_id = group_response.json()["group_id"]
    p1 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P1"})).json()
    a_id = await _roster_entry_id(db_session, group_id, "團長I")
    await _make_completed_match(
        db_session, group_id, winner_team="A", team_a=[a_id], team_b=[p1["roster_entry_id"]]
    )

    response = await client.get(f"/members/me/groups/{group_id}/history", headers=a_headers)
    assert response.status_code == 200
    rows = {row["roster_entry_id"]: row for row in response.json()["final_standings"]}
    assert rows[a_id]["total_wins"] == 1
    assert rows[a_id]["rank"] == 1
    assert rows[p1["roster_entry_id"]]["total_losses"] == 1


async def test_final_standings_empty_group_and_zero_record_participant(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """US3 (quickstart.md 情境 5): a group with zero completed matches
    still returns every participant (not an empty list), each with
    total_matches == 0 — and, in a mixed group, a not-yet-played
    participant is never dropped or misjudged as tied for last (FR-007/
    FR-008/SC-004), verifying Foundational's zero-record aggregation."""
    a_token = await _register_verified_and_login(
        client, db_session, "final-standings-a6@example.com", "團長J", valid_turnstile_token
    )
    a_headers = {"Authorization": f"Bearer {a_token}"}
    group_response = await client.post(
        "/groups",
        headers=a_headers,
        json={
            "name": "Final Standings Group 6",
            "max_members": 6,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "turnstile_token": valid_turnstile_token,
        },
    )
    group_id = group_response.json()["group_id"]

    empty_response = await client.get(
        f"/members/me/groups/{group_id}/history", headers=a_headers
    )
    empty_body = empty_response.json()
    assert len(empty_body["final_standings"]) == 1
    assert empty_body["final_standings"][0]["total_matches"] == 0

    p1 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P1"})).json()
    p2 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P2"})).json()
    a_id = await _roster_entry_id(db_session, group_id, "團長J")
    await _make_completed_match(
        db_session, group_id, winner_team="A", team_a=[a_id], team_b=[p1["roster_entry_id"]]
    )

    mixed_response = await client.get(
        f"/members/me/groups/{group_id}/history", headers=a_headers
    )
    rows = {row["roster_entry_id"]: row for row in mixed_response.json()["final_standings"]}
    assert rows[a_id]["total_matches"] == 1
    assert rows[p1["roster_entry_id"]]["total_matches"] == 1
    # P2 never played — MUST still appear, distinguishable from P1's 0-win
    # loss via total_matches, not excluded from the list.
    assert rows[p2["roster_entry_id"]]["total_matches"] == 0
