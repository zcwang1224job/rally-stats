"""Unit test: build_group_standings() per-round win/loss tally
(RoundRecord: wins/losses/left) per research.md #4 of 005-member-view —
covers every state and every cause listed in FR-006~010, scope isolation
(FR-009), and 011-round-robin-scheduling's multi-match-per-round case
(singles full round-robin can complete several matches for one Member
within a single round_number, which the original single-outcome formula
silently collapsed to just the last match processed)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group, RoundHistory
from app.domains.group.schemas import GroupStandingsResponse, RoundRecord
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import build_group_standings
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant

pytestmark = pytest.mark.asyncio

T2 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
T3 = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
T4 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
BEFORE = T2 - timedelta(hours=1)
AFTER_T2_BEFORE_T3 = T2 + timedelta(minutes=30)


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Standings Formula Test",
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
) -> RosterEntry:
    entry = RosterEntry(
        group_id=group.id,
        nickname=f"P-{uuid.uuid4().hex[:6]}",
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


def _record(
    response: GroupStandingsResponse, roster_entry_id: uuid.UUID, round_number: int
) -> RoundRecord:
    for member in response.members:
        if member.roster_entry_id == str(roster_entry_id):
            return member.rounds[round_number]
    raise AssertionError("roster entry not found in standings response")


async def test_won_and_lost(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_round_history(db_session, group, 2, T2)
    winner = await _make_entry(db_session, group, joined_at=BEFORE)
    loser = await _make_entry(db_session, group, joined_at=BEFORE)
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[winner.id], team_b=[loser.id],
    )

    response = await build_group_standings(db_session, group)

    assert _record(response, winner.id, 2) == RoundRecord(wins=1, losses=0, left=False)
    assert _record(response, loser.id, 2) == RoundRecord(wins=0, losses=1, left=False)


async def test_multiple_matches_in_one_round_are_all_tallied(db_session: AsyncSession) -> None:
    """Regression: 011-round-robin-scheduling's singles full round-robin
    (_generate_singles_round_robin_matches) plays every other active
    member once within the SAME round_number — a Member can have several
    completed matches there before Next Round is pressed. The original
    formula kept only whichever match SQLAlchemy happened to return last
    for that (member, round) pair, silently discarding the rest."""
    group = await _make_group(db_session, match_mode="singles")
    await _make_round_history(db_session, group, 2, T2)
    p1 = await _make_entry(db_session, group, joined_at=BEFORE)
    p2 = await _make_entry(db_session, group, joined_at=BEFORE)
    p3 = await _make_entry(db_session, group, joined_at=BEFORE)
    p4 = await _make_entry(db_session, group, joined_at=BEFORE)
    # p1 plays (and beats) p2, then plays (and loses to) p3 — same round.
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[p1.id], team_b=[p2.id],
    )
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="B",
        team_a=[p1.id], team_b=[p3.id],
    )
    # An unrelated third match this round, not involving p1 at all.
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[p4.id], team_b=[p2.id],
    )

    response = await build_group_standings(db_session, group)

    assert _record(response, p1.id, 2) == RoundRecord(wins=1, losses=1, left=False)
    assert _record(response, p2.id, 2) == RoundRecord(wins=0, losses=2, left=False)
    assert _record(response, p3.id, 2) == RoundRecord(wins=1, losses=0, left=False)
    assert _record(response, p4.id, 2) == RoundRecord(wins=1, losses=0, left=False)


async def test_did_not_play_bench(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_round_history(db_session, group, 2, T2)
    bench = await _make_entry(db_session, group, joined_at=BEFORE)

    response = await build_group_standings(db_session, group)

    assert _record(response, bench.id, 2) == RoundRecord(wins=0, losses=0, left=False)


async def test_did_not_play_abandoned(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_round_history(db_session, group, 2, T2)
    a = await _make_entry(db_session, group, joined_at=BEFORE)
    b = await _make_entry(db_session, group, joined_at=BEFORE)
    await _make_match(
        db_session, group, round_number=2, status="abandoned", winner_team=None,
        team_a=[a.id], team_b=[b.id],
    )

    response = await build_group_standings(db_session, group)

    assert _record(response, a.id, 2) == RoundRecord(wins=0, losses=0, left=False)
    assert _record(response, b.id, 2) == RoundRecord(wins=0, losses=0, left=False)


async def test_did_not_play_in_progress_transient(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_round_history(db_session, group, 2, T2)
    a = await _make_entry(db_session, group, joined_at=BEFORE)
    b = await _make_entry(db_session, group, joined_at=BEFORE)
    await _make_match(
        db_session, group, round_number=2, status="in_progress", winner_team=None,
        team_a=[a.id], team_b=[b.id],
    )

    response = await build_group_standings(db_session, group)

    assert _record(response, a.id, 2) == RoundRecord(wins=0, losses=0, left=False)
    assert _record(response, b.id, 2) == RoundRecord(wins=0, losses=0, left=False)


async def test_did_not_play_joined_after_round_start(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_round_history(db_session, group, 2, T2)
    late = await _make_entry(db_session, group, joined_at=T2 + timedelta(hours=1))

    response = await build_group_standings(db_session, group)

    assert _record(response, late.id, 2) == RoundRecord(wins=0, losses=0, left=False)


async def test_left_state_is_irreversible(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, current_round_number=4)
    await _make_round_history(db_session, group, 2, T2)
    await _make_round_history(db_session, group, 3, T3)
    await _make_round_history(db_session, group, 4, T4)
    leaver = await _make_entry(
        db_session, group, joined_at=BEFORE, status="left", left_at=AFTER_T2_BEFORE_T3
    )

    response = await build_group_standings(db_session, group)

    # left_at is after round 2 started
    assert _record(response, leaver.id, 2) == RoundRecord(wins=0, losses=0, left=False)
    assert _record(response, leaver.id, 3) == RoundRecord(wins=0, losses=0, left=True)
    assert _record(response, leaver.id, 4) == RoundRecord(wins=0, losses=0, left=True)  # never reverts


async def test_left_state_basis_consistent_in_manual_mode(db_session: AsyncSession) -> None:
    group = await _make_group(
        db_session, current_round_number=3, scheduling_mechanism="manual"
    )
    await _make_round_history(db_session, group, 2, T2)
    await _make_round_history(db_session, group, 3, T3)
    kicked = await _make_entry(
        db_session, group, joined_at=BEFORE, status="kicked", left_at=AFTER_T2_BEFORE_T3
    )

    response = await build_group_standings(db_session, group)

    assert _record(response, kicked.id, 2) == RoundRecord(wins=0, losses=0, left=False)
    assert _record(response, kicked.id, 3) == RoundRecord(wins=0, losses=0, left=True)


async def test_scope_isolation_excludes_other_groups(db_session: AsyncSession) -> None:
    group_a = await _make_group(db_session)
    group_b = await _make_group(db_session)
    await _make_round_history(db_session, group_a, 2, T2)
    await _make_round_history(db_session, group_b, 2, T2)
    entry_a = await _make_entry(db_session, group_a, joined_at=BEFORE)
    entry_b1 = await _make_entry(db_session, group_b, joined_at=BEFORE)
    entry_b2 = await _make_entry(db_session, group_b, joined_at=BEFORE)
    await _make_match(
        db_session, group_b, round_number=2, status="completed", winner_team="A",
        team_a=[entry_b1.id], team_b=[entry_b2.id],
    )

    response = await build_group_standings(db_session, group_a)

    member_ids = {member.roster_entry_id for member in response.members}
    assert member_ids == {str(entry_a.id)}
    assert _record(response, entry_a.id, 2) == RoundRecord(wins=0, losses=0, left=False)
