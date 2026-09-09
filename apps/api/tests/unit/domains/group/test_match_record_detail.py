"""Unit test: get_completed_match_or_404()/build_match_record_detail() —
016-match-score-timeline research.md #2/#3. Three-state record_completeness
detection, elapsed_seconds conversion, and the created_at/id ordering
tie-breaker (research.md #3)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import build_match_record_detail, get_completed_match_or_404
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant, ScoreEvent

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Match Record Detail Test",
        max_members=8,
        match_mode="singles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_entry(session: AsyncSession, group: Group, nickname: str) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def _make_match(
    session: AsyncSession,
    group: Group,
    *,
    status: str = "completed",
    winner_team: str | None = "A",
    score_a: int = 21,
    score_b: int = 18,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    team_a: list[uuid.UUID],
    team_b: list[uuid.UUID],
) -> Match:
    now = datetime.now(UTC)
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=1,
        status=status,
        winner_team=winner_team,
        score_a=score_a,
        score_b=score_b,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
        started_at=started_at if started_at is not None else now,
        ended_at=ended_at if ended_at is not None else now,
    )
    session.add(match)
    await session.flush()
    for pid in team_a:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="A"))
    for pid in team_b:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="B"))
    await session.commit()
    await session.refresh(match)
    return match


async def _add_event(
    session: AsyncSession,
    match: Match,
    *,
    side: str,
    delta: int,
    score_a: int,
    score_b: int,
    created_at: datetime,
) -> ScoreEvent:
    event = ScoreEvent(
        match_id=match.id,
        group_id=match.group_id,
        side=side,
        delta=delta,
        score_a=score_a,
        score_b=score_b,
        source="control_panel",
        created_at=created_at,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def test_get_completed_match_or_404_rejects_missing_match(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ApiError) as exc_info:
        await get_completed_match_or_404(db_session, uuid.uuid4())
    assert exc_info.value.error_code == "MATCH_NOT_FOUND"


async def test_get_completed_match_or_404_rejects_non_completed_match(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")
    match = await _make_match(
        db_session, group, status="in_progress", winner_team=None, team_a=[a.id], team_b=[b.id]
    )

    with pytest.raises(ApiError) as exc_info:
        await get_completed_match_or_404(db_session, match.id)
    assert exc_info.value.error_code == "MATCH_NOT_FOUND"


async def test_no_events_yields_none_completeness(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")
    match = await _make_match(db_session, group, team_a=[a.id], team_b=[b.id])

    detail = await build_match_record_detail(db_session, match)

    assert detail.record_completeness == "none"
    assert detail.events == []
    assert detail.score_a == 21
    assert detail.score_b == 18
    assert detail.winner_team == "A"


async def test_first_event_at_one_zero_yields_complete(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")
    match = await _make_match(
        db_session, group, score_a=2, score_b=1, team_a=[a.id], team_b=[b.id]
    )
    start = match.started_at
    assert start is not None
    await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=10),
    )
    await _add_event(
        db_session, match, side="B", delta=1, score_a=1, score_b=1,
        created_at=start + timedelta(seconds=20),
    )
    await _add_event(
        db_session, match, side="A", delta=1, score_a=2, score_b=1,
        created_at=start + timedelta(seconds=30),
    )

    detail = await build_match_record_detail(db_session, match)

    assert detail.record_completeness == "complete"
    assert [e.elapsed_seconds for e in detail.events] == [10, 20, 30]
    assert [e.side for e in detail.events] == ["A", "B", "A"]
    assert [e.score_a for e in detail.events] == [1, 1, 2]
    assert [e.score_b for e in detail.events] == [0, 1, 1]


async def test_first_event_not_at_one_zero_yields_partial(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")
    match = await _make_match(
        db_session, group, score_a=6, score_b=3, team_a=[a.id], team_b=[b.id]
    )
    start = match.started_at
    assert start is not None
    # Recording started mid-match: first captured event already shows 5:3,
    # not 1:0/0:1 — proves points were on the board before this feature
    # began recording (research.md #3).
    await _add_event(
        db_session, match, side="A", delta=1, score_a=5, score_b=3,
        created_at=start + timedelta(seconds=100),
    )
    await _add_event(
        db_session, match, side="A", delta=1, score_a=6, score_b=3,
        created_at=start + timedelta(seconds=110),
    )

    detail = await build_match_record_detail(db_session, match)

    assert detail.record_completeness == "partial"
    assert len(detail.events) == 2
    # Even though the record is partial, the final score still matches the
    # match's real final score (only the beginning was missed).
    assert detail.score_a == 6
    assert detail.score_b == 3


async def test_deduction_event_is_included_not_hidden(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")
    match = await _make_match(
        db_session, group, score_a=1, score_b=0, team_a=[a.id], team_b=[b.id]
    )
    start = match.started_at
    assert start is not None
    await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )
    await _add_event(
        db_session, match, side="A", delta=-1, score_a=0, score_b=0,
        created_at=start + timedelta(seconds=8),
    )
    await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=12),
    )

    detail = await build_match_record_detail(db_session, match)

    assert [e.delta for e in detail.events] == [1, -1, 1]


async def test_large_number_of_events_not_truncated(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")
    match = await _make_match(
        db_session, group, score_a=21, score_b=19, team_a=[a.id], team_b=[b.id]
    )
    start = match.started_at
    assert start is not None
    await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=1),
    )
    # Simulate a long back-and-forth deuce battle: 45 more scoring actions.
    for i in range(2, 47):
        await _add_event(
            db_session, match, side="A" if i % 2 == 0 else "B", delta=1,
            score_a=i // 2, score_b=i - i // 2,
            created_at=start + timedelta(seconds=i),
        )

    detail = await build_match_record_detail(db_session, match)

    assert len(detail.events) == 46
    assert detail.record_completeness == "complete"


async def test_ordering_tie_break_by_id_when_created_at_equal(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")
    match = await _make_match(
        db_session, group, score_a=1, score_b=1, team_a=[a.id], team_b=[b.id]
    )
    start = match.started_at
    assert start is not None
    same_instant = start + timedelta(seconds=15)
    first = await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0, created_at=same_instant
    )
    second = await _add_event(
        db_session, match, side="B", delta=1, score_a=1, score_b=1, created_at=same_instant
    )
    expected_order = sorted([first.id, second.id])

    detail_1 = await build_match_record_detail(db_session, match)
    detail_2 = await build_match_record_detail(db_session, match)

    ids_in_order = [first.id, second.id] if expected_order[0] == first.id else [second.id, first.id]
    scores_in_order = [(1, 0), (1, 1)] if ids_in_order[0] == first.id else [(1, 1), (1, 0)]
    assert [(e.score_a, e.score_b) for e in detail_1.events] == scores_in_order
    # Repeated queries against the same data MUST return the same order.
    assert [(e.score_a, e.score_b) for e in detail_1.events] == [
        (e.score_a, e.score_b) for e in detail_2.events
    ]
