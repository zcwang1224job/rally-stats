"""Unit test: list_benchmark_groups() / build_group_benchmark() —
036-match-insights-benchmarks US3. Through the database: who counts as a
player of the group, that "my" numbers are the dashboard's own, and that the
work does not grow a query per match."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.member.models import Member
from app.domains.member.schemas import GroupBenchmarkMetric, GroupBenchmarkResponse
from app.domains.member.service import (
    MemberMatchFilters,
    build_group_benchmark,
    build_member_match_dashboard,
    list_benchmark_groups,
)
from app.domains.roster.models import RosterEntry
from tests.unit.domains._match_history import (
    make_entry,
    make_group,
    make_member,
    make_played_match,
)
from tests.unit.domains.group.test_match_stat_inputs import count_selects

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
A_WINS = "A" * 21
B_WINS_BY_6 = "A" * 15 + "B" * 21


def _metric(benchmark: GroupBenchmarkResponse, key: str) -> GroupBenchmarkMetric:
    return next(metric for metric in benchmark.metrics if metric.key == key)


async def _singles(
    session: AsyncSession, group: Group, a: RosterEntry, b: RosterEntry, sides: str, age: int
) -> None:
    await make_played_match(
        session,
        group,
        team_a=[a.id],
        team_b=[b.id],
        sides=sides,
        ended_at=NOW - timedelta(days=age),
    )


class _League:
    """A singles group: me (a member), another member, and two guests. Each
    pair plays enough that everyone has five matches."""

    me: Member
    group: Group
    mine: RosterEntry
    rival: RosterEntry
    guest1: RosterEntry
    guest2: RosterEntry

    @classmethod
    async def create(cls, session: AsyncSession, tag: str) -> "_League":
        self = cls()
        self.me = await make_member(session, f"bench-me-{tag}@example.com")
        other = await make_member(session, f"bench-rival-{tag}@example.com")
        self.group = await make_group(session, f"League {tag}", match_mode="singles")
        self.mine = await make_entry(session, self.group, "我", self.me.id)
        self.rival = await make_entry(session, self.group, "會員對手", other.id)
        self.guest1 = await make_entry(session, self.group, "訪客一")
        self.guest2 = await make_entry(session, self.group, "訪客二")
        return self

    async def round_robin(self, session: AsyncSession, rounds: int = 2) -> None:
        """I beat everyone 21:0; among the others the first-listed wins by 6."""
        players = [self.mine, self.rival, self.guest1, self.guest2]
        age = 0
        for _ in range(rounds):
            for i, first in enumerate(players):
                for second in players[i + 1 :]:
                    sides = (
                        A_WINS
                        if first is self.mine
                        else B_WINS_BY_6.replace("A", "x").replace("B", "A").replace("x", "B")
                    )
                    await _singles(session, self.group, first, second, sides, age)
                    age += 1


async def test_guests_and_members_are_all_players_of_the_group(db_session: AsyncSession) -> None:
    league = await _League.create(db_session, "a")
    await league.round_robin(db_session)  # 6 matches each

    benchmark = await build_group_benchmark(db_session, league.me.id, league.group.id)

    assert benchmark.group.name == "League a"
    assert (benchmark.total_matches, benchmark.my_matches) == (12, 6)
    points_for = _metric(benchmark, "avg_points_for")
    assert points_for.status == "ok"
    assert points_for.pool_size == 4  # two members and two guests
    assert points_for.rank == 1  # I scored 21 every time
    assert points_for.mine is not None and points_for.mine.value == 21.0


async def test_my_value_is_exactly_my_dashboards_value_for_this_group(
    db_session: AsyncSession,
) -> None:
    league = await _League.create(db_session, "b")
    await league.round_robin(db_session)
    # A match of mine in ANOTHER group must not move my in-group numbers.
    elsewhere = await make_group(db_session, "Elsewhere b", match_mode="singles")
    me_there = await make_entry(db_session, elsewhere, "我", league.me.id)
    someone = await make_entry(db_session, elsewhere, "路人")
    await _singles(db_session, elsewhere, someone, me_there, A_WINS, 0)  # I lose 0:21

    benchmark = await build_group_benchmark(db_session, league.me.id, league.group.id)
    dashboard = await build_member_match_dashboard(
        db_session, league.me.id, MemberMatchFilters(group_id=league.group.id)
    )

    for metric in dashboard.metrics:
        assert _metric(benchmark, metric.key).mine == metric.all, metric.key  # FR-029
    assert benchmark.my_matches == dashboard.total_matches == 6


async def test_a_member_who_left_and_rejoined_is_one_player(db_session: AsyncSession) -> None:
    league = await _League.create(db_session, "c")
    await league.round_robin(db_session)  # 6 matches each
    # My second stint: a new roster row, three more matches.
    league.mine.status = "left"
    await db_session.commit()
    again = await make_entry(db_session, league.group, "我又來了", league.me.id)
    for index, opponent in enumerate([league.rival, league.guest1, league.guest2]):
        await _singles(db_session, league.group, again, opponent, A_WINS, 50 + index)

    benchmark = await build_group_benchmark(db_session, league.me.id, league.group.id)

    assert benchmark.my_matches == 9
    points_for = _metric(benchmark, "avg_points_for")
    assert points_for.mine is not None and points_for.mine.matches_used == 9
    # Four players — me once, not twice.
    assert points_for.pool_size == 4


async def test_players_who_left_still_count(db_session: AsyncSession) -> None:
    league = await _League.create(db_session, "d")
    await league.round_robin(db_session)
    league.guest2.status = "kicked"
    league.rival.status = "left"
    await db_session.commit()

    benchmark = await build_group_benchmark(db_session, league.me.id, league.group.id)

    assert _metric(benchmark, "avg_points_for").pool_size == 4


async def test_a_simple_scoring_group_only_has_the_final_score_metrics(
    db_session: AsyncSession,
) -> None:
    league = await _League.create(db_session, "e")
    players = [league.mine, league.rival, league.guest1, league.guest2]
    age = 0
    for _ in range(2):
        for i, first in enumerate(players):
            for second in players[i + 1 :]:
                await make_played_match(
                    db_session,
                    league.group,
                    team_a=[first.id],
                    team_b=[second.id],
                    sides=A_WINS,
                    log="none",
                    ended_at=NOW - timedelta(days=age),
                )
                age += 1

    benchmark = await build_group_benchmark(db_session, league.me.id, league.group.id)

    usable = {m.key for m in benchmark.metrics if m.status != "pool_too_small"}
    assert "avg_points_for" in usable and "avg_points_against" in usable
    assert usable <= {"avg_points_for", "avg_points_against", "avg_win_margin", "avg_loss_margin"}
    assert _metric(benchmark, "team_serve").mine is None


async def test_never_a_member_of_the_group_is_refused(db_session: AsyncSession) -> None:
    league = await _League.create(db_session, "f")
    stranger = await make_member(db_session, "bench-stranger@example.com")

    with pytest.raises(ApiError) as excinfo:
        await build_group_benchmark(db_session, stranger.id, league.group.id)
    assert (excinfo.value.error_code, excinfo.value.status_code) == (
        "GROUP_MEMBERSHIP_NEVER_HELD",
        403,
    )

    with pytest.raises(ApiError) as excinfo:
        await build_group_benchmark(db_session, league.me.id, uuid.uuid4())  # no such group
    assert excinfo.value.error_code == "GROUP_MEMBERSHIP_NEVER_HELD"


async def test_query_count_does_not_grow_with_the_number_of_matches(
    db_session: AsyncSession,
) -> None:
    league = await _League.create(db_session, "g")
    await league.round_robin(db_session, rounds=1)
    with count_selects(db_session) as few:
        await build_group_benchmark(db_session, league.me.id, league.group.id)
    await league.round_robin(db_session, rounds=3)
    with count_selects(db_session) as many:
        await build_group_benchmark(db_session, league.me.id, league.group.id)
    assert len(few) == len(many)


async def test_benchmark_insights_quote_the_metrics_own_numbers(db_session: AsyncSession) -> None:
    league = await _League.create(db_session, "h")
    await league.round_robin(db_session)

    benchmark = await build_group_benchmark(db_session, league.me.id, league.group.id)

    assert benchmark.insights.benchmark_group_name == "League h"
    from_group = [
        item
        for item in benchmark.insights.strengths + benchmark.insights.weaknesses
        if item.source == "benchmark"
    ]
    assert from_group, "I lead every metric in a four-player pool"
    for item in from_group:
        assert item.rule == "benchmark_quartile" and item.metric_key is not None
        metric = _metric(benchmark, item.metric_key)
        assert metric.mine is not None
        assert item.params["mine"] == metric.mine.value
        assert item.params["group_average"] == metric.group_average
        assert item.params["rank"] == metric.rank
        assert item.params["pool_size"] == metric.pool_size


# --- list_benchmark_groups() ----------------------------------------------


async def test_groups_i_ever_belonged_to_most_matches_first(db_session: AsyncSession) -> None:
    league = await _League.create(db_session, "i")
    await league.round_robin(db_session, rounds=1)  # 3 of mine
    quiet = await make_group(db_session, "Quiet i", match_mode="singles")
    await make_entry(db_session, quiet, "我", league.me.id, status="left")
    busy = await make_group(db_session, "Busy i", match_mode="singles")
    me_busy = await make_entry(db_session, busy, "我", league.me.id, status="kicked")
    rival = await make_entry(db_session, busy, "對手")
    for age in range(5):
        await _singles(db_session, busy, me_busy, rival, A_WINS, age)
    busy.status = "disbanded"
    # A group I only ever played in as a guest is not mine to compare.
    guest_only = await make_group(db_session, "Guest i", match_mode="singles")
    await make_entry(db_session, guest_only, "我（訪客）")
    await db_session.commit()

    listed = await list_benchmark_groups(db_session, league.me.id)

    assert [(g.name, g.my_completed_matches, g.member_status) for g in listed.groups] == [
        ("Busy i", 5, "kicked"),
        ("League i", 3, "active"),
        ("Quiet i", 0, "left"),
    ]
    assert listed.groups[0].status == "disbanded"
    # Every listed group can actually be opened — same predicate as the check.
    for option in listed.groups:
        await build_group_benchmark(db_session, league.me.id, uuid.UUID(option.group_id))


async def test_no_groups(db_session: AsyncSession) -> None:
    nobody = await make_member(db_session, "bench-nobody@example.com")
    assert (await list_benchmark_groups(db_session, nobody.id)).groups == []
