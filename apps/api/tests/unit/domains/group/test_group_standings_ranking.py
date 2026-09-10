"""Unit test: 018-group-leaderboard's ranking layer on top of
`build_group_standings()` — `rank`/`total_wins`/`total_losses` per
research.md #2/#3/#6. T001 (a)-(f)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group, RoundHistory
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import build_group_standings
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant

pytestmark = pytest.mark.asyncio

T2 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
BEFORE = T2 - timedelta(hours=1)


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Standings Ranking Test",
        "max_members": 16,
        "match_mode": "doubles",
        "scheduling_mechanism": "fair_rotation",
        "current_member_count": 1,
        "current_round_number": 2,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
    }
    defaults.update(overrides)
    group = Group(**defaults)  # type: ignore[arg-type]
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_round_history(
    session: AsyncSession, group: Group, round_number: int, started_at: datetime
) -> None:
    session.add(RoundHistory(group_id=group.id, round_number=round_number, started_at=started_at))
    await session.commit()


async def _make_entry(
    session: AsyncSession,
    group: Group,
    *,
    joined_at: datetime,
    status: str = "active",
    left_at: datetime | None = None,
    nickname: str | None = None,
) -> RosterEntry:
    entry = RosterEntry(
        group_id=group.id,
        nickname=nickname or f"P-{uuid.uuid4().hex[:6]}",
        status=status,
        joined_at=joined_at,
        left_at=left_at,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def _make_match(
    session: AsyncSession,
    group: Group,
    *,
    round_number: int,
    status: str,
    winner_team: str | None,
    team_a: list[uuid.UUID],
    team_b: list[uuid.UUID],
) -> Match:
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=round_number,
        status=status,
        winner_team=winner_team,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
    )
    session.add(match)
    await session.flush()
    for pid in team_a:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="A"))
    for pid in team_b:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="B"))
    await session.commit()
    return match


def _row(response, roster_entry_id: uuid.UUID):  # type: ignore[no-untyped-def]
    for member in response.members:
        if member.roster_entry_id == str(roster_entry_id):
            return member
    raise AssertionError("roster entry not found in standings response")


async def test_ranks_by_total_wins_descending(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_round_history(db_session, group, 2, T2)
    top = await _make_entry(db_session, group, joined_at=BEFORE)
    mid = await _make_entry(db_session, group, joined_at=BEFORE)
    bottom = await _make_entry(db_session, group, joined_at=BEFORE)
    # top: 2 wins, mid: 1 win, bottom: 0 wins.
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[top.id], team_b=[mid.id],
    )
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[top.id], team_b=[bottom.id],
    )
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[mid.id], team_b=[bottom.id],
    )

    response = await build_group_standings(db_session, group)

    assert [m.roster_entry_id for m in response.members] == [
        str(top.id), str(mid.id), str(bottom.id),
    ]
    assert _row(response, top.id).rank == 1
    assert _row(response, top.id).total_wins == 2
    assert _row(response, mid.id).rank == 2
    assert _row(response, mid.id).total_wins == 1
    assert _row(response, mid.id).total_losses == 1
    assert _row(response, bottom.id).rank == 3
    assert _row(response, bottom.id).total_losses == 2


async def test_tied_total_wins_share_rank_and_skip_next(db_session: AsyncSession) -> None:
    """Standard competition ranking ("1224"): two members tied for 2nd
    place both show rank 2, and the next member is rank 4, not 3."""
    group = await _make_group(db_session)
    await _make_round_history(db_session, group, 2, T2)
    first = await _make_entry(db_session, group, joined_at=BEFORE)
    tied_a = await _make_entry(db_session, group, joined_at=BEFORE)
    tied_b = await _make_entry(db_session, group, joined_at=BEFORE + timedelta(minutes=1))
    last = await _make_entry(db_session, group, joined_at=BEFORE)
    # first: 3 wins; tied_a/tied_b: 1 win each; last: 0 wins.
    for _ in range(3):
        await _make_match(
            db_session, group, round_number=2, status="completed", winner_team="A",
            team_a=[first.id], team_b=[last.id],
        )
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[tied_a.id], team_b=[last.id],
    )
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[tied_b.id], team_b=[last.id],
    )

    response = await build_group_standings(db_session, group)

    assert _row(response, first.id).rank == 1
    assert _row(response, tied_a.id).rank == 2
    assert _row(response, tied_b.id).rank == 2
    assert _row(response, last.id).rank == 4
    # tied_a joined before tied_b -> tied_a listed first among the tie.
    ids_in_order = [m.roster_entry_id for m in response.members]
    assert ids_in_order.index(str(tied_a.id)) < ids_in_order.index(str(tied_b.id))


async def test_no_completed_matches_still_appears_with_zero_totals(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_round_history(db_session, group, 2, T2)
    bench = await _make_entry(db_session, group, joined_at=BEFORE)

    response = await build_group_standings(db_session, group)

    row = _row(response, bench.id)
    assert row.total_wins == 0
    assert row.total_losses == 0
    assert row.rank == 1


async def test_left_member_excluded_but_opponent_stats_unaffected(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, current_round_number=3)
    await _make_round_history(db_session, group, 2, T2)
    winner = await _make_entry(db_session, group, joined_at=BEFORE)
    leaver = await _make_entry(
        db_session, group, joined_at=BEFORE, status="left", left_at=T2 + timedelta(hours=1)
    )
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[winner.id], team_b=[leaver.id],
    )

    response = await build_group_standings(db_session, group)

    member_ids = {m.roster_entry_id for m in response.members}
    assert str(leaver.id) not in member_ids
    assert str(winner.id) in member_ids
    assert _row(response, winner.id).total_wins == 1
    assert _row(response, winner.id).total_losses == 0


async def test_fixed_partner_ranks_individually_not_by_partnership(
    db_session: AsyncSession,
) -> None:
    """FR-009: fixed_partner doubles still ranks each of the 4 players
    independently — the two winners on team A each get their own win, the
    two losers on team B each get their own loss, never merged as a pair."""
    group = await _make_group(db_session, scheduling_mechanism="fixed_partner")
    await _make_round_history(db_session, group, 2, T2)
    a1 = await _make_entry(db_session, group, joined_at=BEFORE)
    a2 = await _make_entry(db_session, group, joined_at=BEFORE)
    b1 = await _make_entry(db_session, group, joined_at=BEFORE)
    b2 = await _make_entry(db_session, group, joined_at=BEFORE)
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )

    response = await build_group_standings(db_session, group)

    assert _row(response, a1.id).total_wins == 1
    assert _row(response, a1.id).total_losses == 0
    assert _row(response, a2.id).total_wins == 1
    assert _row(response, a2.id).total_losses == 0
    assert _row(response, b1.id).total_wins == 0
    assert _row(response, b1.id).total_losses == 1
    assert _row(response, b2.id).total_wins == 0
    assert _row(response, b2.id).total_losses == 1
    # Both winners tied at 1 win, ranked ahead of both losers tied at 0.
    assert _row(response, a1.id).rank == 1
    assert _row(response, a2.id).rank == 1
    assert _row(response, b1.id).rank == 3
    assert _row(response, b2.id).rank == 3
