"""Contract test for GET /members/me/match-dashboard and
GET /members/{member_id}/match-dashboard per
specs/034-clutch-points-player-dashboard/contracts/member-match-dashboard-api.md."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member
from app.domains.member.service import register
from tests.unit.domains._match_history import make_entry, make_group, make_played_match

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
]
EMPTY = {
    "total_matches": 0,
    "recent_window": 10,
    "has_comparison": False,
    "metrics": [],
    "trends": [],
    "landing": None,
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
    """Constitution IV — deliberately stricter than /members/me/match-records."""
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
