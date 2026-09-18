"""Contract tests for 036-match-insights-benchmarks US2, per
specs/036-match-insights-benchmarks/contracts/member-match-records-api.md:
the partner/opponent fields on the two match-records endpoints and the two
exact filters shared by all four filtered endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.models import FriendRequest
from app.domains.member.models import Member
from app.domains.member.service import register
from tests.unit.domains._match_history import make_entry, make_group, make_played_match

pytestmark = pytest.mark.asyncio

WIN = "A" * 21
MATCHUP_FIELDS = {
    "player_key",
    "member_id",
    "nickname",
    "matches",
    "wins",
    "losses",
    "win_rate",
    "avg_margin",
    "low_sample",
}
FILTERED_ROUTES = (
    "/members/me/match-records",
    "/members/me/match-dashboard",
    "/members/{friend}/match-records",
    "/members/{friend}/match-dashboard",
)


async def _register(session: AsyncSession, email: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    await session.commit()
    return member


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _befriend(session: AsyncSession, one: Member, other: Member) -> None:
    session.add(FriendRequest(requester_id=one.id, addressee_id=other.id, status="accepted"))
    await session.commit()


async def _play_doubles(session: AsyncSession, member: Member, partner: Member) -> dict[str, str]:
    """Three won doubles matches with `partner`, against two guests. Returns
    the player keys involved."""
    group = await make_group(session, "Matchups", match_mode="doubles")
    mine = [
        (await make_entry(session, group, "我", member.id)).id,
        (await make_entry(session, group, "搭檔", partner.id)).id,
    ]
    rivals = [
        await make_entry(session, group, "對手一"),
        await make_entry(session, group, "對手二"),
    ]
    for _ in range(3):
        await make_played_match(
            session, group, team_a=mine, team_b=[r.id for r in rivals], sides=WIN
        )
    return {"partner": f"m:{partner.id}", "rival": f"r:{rivals[0].id}"}


async def test_records_carry_partner_and_opponent_rows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    me = await _register(db_session, "matchups-me@example.com")
    partner = await _register(db_session, "matchups-partner@example.com")
    keys = await _play_doubles(db_session, me, partner)

    response = await client.get(
        "/members/me/match-records", headers=await _login(client, "matchups-me@example.com")
    )

    assert response.status_code == 200
    body = response.json()
    (row,) = body["partner_records"]
    assert set(row) == MATCHUP_FIELDS
    assert (row["player_key"], row["member_id"]) == (keys["partner"], str(partner.id))
    assert (row["matches"], row["wins"], row["win_rate"], row["avg_margin"]) == (3, 3, 1.0, 21.0)
    assert row["low_sample"] is False
    assert len(body["opponent_records"]) == 2
    assert all(set(item) == MATCHUP_FIELDS for item in body["opponent_records"])
    assert all(item["member_id"] is None for item in body["opponent_records"])  # guests
    assert set(body["matchup_highlights"]) == {
        "most_played_partner",
        "best_partner",
        "most_faced_opponent",
        "toughest_opponent",
    }
    assert body["matchup_highlights"]["most_played_partner"] == keys["partner"]
    assert body["matchup_highlights"]["best_partner"] is None  # three matches: under five
    assert body["doubles_matches"] == 3


async def test_a_member_without_matches_gets_empty_tables(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(db_session, "matchups-empty@example.com")

    body = (
        await client.get(
            "/members/me/match-records",
            headers=await _login(client, "matchups-empty@example.com"),
        )
    ).json()

    assert body["partner_records"] == [] and body["opponent_records"] == []
    assert body["doubles_matches"] == 0
    assert set(body["matchup_highlights"].values()) == {None}


async def test_exact_filters_narrow_records_and_dashboard_alike(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    me = await _register(db_session, "matchups-filter@example.com")
    partner = await _register(db_session, "matchups-filter-p@example.com")
    keys = await _play_doubles(db_session, me, partner)
    headers = await _login(client, "matchups-filter@example.com")

    for query, expected in (
        (f"partner_key={keys['partner']}", 3),
        (f"opponent_key={keys['rival']}", 3),
        (f"opponent_key={keys['partner']}", 0),  # a partner is not an opponent
        (f"partner_key=m:{uuid.uuid4()}", 0),  # well-formed, matches nobody: not an error
    ):
        records = await client.get(f"/members/me/match-records?{query}", headers=headers)
        dashboard = await client.get(f"/members/me/match-dashboard?{query}", headers=headers)
        assert records.status_code == dashboard.status_code == 200, query
        assert records.json()["total_matches"] == expected, query
        assert dashboard.json()["total_matches"] == expected, query


@pytest.mark.parametrize("bad", ["阿哲", "m:not-a-uuid", "x:6b1f0c1e-0000-4000-8000-000000000001"])
@pytest.mark.parametrize("name", ["partner_key", "opponent_key"])
async def test_a_malformed_key_is_rejected_on_all_four_routes(
    client: AsyncClient, db_session: AsyncSession, name: str, bad: str
) -> None:
    tag = uuid.uuid4().hex[:8]
    viewer = await _register(db_session, f"matchups-bad-{tag}@example.com")
    friend = await _register(db_session, f"matchups-bad-friend-{tag}@example.com")
    await _befriend(db_session, viewer, friend)
    headers = await _login(client, viewer.email)

    for route in FILTERED_ROUTES:
        response = await client.get(
            route.format(friend=friend.id), params={name: bad}, headers=headers
        )
        assert response.status_code == 422, route
        assert response.json()["error_code"] == "INVALID_PLAYER_KEY", route


async def test_friend_view_carries_the_same_tables_and_a_refusal_carries_none(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    viewer = await _register(db_session, "matchups-viewer@example.com")
    owner = await _register(db_session, "matchups-owner@example.com")
    partner = await _register(db_session, "matchups-owner-p@example.com")
    await _befriend(db_session, viewer, owner)
    keys = await _play_doubles(db_session, owner, partner)
    headers = await _login(client, "matchups-viewer@example.com")

    as_friend = await client.get(f"/members/{owner.id}/match-records", headers=headers)
    as_owner = await client.get(
        "/members/me/match-records", headers=await _login(client, "matchups-owner@example.com")
    )

    assert as_friend.status_code == 200
    for field in ("partner_records", "opponent_records", "matchup_highlights", "doubles_matches"):
        assert as_friend.json()[field] == as_owner.json()[field], field
    assert as_friend.json()["partner_records"][0]["player_key"] == keys["partner"]

    owner.share_match_records_with_friends = False
    await db_session.commit()
    refused = await client.get(f"/members/{owner.id}/match-records", headers=headers)
    assert refused.status_code == 403
    assert "partner_records" not in refused.json() and "opponent_records" not in refused.json()
