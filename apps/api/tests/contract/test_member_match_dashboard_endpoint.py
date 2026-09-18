"""Contract test for GET /members/me/match-dashboard and
GET /members/{member_id}/match-dashboard per
specs/034-clutch-points-player-dashboard/contracts/member-match-dashboard-api.md."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.models import FriendRequest
from app.domains.member.models import Member
from app.domains.member.service import register
from app.domains.notification.models import Notification
from tests.unit.domains._match_history import Shot, make_entry, make_group, make_played_match

pytestmark = pytest.mark.asyncio

METRIC_KEYS = [
    "team_serve",
    "team_receive",
    "own_serve",
    "own_receive",
    "points_scored",
    "points_lost",
    "scored_lost_ratio",
    "endgame",
    "deuce",
    "match_point_conversion",
    "match_points_saved",
    "when_leading",
    "when_tied",
    "when_trailing",
    "avg_points_for",
    "avg_points_against",
    "avg_win_margin",
    "avg_loss_margin",
    # 035-point-ending-type: five more, appended — the first 18 never move.
    "winner_share",
    "winners_per_match",
    "errors_per_match",
    "error_share_of_lost",
    "winner_error_ratio",
]
EMPTY = {
    "total_matches": 0,
    "recent_window": 10,
    "has_comparison": False,
    "metrics": [],
    "trends": [],
    "landing": None,
    "error_breakdown": None,
}


async def _register(session: AsyncSession, email: str, *, verified: bool = True) -> Member:
    member = await register(session, email, "abc12345")
    if verified:
        member.verification_status = "verified"
        await session.commit()
    return member


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _play(session: AsyncSession, member: Member, *, singles: int, doubles: int) -> None:
    """`singles` won singles matches and `doubles` lost doubles matches."""
    singles_group = await make_group(session, "Singles", match_mode="singles")
    me = await make_entry(session, singles_group, "我", member.id)
    rival = await make_entry(session, singles_group, "對手")
    for _ in range(singles):
        await make_played_match(
            session, singles_group, team_a=[me.id], team_b=[rival.id], sides="A" * 21
        )
    doubles_group = await make_group(session, "Doubles", match_mode="doubles")
    mine = [
        (await make_entry(session, doubles_group, "我", member.id)).id,
        (await make_entry(session, doubles_group, "搭檔")).id,
    ]
    theirs = [
        (await make_entry(session, doubles_group, "對手一")).id,
        (await make_entry(session, doubles_group, "對手二")).id,
    ]
    for _ in range(doubles):
        await make_played_match(
            session, doubles_group, team_a=mine, team_b=theirs, sides="B" * 21
        )


# ---------------------------------------------------------------- GET /members/me/match-dashboard


async def test_requires_login(client: AsyncClient) -> None:
    response = await client.get("/members/me/match-dashboard")

    assert response.status_code == 401
    assert response.json()["error_code"] == "MEMBER_TOKEN_INVALID"


async def test_unverified_member_is_locked_out(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Constitution IV — the same lock as /members/me/match-records."""
    await _register(db_session, "dash-unverified@example.com", verified=False)
    headers = await _login(client, "dash-unverified@example.com")

    response = await client.get("/members/me/match-dashboard", headers=headers)

    assert response.status_code == 403
    body = response.json()
    assert body["error_code"] == "EMAIL_NOT_VERIFIED"
    assert "metrics" not in body and "total_matches" not in body


