"""Unit test: build_member_match_dashboard() —
034-clutch-points-player-dashboard US2. Through the database: the batch
load, the conversion to "my" point of view, and the promise that a match
contributes exactly what its own detail dialog shows (FR-003)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.service import build_match_record_detail
from app.domains.member.models import Member
from app.domains.member.schemas import DashboardMetric, MemberMatchDashboardResponse
from app.domains.member.service import (
    MemberMatchFilters,
    build_member_match_dashboard,
    build_member_match_records,
)
from app.domains.roster.models import RosterEntry
from tests.unit.domains._match_history import (
    Shot,
    make_entry,
    make_group,
    make_member,
    make_played_match,
)
from tests.unit.domains.group.test_match_stat_inputs import count_selects

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
# 0:5 down, back to win 21:19 — reaches the endgame, never reaches deuce.
COMEBACK = "BBBBB" + "AB" * 13 + "A" * 7 + "BA"


def _metric(dashboard: MemberMatchDashboardResponse, key: str) -> DashboardMetric:
    return next(metric for metric in dashboard.metrics if metric.key == key)


def _used(dashboard: MemberMatchDashboardResponse, key: str) -> int:
    value = _metric(dashboard, key).all
    return value.matches_used if value is not None else 0


class _Doubles:
    """Me + a partner (both on team B unless told otherwise) against two
    guests, in one doubles group."""

    group: Group
    member: Member
    me: RosterEntry
    partner: RosterEntry
    opp1: RosterEntry
    opp2: RosterEntry

    @classmethod
    async def create(cls, session: AsyncSession, email: str = "dash@example.com") -> "_Doubles":
        self = cls()
        self.group = await make_group(session, match_mode="doubles")
        self.member = await make_member(session, email)
        self.me = await make_entry(session, self.group, "我", self.member.id)
        self.partner = await make_entry(session, self.group, "搭檔")
        self.opp1 = await make_entry(session, self.group, "對手一")
        self.opp2 = await make_entry(session, self.group, "對手二")
        return self

    @property
    def mine(self) -> list[uuid.UUID]:
        return [self.me.id, self.partner.id]

    @property
    def theirs(self) -> list[uuid.UUID]:
        return [self.opp1.id, self.opp2.id]


async def test_no_matches_is_the_empty_response(db_session: AsyncSession) -> None:
    member = await make_member(db_session, "nobody@example.com")

    dashboard = await build_member_match_dashboard(db_session, member.id, MemberMatchFilters())

    assert dashboard.total_matches == 0 and dashboard.has_comparison is False
    assert dashboard.metrics == [] and dashboard.trends == [] and dashboard.landing is None


async def test_one_match_contributes_exactly_what_its_detail_shows(
    db_session: AsyncSession,
) -> None:
    setup = await _Doubles.create(db_session)
    # I'm on team B here, so "my" numbers are the detail's B rows.
    match = await make_played_match(
        db_session, setup.group, team_a=setup.theirs, team_b=setup.mine,
        sides=COMEBACK.replace("A", "x").replace("B", "A").replace("x", "B"),  # B wins 21:19
        shots={
            0: Shot(scorer=setup.opp1.id, loser=setup.me.id, landing=(0.2, 0.3)),
            5: Shot(scorer=setup.me.id, loser=setup.opp2.id, landing=(0.1, 0.8)),
            7: Shot(scorer=setup.me.id, loser=None, landing=None),  # player only, no landing
        },
    )

    dashboard = await build_member_match_dashboard(
        db_session, setup.member.id, MemberMatchFilters()
    )
    detail = await build_match_record_detail(db_session, match)

    assert dashboard.total_matches == 1
    assert detail.serve_stats is not None and detail.clutch_stats is not None
    serve_b = detail.serve_stats.teams[1]
    me_serve = next(
        p for p in detail.serve_stats.players if p.roster_entry_id == str(setup.me.id)
    )
    endgame_b = detail.clutch_stats.endgame[1] if detail.clutch_stats.endgame else None
    state_b = detail.clutch_stats.by_state[1]
    assert serve_b.team == "B" and state_b.team == "B" and endgame_b is not None

    def pair(key: str) -> tuple[int, int]:
        value = _metric(dashboard, key).all
        assert value is not None, key
        return value.numerator, value.denominator

    assert pair("team_serve") == (serve_b.serve_points_won, serve_b.serve_points_total)
    assert pair("team_receive") == (serve_b.receive_points_won, serve_b.receive_points_total)
    assert pair("own_serve") == (me_serve.serve_points_won, me_serve.serve_points_total)
    assert pair("endgame") == (endgame_b.won, endgame_b.total)
    assert pair("when_trailing") == (state_b.trailing.won, state_b.trailing.total)
    assert pair("when_leading") == (state_b.leading.won, state_b.leading.total)
    assert pair("match_point_conversion") == (1, 1)
    mine = next(p for p in detail.player_stats if p.roster_entry_id == str(setup.me.id))
    assert pair("points_scored") == (mine.scored_count, 1) == (2, 1)
    assert pair("points_lost") == (mine.fault_count, 1) == (1, 1)
    assert pair("avg_points_for") == (21, 1) and pair("avg_win_margin") == (2, 1)
    assert _metric(dashboard, "deuce").all is None  # never got there
    assert _metric(dashboard, "avg_loss_margin").all is None  # no losses


async def test_each_metric_counts_only_the_matches_that_have_its_data(
    db_session: AsyncSession,
) -> None:
    setup = await _Doubles.create(db_session)
    singles_group = await make_group(db_session, "Singles", match_mode="singles")
    me_singles = await make_entry(db_session, singles_group, "我", setup.member.id)
    rival = await make_entry(db_session, singles_group, "單打對手")
    common = {"team_a": setup.mine, "team_b": setup.theirs}

    # detailed scoring, with serve records
    await make_played_match(
        db_session, setup.group, sides=COMEBACK, **common,
        shots={0: Shot(scorer=setup.opp1.id, loser=setup.me.id, landing=(0.9, 0.5))},
    )
    # simple scoring, with serve records
    await make_played_match(db_session, setup.group, sides="A" * 21, **common)
    # pre-030: a complete point log but no serve records
    await make_played_match(
        db_session, setup.group, sides="A" * 21, serve_records=False, **common
    )
    # recording started mid-match
    await make_played_match(db_session, setup.group, sides="B" * 21, log="partial", **common)
    # singles
    await make_played_match(
        db_session, singles_group, team_a=[me_singles.id], team_b=[rival.id], sides="A" * 21
    )
    # 7-point format: no endgame phase
    await make_played_match(
        db_session, setup.group, sides="A" * 7, target_score=7, cap_score=10, **common
    )

    dashboard = await build_member_match_dashboard(
        db_session, setup.member.id, MemberMatchFilters()
    )

    assert dashboard.total_matches == 6
    assert len(dashboard.metrics) == 18
    assert _used(dashboard, "avg_points_for") == 6  # the partial one still counts here
    assert _used(dashboard, "when_tied") == 5  # everything but the partial log
    assert _used(dashboard, "endgame") == 4  # ... and but the 7-point match
    assert _used(dashboard, "team_serve") == 4  # complete log AND serve records
    assert _used(dashboard, "own_serve") == 3  # ... and doubles
    assert _used(dashboard, "points_scored") == 1  # only where players were recorded
    assert _used(dashboard, "avg_loss_margin") == 1


async def test_filters_select_the_same_matches_as_the_match_list(
    db_session: AsyncSession,
) -> None:
    setup = await _Doubles.create(db_session)
    singles_group = await make_group(db_session, "Singles", match_mode="singles")
    me_singles = await make_entry(db_session, singles_group, "我", setup.member.id)
    rival = await make_entry(db_session, singles_group, "單打對手")
    other_partner = await make_entry(db_session, setup.group, "另一位搭檔")

    await make_played_match(
        db_session, setup.group, team_a=setup.mine, team_b=setup.theirs,
        sides="A" * 21, ended_at=NOW - timedelta(days=30),
    )
    await make_played_match(
        db_session, setup.group, team_a=[setup.me.id, other_partner.id], team_b=setup.theirs,
        sides="A" * 21, ended_at=NOW - timedelta(days=2),
    )
    await make_played_match(
        db_session, singles_group, team_a=[me_singles.id], team_b=[rival.id],
        sides="B" * 21, ended_at=NOW - timedelta(days=1),
    )

    cases: list[tuple[MemberMatchFilters, dict[str, object], int]] = [
        (MemberMatchFilters(), {}, 3),
        (MemberMatchFilters(match_mode="doubles"), {"match_mode": "doubles"}, 2),
        (
            MemberMatchFilters(date_from=(NOW - timedelta(days=5)).date()),
            {"date_from": (NOW - timedelta(days=5)).date()},
            2,
        ),
        (MemberMatchFilters(partners=("另一位",)), {"partners": ["另一位"]}, 1),
        (MemberMatchFilters(result="loss"), {"result": "loss"}, 1),
        (MemberMatchFilters(opponents=("不存在",)), {"opponents": ["不存在"]}, 0),
    ]
    for filters, keyword_arguments, expected in cases:
        dashboard = await build_member_match_dashboard(db_session, setup.member.id, filters)
        records = await build_member_match_records(
            db_session, setup.member.id, **keyword_arguments  # type: ignore[arg-type]
        )
        assert dashboard.total_matches == records.total_matches == expected, filters


async def test_guest_era_match_counts_only_once_it_is_bound_to_the_member(
    db_session: AsyncSession,
) -> None:
    setup = await _Doubles.create(db_session)
    as_guest = await make_entry(db_session, setup.group, "訪客時期的我")
    await make_played_match(
        db_session, setup.group, team_a=[as_guest.id, setup.partner.id], team_b=setup.theirs,
        sides="A" * 21,
    )

    before = await build_member_match_dashboard(db_session, setup.member.id, MemberMatchFilters())
    as_guest.member_id = setup.member.id  # what 028's binding does
    await db_session.commit()
    after = await build_member_match_dashboard(db_session, setup.member.id, MemberMatchFilters())

    assert (before.total_matches, after.total_matches) == (0, 1)


async def test_query_count_does_not_grow_with_the_number_of_matches(
    db_session: AsyncSession,
) -> None:
    setup = await _Doubles.create(db_session)
    for _ in range(2):
        await make_played_match(
            db_session, setup.group, team_a=setup.mine, team_b=setup.theirs, sides="A" * 21
        )
    with count_selects(db_session) as few:
        await build_member_match_dashboard(db_session, setup.member.id, MemberMatchFilters())

    for _ in range(7):
        await make_played_match(
            db_session, setup.group, team_a=setup.mine, team_b=setup.theirs, sides="A" * 21
        )
    with count_selects(db_session) as many:
        dashboard = await build_member_match_dashboard(
            db_session, setup.member.id, MemberMatchFilters()
        )

    assert dashboard.total_matches == 9
    assert len(few) == len(many)
