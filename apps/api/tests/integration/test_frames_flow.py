"""043 T069–T071: a billiards group end to end, then the member side — the
`sport` filter on records and dashboards, the activity list and the
per-activity dashboard sections (contracts/sections-manifest.md §4,
sports-api.md §4–§5, US3)."""

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register
from tests.unit.domains._match_history import make_entry, make_group, make_played_match

pytestmark = pytest.mark.asyncio


async def _member(
    session: AsyncSession, client: AsyncClient
) -> tuple[uuid.UUID, dict[str, str]]:
    member = await register(session, "frames@example.com", "abc12345")
    member.verification_status = "verified"
    member_id = member.id
    await session.commit()
    login = await client.post(
        "/auth/login", json={"email": "frames@example.com", "password": "abc12345"}
    )
    return member_id, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _billiards_group(
    client: AsyncClient, session: AsyncSession, token: str, member_id: uuid.UUID
) -> dict[str, Any]:
    created = (
        await client.post(
            "/groups",
            json={
                "max_members": 4,
                "team_size": 1,
                "sport": {"sport_key": "billiards"},
                "scheduling_mechanism": "manual",
                "creator_nickname": "莊家",
                "turnstile_token": token,
            },
        )
    ).json()
    assert "group_id" in created, created
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    court = (
        await client.post(
            f"/groups/{created['group_id']}/courts", headers=headers, json={"name": "2 號桌"}
        )
    ).json()
    me, rival = str(uuid.uuid4()), str(uuid.uuid4())
    for rid, nickname, owner in ((me, "我", str(member_id)), (rival, "阿強", None)):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator, "
                "member_id) VALUES (:id, :group_id, :nickname, 'active', false, :member_id)"
            ),
            {
                "id": rid,
                "group_id": created["group_id"],
                "nickname": nickname,
                "member_id": owner,
            },
        )
    await session.commit()
    return {"created": created, "headers": headers, "court": court, "me": me, "rival": rival}


async def _play_frames(client: AsyncClient, g: dict[str, Any], winners: str) -> str:
    """One match, me on team A; `winners` is each frame's winner, in order."""
    assign = await client.post(
        f"/courts/{g['court']['court_id']}/manual-assign",
        headers=g["headers"],
        json={"participant_ids": [g["me"], g["rival"]], "teams": {g["me"]: "A", g["rival"]: "B"}},
    )
    assert assign.status_code == 201, assign.text
    match_id = assign.json()["match_id"]
    url = f"/courts/by-token/{g['court']['control_panel_token']}/matches/{match_id}"
    for winner in winners:
        response = await client.post(
            f"{url}/events",
            json={"kind": "frames.frame_end", "payload": {"winner_team": winner}},
        )
        assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    return str(match_id)


