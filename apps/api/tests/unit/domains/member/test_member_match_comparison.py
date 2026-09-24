"""Unit test: view_member_match_comparison() — 036-match-insights-benchmarks
US4. Through the database."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.models import FriendRequest
from app.domains.member.models import Member
from app.domains.member.player_dashboard import MetricValue
from app.domains.member.schemas import ComparisonMetric, MatchComparisonResponse
from app.domains.member.service import (
    MemberMatchFilters,
    _better,
    build_member_match_dashboard,
    view_member_match_comparison,
)
from app.domains.notification.models import Notification
from tests.unit.domains._match_history import (
    make_entry,
    make_group,
    make_member,
    make_played_match,
)

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
A_WINS = "A" * 21
A_WINS_BY_6 = "B" * 15 + "A" * 21


def _metric(comparison: MatchComparisonResponse, key: str) -> ComparisonMetric:
    return next(metric for metric in comparison.metrics if metric.key == key)


async def _friends(session: AsyncSession, tag: str) -> tuple[Member, Member]:
    me = await make_member(session, f"cmp-me-{tag}@example.com")
    friend = await make_member(session, f"cmp-friend-{tag}@example.com")
    session.add(FriendRequest(requester_id=me.id, addressee_id=friend.id, status="accepted"))
    await session.commit()
    return me, friend


async def test_both_sides_are_each_members_own_unfiltered_dashboard(
    db_session: AsyncSession,
) -> None:
    me, friend = await _friends(db_session, "a")
    group = await make_group(db_session, "Cmp a", match_mode="singles")
    mine = await make_entry(db_session, group, "我", me.id)
    theirs = await make_entry(db_session, group, "好友", friend.id)
    guest = await make_entry(db_session, group, "路人")
    for age in range(3):  # I beat the friend 21:15 three times…
        await make_played_match(
            db_session,
            group,
            team_a=[mine.id],
            team_b=[theirs.id],
            sides=A_WINS_BY_6,
            ended_at=NOW - timedelta(days=age),
        )
    for age in range(3, 5):  # …and the friend beats a guest 21:0 twice.
        await make_played_match(
            db_session,
            group,
            team_a=[theirs.id],
            team_b=[guest.id],
            sides=A_WINS,
            ended_at=NOW - timedelta(days=age),
        )

    comparison = await view_member_match_comparison(db_session, me.id, friend.id)
    my_dashboard = await build_member_match_dashboard(db_session, me.id, MemberMatchFilters())
    friend_dashboard = await build_member_match_dashboard(
        db_session, friend.id, MemberMatchFilters()
    )

    assert (comparison.my_total_matches, comparison.friend_total_matches) == (3, 5)
    assert [m.key for m in comparison.metrics] == [m.key for m in my_dashboard.metrics]
    for metric in my_dashboard.metrics:
        assert _metric(comparison, metric.key).me == metric.all, metric.key
    for metric in friend_dashboard.metrics:
        assert _metric(comparison, metric.key).friend == metric.all, metric.key

    points_for = _metric(comparison, "avg_points_for")
    assert points_for.me is not None and points_for.me.value == 21.0
    assert points_for.better == "me"  # the friend averages (3×15 + 2×21) / 5 = 17.4
    against = _metric(comparison, "avg_points_against")  # lower is better
    assert against.me is not None and against.friend is not None
    assert (against.me.value, against.friend.value) == (15.0, 12.6)
    assert against.better == "friend"
    assert _metric(comparison, "match_points_saved").better is None  # no direction
    assert _metric(comparison, "team_serve").better is not None  # both have serve records

    # Head to head, from MY side.
    assert comparison.head_to_head.as_partners is None
    meetings = comparison.head_to_head.as_opponents
    assert meetings is not None
    assert (meetings.matches, meetings.wins, meetings.losses) == (3, 3, 0)
    assert (meetings.win_rate, meetings.avg_margin) == (1.0, 6.0)


async def test_partners_are_found_too(db_session: AsyncSession) -> None:
    me, friend = await _friends(db_session, "b")
    group = await make_group(db_session, "Cmp b", match_mode="doubles")
    pair = [
        (await make_entry(db_session, group, "我", me.id)).id,
        (await make_entry(db_session, group, "好友", friend.id)).id,
    ]
    rivals = [
        (await make_entry(db_session, group, "對手一")).id,
        (await make_entry(db_session, group, "對手二")).id,
    ]
    await make_played_match(db_session, group, team_a=rivals, team_b=pair, sides=A_WINS)

    comparison = await view_member_match_comparison(db_session, me.id, friend.id)

    assert comparison.head_to_head.as_opponents is None
    together = comparison.head_to_head.as_partners
    assert together is not None
    assert (together.matches, together.losses, together.avg_margin) == (1, 1, -21.0)


async def test_friends_who_never_met(db_session: AsyncSession) -> None:
    me, friend = await _friends(db_session, "c")
    comparison = await view_member_match_comparison(db_session, me.id, friend.id)
    assert comparison.head_to_head.as_opponents is None
    assert comparison.head_to_head.as_partners is None
    assert all(m.me is None and m.friend is None and m.better is None for m in comparison.metrics)
    assert len(comparison.metrics) == 23


def _value(number: float | None, matches: int = 10) -> MetricValue:
    return MetricValue(value=number, numerator=0, denominator=10, matches_used=matches)


@pytest.mark.parametrize(
    ("direction", "friend", "me", "expected"),
    [
        ("higher", _value(0.4), _value(0.6), "me"),
        ("higher", _value(0.6), _value(0.4), "friend"),
        ("lower", _value(0.4), _value(0.6), "friend"),
        ("lower", _value(0.6), _value(0.4), "me"),
        ("higher", _value(0.5), _value(0.5), "tie"),
        (None, _value(0.4), _value(0.6), None),
        ("higher", None, _value(0.6), None),
        ("higher", _value(None), _value(0.6), None),
        ("higher", _value(0.4, 2), _value(0.6), None),  # under three matches: no verdict
        ("higher", _value(0.4), _value(0.6, 2), None),
        ("higher", _value(0.4, 3), _value(0.6, 3), "me"),
    ],
)
def test_which_side_is_better(
    direction: str | None, friend: MetricValue | None, me: MetricValue | None, expected: str | None
) -> None:
    assert _better(direction, friend, me) == expected  # type: ignore[arg-type]


async def test_the_gate_is_023s_and_is_checked_on_every_call(db_session: AsyncSession) -> None:
    me, friend = await _friends(db_session, "d")
    stranger = await make_member(db_session, "cmp-stranger@example.com")

    for target, code in ((me.id, "SELF_VIEW_NOT_SUPPORTED"), (stranger.id, "FRIENDSHIP_REQUIRED")):
        with pytest.raises(ApiError) as excinfo:
            await view_member_match_comparison(db_session, me.id, target)
        assert excinfo.value.error_code == code

    await view_member_match_comparison(db_session, me.id, friend.id)  # allowed…
    friend.share_match_records_with_friends = False
    await db_session.commit()
    with pytest.raises(ApiError) as excinfo:  # …until the friend says otherwise
        await view_member_match_comparison(db_session, me.id, friend.id)
    assert excinfo.value.error_code == "MATCH_RECORDS_PRIVATE"

    # My own sharing setting is irrelevant: I am looking at theirs, not showing mine.
    friend.share_match_records_with_friends = True
    me.share_match_records_with_friends = False
    await db_session.commit()
    await view_member_match_comparison(db_session, me.id, friend.id)


async def test_looking_writes_nothing_and_notifies_nobody(db_session: AsyncSession) -> None:
    me, friend = await _friends(db_session, "e")
    before = await db_session.scalar(select(func.count()).select_from(Notification))

    await view_member_match_comparison(db_session, me.id, friend.id)

    assert not db_session.new and not db_session.dirty and not db_session.deleted
    after = await db_session.scalar(select(func.count()).select_from(Notification))
    assert after == before  # FR-039
