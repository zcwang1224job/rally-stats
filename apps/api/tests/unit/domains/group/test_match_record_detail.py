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
from app.domains.schedule.models import (
    Match,
    MatchParticipant,
    ScoreEvent,
    ScoreServeRecord,
    ShotPlacementRecord,
)

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


async def _add_shot_placement(
    session: AsyncSession,
    event: ScoreEvent,
    *,
    team: str,
    roster_entry_id: uuid.UUID | None = None,
    losing_roster_entry_id: uuid.UUID | None = None,
    landing_x: float | None = None,
    landing_y: float | None = None,
) -> ShotPlacementRecord:
    record = ShotPlacementRecord(
        score_event_id=event.id,
        match_id=event.match_id,
        group_id=event.group_id,
        roster_entry_id=roster_entry_id,
        losing_roster_entry_id=losing_roster_entry_id,
        team=team,
        landing_x=landing_x,
        landing_y=landing_y,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


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


# 032-match-record-scoring-stats


async def test_full_shot_placement_record_is_attached_to_its_event(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    match = await _make_match(db_session, group, score_a=1, score_b=0, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    event = await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )
    await _add_shot_placement(
        db_session, event, team="A",
        roster_entry_id=a.id, losing_roster_entry_id=b.id, landing_x=0.62, landing_y=0.18,
    )

    detail = await build_match_record_detail(db_session, match)

    [summary] = detail.events
    assert summary.detail is not None
    assert summary.detail.scoring_roster_entry_id == str(a.id)
    assert summary.detail.scoring_nickname == "小明"
    assert summary.detail.losing_roster_entry_id == str(b.id)
    assert summary.detail.losing_nickname == "小美"
    assert summary.detail.landing_x == 0.62
    assert summary.detail.landing_y == 0.18


async def test_event_with_no_shot_placement_record_has_no_detail(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    match = await _make_match(db_session, group, score_a=1, score_b=0, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )

    detail = await build_match_record_detail(db_session, match)

    [summary] = detail.events
    assert summary.detail is None


async def test_shot_placement_record_with_all_fields_null_has_no_detail(
    db_session: AsyncSession,
) -> None:
    """research.md Decision 2: confirming the picker with nothing picked at
    all still writes a ShotPlacementRecord row (every field NULL) — it MUST
    render identically to "no row at all"."""
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    match = await _make_match(db_session, group, score_a=1, score_b=0, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    event = await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )
    await _add_shot_placement(db_session, event, team="A")

    detail = await build_match_record_detail(db_session, match)

    [summary] = detail.events
    assert summary.detail is None


async def test_deduction_event_never_has_detail(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    match = await _make_match(db_session, group, score_a=0, score_b=0, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    scoring_event = await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )
    await _add_shot_placement(db_session, scoring_event, team="A", roster_entry_id=a.id)
    await _add_event(
        db_session, match, side="A", delta=-1, score_a=0, score_b=0,
        created_at=start + timedelta(seconds=8),
    )

    detail = await build_match_record_detail(db_session, match)

    scoring_summary, deduction_summary = detail.events
    assert scoring_summary.detail is not None
    assert deduction_summary.detail is None


async def test_partial_shot_placement_record_only_populates_recorded_fields(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    match = await _make_match(db_session, group, score_a=2, score_b=0, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    only_scoring_player = await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )
    await _add_shot_placement(db_session, only_scoring_player, team="A", roster_entry_id=a.id)
    only_landing = await _add_event(
        db_session, match, side="A", delta=1, score_a=2, score_b=0,
        created_at=start + timedelta(seconds=10),
    )
    await _add_shot_placement(db_session, only_landing, team="A", landing_x=0.3, landing_y=0.4)

    detail = await build_match_record_detail(db_session, match)

    first, second = detail.events
    assert first.detail is not None
    assert first.detail.scoring_roster_entry_id == str(a.id)
    assert first.detail.losing_roster_entry_id is None
    assert first.detail.landing_x is None
    assert second.detail is not None
    assert second.detail.scoring_roster_entry_id is None
    assert second.detail.landing_x == 0.3
    assert second.detail.landing_y == 0.4


async def test_player_stats_aggregates_independently_per_field_and_includes_zero_players(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a1 = await _make_entry(db_session, group, "A1")
    a2 = await _make_entry(db_session, group, "A2")
    b1 = await _make_entry(db_session, group, "B1")
    b2 = await _make_entry(db_session, group, "B2")
    match = await _make_match(
        db_session, group, score_a=3, score_b=1, team_a=[a1.id, a2.id], team_b=[b1.id, b2.id]
    )
    start = match.started_at
    assert start is not None

    # a1 scores twice (once against b1, once against b2); a2 only scores
    # (no losing player recorded); b1 scores once (only losing player, a2,
    # recorded — a1's scoring side left blank); a1's own losing partner a2
    # never gets recorded as a losing player at all.
    e1 = await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )
    await _add_shot_placement(
        db_session, e1, team="A", roster_entry_id=a1.id, losing_roster_entry_id=b1.id
    )
    e2 = await _add_event(
        db_session, match, side="A", delta=1, score_a=2, score_b=0,
        created_at=start + timedelta(seconds=10),
    )
    await _add_shot_placement(
        db_session, e2, team="A", roster_entry_id=a1.id, losing_roster_entry_id=b2.id
    )
    e3 = await _add_event(
        db_session, match, side="A", delta=1, score_a=3, score_b=0,
        created_at=start + timedelta(seconds=15),
    )
    await _add_shot_placement(db_session, e3, team="A", roster_entry_id=a2.id)
    e4 = await _add_event(
        db_session, match, side="B", delta=1, score_a=3, score_b=1,
        created_at=start + timedelta(seconds=20),
    )
    await _add_shot_placement(db_session, e4, team="B", losing_roster_entry_id=a2.id)

    detail = await build_match_record_detail(db_session, match)

    stats_by_id = {stat.roster_entry_id: stat for stat in detail.player_stats}
    assert len(detail.player_stats) == 4  # every participant listed, none omitted
    assert stats_by_id[str(a1.id)].scored_count == 2
    assert stats_by_id[str(a1.id)].fault_count == 0
    assert stats_by_id[str(a2.id)].scored_count == 1
    assert stats_by_id[str(a2.id)].fault_count == 1
    assert stats_by_id[str(b1.id)].scored_count == 0
    assert stats_by_id[str(b1.id)].fault_count == 1
    assert stats_by_id[str(b2.id)].scored_count == 0
    assert stats_by_id[str(b2.id)].fault_count == 1


async def test_player_stats_is_empty_when_no_shot_placement_data_recorded(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    match = await _make_match(db_session, group, score_a=1, score_b=0, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    # Non-detailed-mode point: no ShotPlacementRecord at all.
    await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )

    detail = await build_match_record_detail(db_session, match)

    assert detail.player_stats == []


async def test_player_stats_is_empty_when_shot_placement_rows_are_all_null(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    match = await _make_match(db_session, group, score_a=1, score_b=0, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    event = await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )
    # Confirmed with nothing picked — a real row exists but carries no
    # player information at all.
    await _add_shot_placement(db_session, event, team="A")

    detail = await build_match_record_detail(db_session, match)

    assert detail.player_stats == []


# ---------------------------------------------------------------------------
# 033-match-record-derived-stats: the query/conversion half only — every
# rule itself is covered without a database in test_match_stats.py.


async def _add_serve_record(
    session: AsyncSession,
    event: ScoreEvent,
    *,
    server_team: str,
    server: uuid.UUID,
    a_right: uuid.UUID | None,
    a_left: uuid.UUID | None,
    b_right: uuid.UUID | None,
    b_left: uuid.UUID | None,
) -> None:
    session.add(
        ScoreServeRecord(
            score_event_id=event.id,
            match_id=event.match_id,
            group_id=event.group_id,
            server_roster_entry_id=server,
            server_team=server_team,
            team_a_right_roster_entry_id=a_right,
            team_a_left_roster_entry_id=a_left,
            team_b_right_roster_entry_id=b_right,
            team_b_left_roster_entry_id=b_left,
        )
    )
    await session.commit()


async def _doubles_two_one(
    session: AsyncSession, *, with_serve_records: bool
) -> tuple[Match, list[RosterEntry], list[ScoreEvent]]:
    """A A B -> 2:1, at 10s/30s/45s. Serve records are what the write path
    leaves for "A serves first, reference servers a1/b1": each row is the
    state AFTER its own point."""
    group = await _make_group(session)
    a1, a2, b1, b2 = [await _make_entry(session, group, name) for name in ("甲", "乙", "丙", "丁")]
    match = await _make_match(
        session, group, score_a=2, score_b=1, team_a=[a1.id, a2.id], team_b=[b1.id, b2.id]
    )
    start = match.started_at
    assert start is not None
    events = [
        await _add_event(
            session, match, side=side, delta=1, score_a=score_a, score_b=score_b,
            created_at=start + timedelta(seconds=at),
        )
        for side, score_a, score_b, at in (("A", 1, 0, 10), ("A", 2, 0, 30), ("B", 2, 1, 45))
    ]
    if with_serve_records:
        await _add_serve_record(
            session, events[0], server_team="A", server=a1.id,
            a_right=a2.id, a_left=a1.id, b_right=b1.id, b_left=b2.id,
        )
        await _add_serve_record(
            session, events[1], server_team="A", server=a1.id,
            a_right=a1.id, a_left=a2.id, b_right=b1.id, b_left=b2.id,
        )
        await _add_serve_record(
            session, events[2], server_team="B", server=b2.id,
            a_right=a1.id, a_left=a2.id, b_right=b1.id, b_left=b2.id,
        )
    return match, [a1, a2, b1, b2], events


async def test_serve_stats_read_the_previous_points_serve_record(
    db_session: AsyncSession,
) -> None:
    match, [a1, a2, b1, b2], _ = await _doubles_two_one(db_session, with_serve_records=True)

    detail = await build_match_record_detail(db_session, match)

    serve = detail.serve_stats
    assert serve is not None
    assert serve.excluded_points == 1
    team_a, team_b = serve.teams
    assert (team_a.team, team_a.serve_points_won, team_a.serve_points_total) == ("A", 1, 2)
    assert (team_b.team, team_b.receive_points_won, team_b.receive_points_total) == ("B", 1, 2)
    assert team_b.serve_points_total == 0

    assert [p.roster_entry_id for p in serve.players] == [str(e.id) for e in (a1, a2, b1, b2)]
    by_name = {p.nickname: p for p in serve.players}
    assert (by_name["甲"].serve_points_won, by_name["甲"].serve_points_total) == (1, 2)
    # a1 served from the left at 1:0 (to b2), then from the right at 2:0 (to b1).
    assert (by_name["丁"].receive_points_won, by_name["丁"].receive_points_total) == (0, 1)
    assert (by_name["丙"].receive_points_won, by_name["丙"].receive_points_total) == (1, 1)
    assert by_name["乙"].serve_points_total == 0


async def test_momentum_and_tempo_are_derived_from_the_event_log(
    db_session: AsyncSession,
) -> None:
    match, _, _ = await _doubles_two_one(db_session, with_serve_records=False)

    detail = await build_match_record_detail(db_session, match)

    assert detail.momentum_stats is not None
    run_a, run_b = detail.momentum_stats.longest_runs
    assert (run_a.length, run_a.end_score_a, run_a.end_score_b) == (2, 2, 0)
    assert run_b.length == 1
    assert detail.momentum_stats.lead_changes == []

    assert detail.tempo_stats is not None
    assert detail.tempo_stats.counted_points == 3
    assert detail.tempo_stats.average_seconds == 15.0
    longest = detail.tempo_stats.longest
    assert (longest.seconds, longest.score_a, longest.score_b) == (20.0, 2, 0)


async def test_match_without_serve_records_has_no_serve_stats_but_keeps_the_rest(
    db_session: AsyncSession,
) -> None:
    match, _, _ = await _doubles_two_one(db_session, with_serve_records=False)

    detail = await build_match_record_detail(db_session, match)

    assert detail.serve_stats is None
    assert detail.momentum_stats is not None
    assert detail.tempo_stats is not None
    assert detail.landing_distribution == []


async def test_partial_record_has_no_derived_stats_at_all(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    match = await _make_match(db_session, group, score_a=6, score_b=3, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    await _add_event(
        db_session, match, side="A", delta=1, score_a=6, score_b=3,
        created_at=start + timedelta(seconds=300),
    )

    detail = await build_match_record_detail(db_session, match)

    assert detail.record_completeness == "partial"
    assert detail.serve_stats is None
    assert detail.momentum_stats is None
    assert detail.tempo_stats is None
    assert detail.landing_distribution == []


async def test_history_that_contradicts_the_final_score_has_no_derived_stats(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    # Complete log of a single point, but the match says 21:18.
    match = await _make_match(db_session, group, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    await _add_event(
        db_session, match, side="A", delta=1, score_a=1, score_b=0,
        created_at=start + timedelta(seconds=5),
    )

    detail = await build_match_record_detail(db_session, match)

    assert detail.record_completeness == "complete"
    assert detail.momentum_stats is None
    assert detail.tempo_stats is None


async def test_voided_point_is_left_out_of_momentum_and_tempo(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "小明")
    b = await _make_entry(db_session, group, "小美")
    match = await _make_match(db_session, group, score_a=1, score_b=1, team_a=[a.id], team_b=[b.id])
    start = match.started_at
    assert start is not None
    for side, delta, score_a, score_b, at in (
        ("A", 1, 1, 0, 10),
        ("A", 1, 2, 0, 20),  # a false 2:0 lead, undone next
        ("A", -1, 1, 0, 25),
        ("B", 1, 1, 1, 200),
    ):
        await _add_event(
            db_session, match, side=side, delta=delta, score_a=score_a, score_b=score_b,
            created_at=start + timedelta(seconds=at),
        )

    detail = await build_match_record_detail(db_session, match)

    assert detail.momentum_stats is not None
    assert detail.momentum_stats.max_leads[0].margin == 1
    assert detail.tempo_stats is not None
    # Only the first point: B's gap spans the correction.
    assert (detail.tempo_stats.counted_points, detail.tempo_stats.longest.seconds) == (1, 10.0)


async def test_landing_distribution_totals_match_player_stats(db_session: AsyncSession) -> None:
    match, [a1, _a2, b1, _b2], events = await _doubles_two_one(db_session, with_serve_records=False)
    await _add_shot_placement(
        db_session, events[0], team="A",
        roster_entry_id=a1.id, losing_roster_entry_id=b1.id, landing_x=0.82, landing_y=0.2,
    )
    await _add_shot_placement(db_session, events[1], team="A", roster_entry_id=a1.id)
    await _add_shot_placement(
        db_session, events[2], team="B",
        roster_entry_id=b1.id, losing_roster_entry_id=a1.id, landing_x=-0.05, landing_y=0.5,
    )

    detail = await build_match_record_detail(db_session, match)

    assert [p.nickname for p in detail.landing_distribution] == ["甲", "乙", "丙", "丁"]
    first = detail.landing_distribution[0]
    assert [(p.x, p.y) for p in first.scored] == [(0.82, 0.2)]
    assert first.scored_total == 2  # the second point named a1 but plotted nothing
    assert [(p.x, p.y) for p in first.lost] == [(-0.05, 0.5)]  # out of bounds, kept verbatim
    stats = {s.roster_entry_id: s for s in detail.player_stats}
    for player in detail.landing_distribution:
        assert player.scored_total == stats[player.roster_entry_id].scored_count
        assert player.lost_total == stats[player.roster_entry_id].fault_count
