"""Unit test: build_member_match_records() — 036-match-insights-benchmarks
US2. Through the database: partner/opponent records keyed by who a player is,
and the two exact filters (`partner_key` / `opponent_key`) a click on a row
turns into."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.member.models import Member
from app.domains.member.service import (
    MemberMatchFilters,
    build_member_match_dashboard,
    build_member_match_records,
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
WIN = "A" * 21  # team A 21:0
LOSS_BY_6 = "A" * 15 + "B" * 21  # A 15 : B 21


class _Club:
    """Me in a doubles group with a member partner, a guest partner, and two
    opponents; plus a second group where the same member plays under another
    nickname."""

    me: Member
    friend: Member
    group: Group
    my_entry: RosterEntry
    friend_entry: RosterEntry
    guest_partner: RosterEntry
    opp1: RosterEntry
    opp2: RosterEntry

    @classmethod
    async def create(cls, session: AsyncSession, tag: str) -> "_Club":
        self = cls()
        self.me = await make_member(session, f"me-{tag}@example.com")
        self.friend = await make_member(session, f"friend-{tag}@example.com")
        self.group = await make_group(session, f"Club {tag}", match_mode="doubles")
        self.my_entry = await make_entry(session, self.group, "我", self.me.id)
        self.friend_entry = await make_entry(session, self.group, "阿哲", self.friend.id)
        self.guest_partner = await make_entry(session, self.group, "路人")
        self.opp1 = await make_entry(session, self.group, "對手一")
        self.opp2 = await make_entry(session, self.group, "對手二")
        return self

    async def play(
        self, session: AsyncSession, partner: RosterEntry, sides: str, age_days: int
    ) -> None:
        await make_played_match(
            session,
            self.group,
            team_a=[self.my_entry.id, partner.id],
            team_b=[self.opp1.id, self.opp2.id],
            sides=sides,
            ended_at=NOW - timedelta(days=age_days),
        )


async def _records(session: AsyncSession, member: Member, **filters: object):  # type: ignore[no-untyped-def]
    return await build_member_match_records(session, member.id, **filters)  # type: ignore[arg-type]


async def test_partners_and_opponents_with_margin_and_highlights(db_session: AsyncSession) -> None:
    club = await _Club.create(db_session, "a")
    for age in range(5):
        await club.play(db_session, club.friend_entry, WIN, age)
    await club.play(db_session, club.guest_partner, LOSS_BY_6, 9)
    await club.play(db_session, club.guest_partner, LOSS_BY_6, 10)

    records = await _records(db_session, club.me)

    assert records.doubles_matches == 7
    partners = {r.player_key: r for r in records.partner_records}
    friend = partners[f"m:{club.friend.id}"]
    assert (friend.nickname, friend.member_id) == ("阿哲", str(club.friend.id))
    assert (friend.matches, friend.wins, friend.losses, friend.win_rate) == (5, 5, 0, 1.0)
    assert (friend.avg_margin, friend.low_sample) == (21.0, False)
    guest = partners[f"r:{club.guest_partner.id}"]
    assert (guest.member_id, guest.matches, guest.avg_margin, guest.low_sample) == (
        None,
        2,
        -6.0,
        True,
    )
    # Both opponents are charged every match; 5 × 21 − 2 × 6 over 7 matches.
    opponent = records.opponent_records[0]
    assert (opponent.matches, opponent.wins, opponent.avg_margin) == (7, 5, 13.3)
    assert len(records.opponent_records) == 2
    assert records.matchup_highlights.best_partner == f"m:{club.friend.id}"
    assert records.matchup_highlights.most_played_partner == f"m:{club.friend.id}"
    assert records.matchup_highlights.toughest_opponent is not None


async def test_one_member_in_two_groups_under_two_nicknames_is_one_row(
    db_session: AsyncSession,
) -> None:
    club = await _Club.create(db_session, "b")
    other = await make_group(db_session, "Other club", match_mode="singles")
    me_there = await make_entry(db_session, other, "我", club.me.id)
    friend_there = await make_entry(db_session, other, "Jay", club.friend.id)
    # Opponent here (older)…
    await make_played_match(
        db_session,
        club.group,
        team_a=[club.my_entry.id, club.guest_partner.id],
        team_b=[club.friend_entry.id, club.opp1.id],
        sides=WIN,
        ended_at=NOW - timedelta(days=5),
    )
    # …and opponent there, under another nickname (newer).
    await make_played_match(
        db_session,
        other,
        team_a=[me_there.id],
        team_b=[friend_there.id],
        sides=WIN,
        ended_at=NOW - timedelta(days=1),
    )

    records = await _records(db_session, club.me)

    rows = [r for r in records.opponent_records if r.player_key == f"m:{club.friend.id}"]
    assert len(rows) == 1
    assert (rows[0].matches, rows[0].nickname) == (2, "Jay")  # named as in the latest match


async def test_two_people_with_one_nickname_are_two_rows(db_session: AsyncSession) -> None:
    club = await _Club.create(db_session, "c")
    twin = await make_entry(db_session, club.group, "對手一")  # same nickname as opp1
    await club.play(db_session, club.guest_partner, WIN, 1)
    await make_played_match(
        db_session,
        club.group,
        team_a=[club.my_entry.id, club.guest_partner.id],
        team_b=[twin.id, club.opp2.id],
        sides=WIN,
        ended_at=NOW - timedelta(days=2),
    )

    records = await _records(db_session, club.me)

    same_name = [r for r in records.opponent_records if r.nickname == "對手一"]
    assert sorted(r.player_key for r in same_name) == sorted([f"r:{club.opp1.id}", f"r:{twin.id}"])
    assert all(r.matches == 1 for r in same_name)


async def test_singles_only_has_no_partner_records(db_session: AsyncSession) -> None:
    me = await make_member(db_session, "solo@example.com")
    group = await make_group(db_session, "Singles", match_mode="singles")
    mine = await make_entry(db_session, group, "我", me.id)
    rival = await make_entry(db_session, group, "對手")
    await make_played_match(db_session, group, team_a=[mine.id], team_b=[rival.id], sides=WIN)

    records = await _records(db_session, me)

    assert records.partner_records == []
    assert records.doubles_matches == 0
    assert len(records.opponent_records) == 1


async def test_matchups_add_no_query(db_session: AsyncSession) -> None:
    club = await _Club.create(db_session, "d")
    await club.play(db_session, club.friend_entry, WIN, 1)
    with count_selects(db_session) as few:
        await _records(db_session, club.me)
    for age in range(2, 8):
        await club.play(db_session, club.guest_partner, WIN, age)
    with count_selects(db_session) as many:
        await _records(db_session, club.me)
    assert len(few) == len(many)


# --- T020: the two exact filters ------------------------------------------


async def test_partner_key_keeps_only_matches_with_that_player_on_my_side(
    db_session: AsyncSession,
) -> None:
    club = await _Club.create(db_session, "e")
    await club.play(db_session, club.friend_entry, WIN, 1)
    await club.play(db_session, club.friend_entry, WIN, 2)
    await club.play(db_session, club.guest_partner, LOSS_BY_6, 3)
    # The friend as an OPPONENT must not count as "partnered with".
    await make_played_match(
        db_session,
        club.group,
        team_a=[club.my_entry.id, club.guest_partner.id],
        team_b=[club.friend_entry.id, club.opp1.id],
        sides=WIN,
        ended_at=NOW - timedelta(days=4),
    )

    with_friend = await _records(db_session, club.me, partner_key=f"m:{club.friend.id}")
    against_friend = await _records(db_session, club.me, opponent_key=f"m:{club.friend.id}")
    with_guest = await _records(db_session, club.me, partner_key=f"r:{club.guest_partner.id}")

    assert (with_friend.total_matches, with_friend.total_wins) == (2, 2)
    assert against_friend.total_matches == 1
    assert with_guest.total_matches == 2
    # The tables follow the filter like everything else.
    assert [r.player_key for r in with_friend.partner_records] == [f"m:{club.friend.id}"]


async def test_exact_key_does_not_drag_in_a_similar_nickname(db_session: AsyncSession) -> None:
    club = await _Club.create(db_session, "f")
    namesake = await make_entry(db_session, club.group, "阿哲哲")  # contains "阿哲"
    await club.play(db_session, club.friend_entry, WIN, 1)
    await club.play(db_session, namesake, WIN, 2)

    by_nickname = await _records(db_session, club.me, partners=["阿哲"])
    by_key = await _records(db_session, club.me, partner_key=f"m:{club.friend.id}")

    assert by_nickname.total_matches == 2  # the substring filter matches both
    assert by_key.total_matches == 1


async def test_exact_key_follows_the_member_into_another_group(db_session: AsyncSession) -> None:
    club = await _Club.create(db_session, "g")
    other = await make_group(db_session, "Other club g", match_mode="singles")
    me_there = await make_entry(db_session, other, "我", club.me.id)
    friend_there = await make_entry(db_session, other, "Jay", club.friend.id)
    await make_played_match(
        db_session, other, team_a=[me_there.id], team_b=[friend_there.id], sides=WIN
    )
    await make_played_match(
        db_session,
        club.group,
        team_a=[club.my_entry.id, club.guest_partner.id],
        team_b=[club.friend_entry.id, club.opp1.id],
        sides=WIN,
    )

    by_key = await _records(db_session, club.me, opponent_key=f"m:{club.friend.id}")
    by_nickname = await _records(db_session, club.me, opponents=["阿哲"])

    assert by_key.total_matches == 2
    assert by_nickname.total_matches == 1


async def test_exact_and_nickname_filters_combine(db_session: AsyncSession) -> None:
    club = await _Club.create(db_session, "h")
    await club.play(db_session, club.friend_entry, WIN, 1)
    await club.play(db_session, club.friend_entry, LOSS_BY_6, 2)

    both = await _records(
        db_session, club.me, partner_key=f"m:{club.friend.id}", result="loss", opponents=["對手一"]
    )
    assert both.total_matches == 1


async def test_a_well_formed_key_that_matches_nothing_is_an_empty_result(
    db_session: AsyncSession,
) -> None:
    club = await _Club.create(db_session, "i")
    await club.play(db_session, club.friend_entry, WIN, 1)

    nobody = await _records(db_session, club.me, opponent_key=f"m:{uuid.uuid4()}")

    assert nobody.total_matches == 0
    assert nobody.opponent_records == [] and nobody.partner_records == []


async def test_the_dashboard_covers_the_same_matches_under_the_same_key(
    db_session: AsyncSession,
) -> None:
    club = await _Club.create(db_session, "j")
    await club.play(db_session, club.friend_entry, WIN, 1)
    await club.play(db_session, club.guest_partner, WIN, 2)
    key = f"m:{club.friend.id}"

    records = await _records(db_session, club.me, partner_key=key)
    dashboard = await build_member_match_dashboard(
        db_session, club.me.id, MemberMatchFilters(partner_key=key)
    )

    assert records.total_matches == dashboard.total_matches == 1


async def test_the_four_filtered_routes_accept_exactly_the_same_filters() -> None:
    """The two dashboard routes share one dependency; the two match-records
    routes spell the same filters out by hand (research.md Decision 4). This
    is what keeps a filter from being added to one pair and not the other."""
    from fastapi.routing import APIRoute

    from app.main import app

    wanted = {
        "/members/me/match-records",
        "/members/{member_id}/match-records",
        "/members/me/match-dashboard",
        "/members/{member_id}/match-dashboard",
    }
    found: dict[str, set[str]] = {}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path in wanted and "GET" in route.methods:
            found[route.path] = {p.name for p in route.dependant.query_params}
            for dependency in route.dependant.dependencies:
                found[route.path] |= {p.name for p in dependency.query_params}
            found[route.path].discard("page")

    assert set(found) == wanted
    reference = found["/members/me/match-dashboard"]
    assert {"partner_key", "opponent_key", "opponent1", "match_mode"} <= reference
    assert all(params == reference for params in found.values()), found


async def test_matchup_insights_quote_the_record_tables_own_numbers(
    db_session: AsyncSession,
) -> None:
    """T024 / FR-002: the dashboard's matchup sentence and the partner table
    are built from the same filtered matches by the same function."""
    club = await _Club.create(db_session, "k")
    for age in range(6):
        await club.play(db_session, club.friend_entry, WIN, age)
    for age in range(10, 16):
        await club.play(db_session, club.guest_partner, LOSS_BY_6, age)

    records = await _records(db_session, club.me)
    dashboard = await build_member_match_dashboard(db_session, club.me.id, MemberMatchFilters())

    (sentence,) = [i for i in dashboard.insights.matchups if i.rule == "partner_above_overall"]
    row = next(r for r in records.partner_records if r.player_key == f"m:{club.friend.id}")
    assert sentence.player is not None
    assert (sentence.player.key, sentence.player.nickname) == (row.player_key, row.nickname)
    assert sentence.params["win_rate"] == row.win_rate == 1.0
    assert sentence.params["matches"] == row.matches == 6
    assert sentence.params["baseline"] == 0.5  # 6 won of 12 doubles matches
    assert (sentence.list, sentence.source, sentence.metric_key) == ("matchup", "matchup", None)