async def test_member_without_matches_gets_the_empty_shape(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(db_session, "dash-empty@example.com")
    headers = await _login(client, "dash-empty@example.com")

    response = await client.get("/members/me/match-dashboard", headers=headers)

    assert response.status_code == 200
    assert response.json() == EMPTY


async def test_response_shape_with_matches(client: AsyncClient, db_session: AsyncSession) -> None:
    member = await _register(db_session, "dash-shape@example.com")
    await _play(db_session, member, singles=2, doubles=1)
    headers = await _login(client, "dash-shape@example.com")

    response = await client.get("/members/me/match-dashboard", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(EMPTY)
    assert (body["total_matches"], body["recent_window"], body["has_comparison"]) == (3, 10, False)
    assert [metric["key"] for metric in body["metrics"]] == METRIC_KEYS
    for metric in body["metrics"]:
        assert set(metric) == {"key", "kind", "better_when", "all", "recent", "verdict"}
        assert metric["kind"] in ("rate", "average", "ratio")
        assert metric["recent"] is None and metric["verdict"] is None  # <= 10 matches
        if metric["all"] is not None:
            assert set(metric["all"]) == {"value", "numerator", "denominator", "matches_used"}
    by_key = {metric["key"]: metric for metric in body["metrics"]}
    serve = by_key["team_serve"]["all"]
    assert serve["value"] == round(serve["numerator"] / serve["denominator"], 4)
    assert by_key["own_serve"]["all"]["matches_used"] == 1  # the doubles match only
    assert by_key["points_scored"]["all"] is None  # nobody recorded players
    # 035: matches, but not one recorded ending — the five new metrics are
    # there with `all: null`, and there is no breakdown.
    for key in METRIC_KEYS[18:]:
        assert by_key[key]["all"] is None, key
    assert body["error_breakdown"] is None


async def test_filters_match_the_match_list_and_page_is_ignored(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    member = await _register(db_session, "dash-filter@example.com")
    await _play(db_session, member, singles=2, doubles=1)
    headers = await _login(client, "dash-filter@example.com")

    for query in ("", "?match_mode=singles", "?result=loss", "?opponent1=不存在"):
        dashboard = await client.get(f"/members/me/match-dashboard{query}", headers=headers)
        records = await client.get(f"/members/me/match-records{query}", headers=headers)
        assert dashboard.status_code == records.status_code == 200
        assert dashboard.json()["total_matches"] == records.json()["total_matches"], query

    with_page = await client.get("/members/me/match-dashboard?page=7", headers=headers)
    without = await client.get("/members/me/match-dashboard", headers=headers)
    assert with_page.json() == without.json()


@pytest.mark.parametrize("query", ["result=draw", "match_mode=triples", "round_from=0"])
async def test_invalid_filter_values_are_rejected(
    client: AsyncClient, db_session: AsyncSession, query: str
) -> None:
    await _register(db_session, "dash-invalid@example.com")
    headers = await _login(client, "dash-invalid@example.com")

    response = await client.get(f"/members/me/match-dashboard?{query}", headers=headers)

    assert response.status_code == 422


async def test_comparison_and_trends_appear_past_ten_matches(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    member = await _register(db_session, "dash-trend@example.com")
    await _play(db_session, member, singles=12, doubles=0)
    headers = await _login(client, "dash-trend@example.com")

    body = (await client.get("/members/me/match-dashboard", headers=headers)).json()

    assert body["total_matches"] == 12 and body["has_comparison"] is True
    by_key = {metric["key"]: metric for metric in body["metrics"]}
    points_for = by_key["avg_points_for"]
    assert points_for["recent"]["matches_used"] == 10
    assert points_for["verdict"] in ("improved", "declined", "unchanged")
    assert by_key["match_points_saved"]["verdict"] is None  # no direction
    assert by_key["own_serve"]["all"] is None and by_key["own_serve"]["verdict"] is None

    trend_keys = {trend["key"] for trend in body["trends"]}
    assert "avg_points_for" in trend_keys and "own_serve" not in trend_keys
    series = next(trend for trend in body["trends"] if trend["key"] == "avg_points_for")
    assert len(series["points"]) == 12 - 4
    for point in series["points"]:
        assert set(point) == {"from_ended_at", "to_ended_at", "value", "numerator", "denominator"}
        # ISO 8601 with an explicit offset (Constitution VIII).
        assert point["to_ended_at"].endswith("Z") or "+" in point["to_ended_at"]


# ---------------------------------------------------------------- GET /members/{id}/match-dashboard


async def _befriend(session: AsyncSession, one: Member, other: Member) -> None:
    session.add(FriendRequest(requester_id=one.id, addressee_id=other.id, status="accepted"))
    await session.commit()


async def _rejections_match_the_match_records_endpoint(
    client: AsyncClient, headers: dict[str, str], member_id: object, status: int, code: str
) -> None:
    dashboard = await client.get(f"/members/{member_id}/match-dashboard", headers=headers)
    records = await client.get(f"/members/{member_id}/match-records", headers=headers)
    assert dashboard.status_code == records.status_code == status
    assert dashboard.json()["error_code"] == records.json()["error_code"] == code
    assert "metrics" not in dashboard.json() and "total_matches" not in dashboard.json()


async def test_friend_sees_exactly_what_the_owner_sees_unfiltered(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    viewer = await _register(db_session, "dash-viewer1@example.com")
    owner = await _register(db_session, "dash-owner1@example.com")
    await _befriend(db_session, viewer, owner)
    await _play(db_session, owner, singles=2, doubles=1)
    notifications_before = await db_session.scalar(select(func.count()).select_from(Notification))

    as_friend = await client.get(
        f"/members/{owner.id}/match-dashboard",
        headers=await _login(client, "dash-viewer1@example.com"),
    )
    as_owner = await client.get(
        "/members/me/match-dashboard", headers=await _login(client, "dash-owner1@example.com")
    )

    assert as_friend.status_code == 200
    assert as_friend.json() == as_owner.json()
    assert as_friend.json()["total_matches"] == 3
    # FR-036: looking is silent.
    notifications_after = await db_session.scalar(select(func.count()).select_from(Notification))
    assert notifications_after == notifications_before


async def test_self_view_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    member = await _register(db_session, "dash-self@example.com")
    headers = await _login(client, "dash-self@example.com")

    await _rejections_match_the_match_records_endpoint(
        client, headers, member.id, 400, "SELF_VIEW_NOT_SUPPORTED"
    )


async def test_unknown_member_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register(db_session, "dash-unknown@example.com")
    headers = await _login(client, "dash-unknown@example.com")

    await _rejections_match_the_match_records_endpoint(
        client, headers, "00000000-0000-4000-8000-000000000000", 404, "MEMBER_NOT_FOUND"
    )


async def test_non_friend_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register(db_session, "dash-stranger@example.com")
    owner = await _register(db_session, "dash-owner2@example.com")
    await _play(db_session, owner, singles=1, doubles=0)
    headers = await _login(client, "dash-stranger@example.com")

    await _rejections_match_the_match_records_endpoint(
        client, headers, owner.id, 403, "FRIENDSHIP_REQUIRED"
    )


async def test_turning_sharing_off_takes_effect_on_the_next_request(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SC-010 + 023 FR-008: eligibility is never cached."""
    viewer = await _register(db_session, "dash-viewer3@example.com")
    owner = await _register(db_session, "dash-owner3@example.com")
    await _befriend(db_session, viewer, owner)
    await _play(db_session, owner, singles=1, doubles=0)
    headers = await _login(client, "dash-viewer3@example.com")

    allowed = await client.get(f"/members/{owner.id}/match-dashboard", headers=headers)
    assert allowed.status_code == 200 and allowed.json()["total_matches"] == 1

    await client.patch(
        "/members/me/privacy",
        json={"share_match_records_with_friends": False},
        headers=await _login(client, "dash-owner3@example.com"),
    )

    await _rejections_match_the_match_records_endpoint(
        client, headers, owner.id, 403, "MATCH_RECORDS_PRIVATE"
    )


async def test_unverified_viewer_is_locked_out(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _register(db_session, "dash-owner4@example.com")
    await _register(db_session, "dash-viewer4@example.com", verified=False)
    headers = await _login(client, "dash-viewer4@example.com")

    response = await client.get(f"/members/{owner.id}/match-dashboard", headers=headers)

    assert response.status_code == 403
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


async def test_me_is_not_swallowed_by_the_member_id_route(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(db_session, "dash-route@example.com")
    headers = await _login(client, "dash-route@example.com")

    response = await client.get("/members/me/match-dashboard", headers=headers)

    assert response.status_code == 200  # a 422 here would mean the routes are in the wrong order


# ---------------------------------------------------------------- 035 ending metrics (T027)


async def test_ending_metrics_and_error_breakdown_with_recorded_endings(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    member = await _register(db_session, "dash-ending@example.com")
    group = await make_group(db_session, "Endings", match_mode="singles")
    me = await make_entry(db_session, group, "我", member.id)
    rival = await make_entry(db_session, group, "對手")
    await make_played_match(
        db_session, group, team_a=[me.id], team_b=[rival.id], sides="A" * 21,
        shots={
            0: Shot(scorer=me.id, loser=rival.id, ending="winner"),
            1: Shot(scorer=me.id, loser=rival.id, ending="winner"),
            2: Shot(scorer=me.id, loser=rival.id, ending="net"),
            3: Shot(scorer=me.id, loser=rival.id),  # detail without an ending
        },
    )
    await make_played_match(
        db_session, group, team_a=[me.id], team_b=[rival.id], sides="B" * 21,
        shots={
            0: Shot(scorer=rival.id, loser=me.id, ending="out"),
            1: Shot(scorer=rival.id, loser=me.id, ending="out"),
            2: Shot(scorer=rival.id, loser=me.id, ending="winner"),
        },
    )
    headers = await _login(client, "dash-ending@example.com")

    response = await client.get("/members/me/match-dashboard", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(EMPTY)
    by_key = {metric["key"]: metric for metric in body["metrics"]}
    assert set(by_key) == set(METRIC_KEYS)
    winner_share = by_key["winner_share"]
    assert (winner_share["kind"], winner_share["better_when"]) == ("rate", "higher")
    assert winner_share["all"] == {
        "value": round(2 / 3, 4), "numerator": 2, "denominator": 3, "matches_used": 2,
    }
    assert by_key["winners_per_match"]["all"] == {
        "value": 1.0, "numerator": 2, "denominator": 2, "matches_used": 2,
    }
    errors = by_key["errors_per_match"]
    assert errors["better_when"] == "lower"
    assert errors["all"] == {"value": 1.0, "numerator": 2, "denominator": 2, "matches_used": 2}
    assert by_key["error_share_of_lost"]["all"] == {
        "value": round(2 / 3, 4), "numerator": 2, "denominator": 3, "matches_used": 2,
    }
    ratio = by_key["winner_error_ratio"]
    assert ratio["kind"] == "ratio"
    assert ratio["all"] == {"value": 1.0, "numerator": 2, "denominator": 2, "matches_used": 2}
    assert body["error_breakdown"] == {
        "all": {"out": 2, "net": 0, "serve_fault": 0, "other_error": 0},
        "recent": None,
    }


async def test_friend_view_carries_the_ending_fields_and_rejections_do_not(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    viewer = await _register(db_session, "dash-viewer-ending@example.com")
    owner = await _register(db_session, "dash-owner-ending@example.com")
    await _befriend(db_session, viewer, owner)
    group = await make_group(db_session, "Endings F", match_mode="singles")
    me = await make_entry(db_session, group, "我", owner.id)
    rival = await make_entry(db_session, group, "對手")
    await make_played_match(
        db_session, group, team_a=[me.id], team_b=[rival.id], sides="A" * 21,
        shots={0: Shot(scorer=me.id, loser=rival.id, ending="winner"),
               1: Shot(scorer=me.id, loser=rival.id, ending="serve_fault")},
    )

    as_friend = await client.get(
        f"/members/{owner.id}/match-dashboard",
        headers=await _login(client, "dash-viewer-ending@example.com"),
    )

    assert as_friend.status_code == 200
    body = as_friend.json()
    assert [m["key"] for m in body["metrics"]] == METRIC_KEYS
    assert body["error_breakdown"] is None  # the owner's only recorded points were won
    assert next(m for m in body["metrics"] if m["key"] == "winner_share")["all"]["numerator"] == 1

    stranger = await _register(db_session, "dash-stranger-ending@example.com")
    rejected = await client.get(
        f"/members/{owner.id}/match-dashboard",
        headers=await _login(client, "dash-stranger-ending@example.com"),
    )
    assert rejected.status_code == 403
    assert "error_breakdown" not in rejected.json() and "metrics" not in rejected.json()
    assert stranger.id != owner.id
