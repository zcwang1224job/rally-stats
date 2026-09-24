"""Contract tests for 036-match-insights-benchmarks US4, per
specs/036-match-insights-benchmarks/contracts/match-comparison-api.md."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.models import FriendRequest
from app.domains.member.models import Member
from app.domains.member.service import register
from app.domains.notification.models import Notification
from tests.unit.domains._match_history import make_entry, make_group, make_played_match

pytestmark = pytest.mark.asyncio

A_WINS_BY_6 = "B" * 15 + "A" * 21


async def _register(session: AsyncSession, email: str, *, verified: bool = True) -> Member:
    member = await register(session, email, "abc12345")
    if verified:
        member.verification_status = "verified"
        await session.commit()
    return member


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _befriend(session: AsyncSession, one: Member, other: Member) -> None:
    session.add(FriendRequest(requester_id=one.id, addressee_id=other.id, status="accepted"))
    await session.commit()


async def _play(session: AsyncSession, winner: Member, loser: Member, matches: int = 3) -> None:
    group = await make_group(session, "Comparison", match_mode="singles")
    a = await make_entry(session, group, "贏家", winner.id)
    b = await make_entry(session, group, "輸家", loser.id)
    for _ in range(matches):
        await make_played_match(session, group, team_a=[a.id], team_b=[b.id], sides=A_WINS_BY_6)


async def test_response_shape(client: AsyncClient, db_session: AsyncSession) -> None:
    viewer = await _register(db_session, "cmp-c-viewer@example.com")
    friend = await _register(db_session, "cmp-c-friend@example.com")
    await _befriend(db_session, viewer, friend)
    await _play(db_session, viewer, friend)
    before = await db_session.scalar(select(func.count()).select_from(Notification))

    response = await client.get(
        f"/members/{friend.id}/match-comparison",
        headers=await _login(client, "cmp-c-viewer@example.com"),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"friend_total_matches", "my_total_matches", "metrics", "head_to_head"}
    assert (body["friend_total_matches"], body["my_total_matches"]) == (3, 3)
    assert len(body["metrics"]) == 23
    assert all(
        set(metric) == {"key", "kind", "better_when", "friend", "me", "better"}
        for metric in body["metrics"]
    )
    points_for = next(m for m in body["metrics"] if m["key"] == "avg_points_for")
    assert (points_for["me"]["value"], points_for["friend"]["value"]) == (21.0, 15.0)
    assert points_for["better"] == "me"
    assert set(points_for["me"]) == {"value", "numerator", "denominator", "matches_used"}
    assert body["head_to_head"] == {
        "as_opponents": {
            "matches": 3,
            "wins": 3,
            "losses": 0,
            "win_rate": 1.0,
            "avg_margin": 6.0,
        },
        "as_partners": None,
    }
    # FR-039: looking is silent.
    after = await db_session.scalar(select(func.count()).select_from(Notification))
    assert after == before


async def test_the_four_refusals_carry_no_numbers(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    viewer = await _register(db_session, "cmp-c-refused@example.com")
    stranger = await _register(db_session, "cmp-c-stranger@example.com")
    private = await _register(db_session, "cmp-c-private@example.com")
    await _befriend(db_session, viewer, private)
    private.share_match_records_with_friends = False
    await db_session.commit()
    headers = await _login(client, "cmp-c-refused@example.com")

    for target, status, code in (
        (viewer.id, 400, "SELF_VIEW_NOT_SUPPORTED"),
        (uuid.uuid4(), 404, "MEMBER_NOT_FOUND"),
        (stranger.id, 403, "FRIENDSHIP_REQUIRED"),
        (private.id, 403, "MATCH_RECORDS_PRIVATE"),
    ):
        response = await client.get(f"/members/{target}/match-comparison", headers=headers)
        assert (response.status_code, response.json()["error_code"]) == (status, code)
        assert "metrics" not in response.json() and "head_to_head" not in response.json()


async def test_turning_sharing_off_takes_effect_on_the_next_request(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    viewer = await _register(db_session, "cmp-c-live@example.com")
    friend = await _register(db_session, "cmp-c-live-friend@example.com")
    await _befriend(db_session, viewer, friend)
    headers = await _login(client, "cmp-c-live@example.com")
    path = f"/members/{friend.id}/match-comparison"
    assert (await client.get(path, headers=headers)).status_code == 200

    friend.share_match_records_with_friends = False
    await db_session.commit()

    refused = await client.get(path, headers=headers)
    assert (refused.status_code, refused.json()["error_code"]) == (403, "MATCH_RECORDS_PRIVATE")


async def test_my_own_sharing_setting_does_not_matter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    viewer = await _register(db_session, "cmp-c-shy@example.com")
    friend = await _register(db_session, "cmp-c-shy-friend@example.com")
    await _befriend(db_session, viewer, friend)
    viewer.share_match_records_with_friends = False
    await db_session.commit()

    response = await client.get(
        f"/members/{friend.id}/match-comparison",
        headers=await _login(client, "cmp-c-shy@example.com"),
    )
    assert response.status_code == 200


async def test_requires_a_verified_member(client: AsyncClient, db_session: AsyncSession) -> None:
    target = uuid.uuid4()
    anonymous = await client.get(f"/members/{target}/match-comparison")
    assert (anonymous.status_code, anonymous.json()["error_code"]) == (401, "MEMBER_TOKEN_INVALID")

    await _register(db_session, "cmp-c-unverified@example.com", verified=False)
    locked = await client.get(
        f"/members/{target}/match-comparison",
        headers=await _login(client, "cmp-c-unverified@example.com"),
    )
    assert (locked.status_code, locked.json()["error_code"]) == (403, "EMAIL_NOT_VERIFIED")


async def test_me_is_not_swallowed_as_a_member_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(db_session, "cmp-c-me@example.com")
    response = await client.get(
        "/members/me/match-comparison", headers=await _login(client, "cmp-c-me@example.com")
    )
    # "me" is not a UUID: a validation error, never somebody's comparison.
    assert response.status_code == 422