async def test_billiards_group_to_member_dashboard(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.domains.schedule.service.publish", AsyncMock())
    member_id, auth = await _member(db_session, client)
    g = await _billiards_group(client, db_session, valid_turnstile_token, member_id)

    # Won 5:2 and lost 3:5, taking the first frame both times.
    won = await _play_frames(client, g, "AABABAA")
    await _play_frames(client, g, "ABBABABB")

    # A badminton match too: left out unless asked for, never added up.
    badminton = await make_group(db_session, "羽球", match_mode="singles")
    mine = await make_entry(db_session, badminton, "我", member_id)
    other = await make_entry(db_session, badminton, "對手")
    await make_played_match(
        db_session, badminton, team_a=[mine.id], team_b=[other.id], sides="A" * 21
    )

    records = (await client.get("/members/me/match-records", headers=auth)).json()
    assert records["total_matches"] == 1
    as_badminton = (
        await client.get("/members/me/match-records", headers=auth, params={"sport": "badminton"})
    ).json()
    assert as_badminton["total_matches"] == 1
    billiards = (
        await client.get("/members/me/match-records", headers=auth, params={"sport": "billiards"})
    ).json()
    assert billiards["total_matches"] == 2
    assert billiards["total_wins"] == 1

    plain = (await client.get("/members/me/match-dashboard", headers=auth)).json()
    same = (
        await client.get("/members/me/match-dashboard", headers=auth, params={"sport": "badminton"})
    ).json()
    assert plain == same
    assert plain["total_matches"] == 1
    refused = await client.get(
        "/members/me/match-dashboard", headers=auth, params={"sport": "billiards"}
    )
    assert refused.status_code == 409
    assert refused.json()["error_code"] == "SPORT_TYPE_NOT_SUPPORTED"
    invalid = await client.get("/members/me/match-records", headers=auth, params={"sport": "polo"})
    assert invalid.status_code == 422
    assert invalid.json()["error_code"] == "INVALID_SPORT_FILTER"

    activities = (await client.get("/members/me/activities", headers=auth)).json()["activities"]
    assert [(a["filter_value"], a["match_count"]) for a in activities] == [
        ("billiards", 2),
        ("badminton", 1),
    ]
    assert activities[0]["sport"]["type_key"] == "frames"

    missing = await client.get("/members/me/dashboard-sections", headers=auth)
    assert missing.status_code == 422
    assert missing.json()["error_code"] == "SPORT_REQUIRED"
    dashboard = (
        await client.get(
            "/members/me/dashboard-sections", headers=auth, params={"sport": "billiards"}
        )
    ).json()
    assert dashboard["type_key"] == "frames"
    assert dashboard["total_matches"] == 2
    kinds = [section["kind"] for section in dashboard["sections"]]
    assert kinds == ["metric_grid", "frames.dashboard_summary", "stat_table"]
    metrics = {m["key"]: m for m in dashboard["sections"][0]["data"]["metrics"]}
    assert metrics["match_win_rate"]["value"] == pytest.approx(0.5)
    assert metrics["frame_win_rate"]["value"] == pytest.approx(8 / 15)
    assert metrics["win_rate_after_first_frame"]["value"] == pytest.approx(0.5)
    assert metrics["avg_frames_per_match"]["value"] == pytest.approx(7.5)
    assert metrics["frame_win_rate"]["group_average"] is None  # fewer than 3 peers
    summary = dashboard["sections"][1]["data"]
    assert summary["longest_match_frames"] == 8
    assert summary["decider_record"] == {"played": 0, "won": 0}

    badminton_sections = (
        await client.get(
            "/members/me/dashboard-sections", headers=auth, params={"sport": "badminton"}
        )
    ).json()
    assert [s["kind"] for s in badminton_sections["sections"]] == ["net_rally.dashboard"]
    empty = (
        await client.get("/members/me/dashboard-sections", headers=auth, params={"sport": "darts"})
    ).json()
    assert empty["total_matches"] == 0
    assert empty["sections"] == [
        {"kind": "text_note", "title_key": None, "data": {"text_key": "playerDashboard.empty"}}
    ]

    detail = (await client.get(f"/members/me/match-records/{won}", headers=auth)).json()
    assert detail["serve_stats"] is None
    assert detail["sport"]["sport_key"] == "billiards"
    frame_list, trend = detail["sections"]
    assert frame_list["kind"] == "frames.frame_list"
    assert [f["winner_team"] for f in frame_list["data"]["frames"]] == list("AABABAA")
    assert {f["ended_by"] for f in frame_list["data"]["frames"]} == {"manual"}
    assert trend["kind"] == "frames.frame_trend"
    assert trend["data"]["points"][-1] == {"frame_no": 7, "frames_a": 5, "frames_b": 2}

    standings = await client.get(
        f"/groups/{g['created']['group_id']}/match-records",
        params={"guest_session_token": g["created"]["guest_session_token"]},
    )
    assert standings.status_code == 200, standings.text


async def test_table_tennis_dashboard_leaves_out_module_metrics(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """T056: `sport=table_tennis` (no serve, no shot placement) — same
    response shape, without the serve / ending metrics, landing or error
    breakdown; badminton keeps all 23."""
    member_id, auth = await _member(db_session, client)
    group = await make_group(db_session, "桌球", match_mode="singles")
    group_id = group.id
    mine = await make_entry(db_session, group, "我", member_id)
    other = await make_entry(db_session, group, "對手")
    await make_played_match(
        db_session, group, team_a=[mine.id], team_b=[other.id], sides="AB" * 5 + "A"
    )
    for table in ("groups", "matches"):
        column = "id" if table == "groups" else "group_id"
        await db_session.execute(
            text(f"UPDATE {table} SET sport_key = 'table_tennis' WHERE {column} = :id"),
            {"id": group_id},
        )
    await db_session.commit()

    body = (
        await client.get(
            "/members/me/match-dashboard", headers=auth, params={"sport": "table_tennis"}
        )
    ).json()
    assert body["total_matches"] == 1
    keys = {metric["key"] for metric in body["metrics"]}
    assert keys.isdisjoint(
        {"team_serve", "team_receive", "own_serve", "own_receive", "winner_share"}
    )
    assert {"points_scored", "deuce", "avg_win_margin"} <= keys
    assert body["landing"] is None
    assert body["error_breakdown"] is None
    assert all(trend["key"] in keys for trend in body["trends"])
    # Left out, `sport` is every net rally activity, table tennis included.
    assert (await client.get("/members/me/match-dashboard", headers=auth)).json()[
        "total_matches"
    ] == 1
