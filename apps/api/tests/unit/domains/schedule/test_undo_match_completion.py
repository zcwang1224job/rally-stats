"""Unit tests for undo_match_completion() (032-cancel-score): reverts the
match this exact winning point just completed, back to in_progress with
that point removed — the picker's "Cancel Score" action's counterpart to
apply_score_delta(-1) specifically for the match-DECIDING point, since a
plain -1 can't target an already-`completed` match at all.

Only proceeds while the completion's cascade "stayed local" — the group's
round hasn't already advanced, and any replacement match pulled onto the
SAME court is still completely untouched — otherwise refuses rather than
risk discarding real gameplay data or leaving scheduling state
inconsistent (see the function's own docstring for the full rationale)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import ScoreEvent
from app.domains.schedule.service import (
    apply_score_delta,
    create_match_with_participants,
    undo_match_completion,
)

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Undo Match Completion Test",
        "max_members": 8,
        "match_mode": "singles",
        "scheduling_mechanism": "manual",
        "current_member_count": 1,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
        # A single point wins outright (match_wins(): score_x >= cap_score)
        # so tests don't need to loop apply_score_delta to reach a win.
        "target_score": 1,
        "deuce_threshold": 1,
        "cap_score": 1,
    }
    defaults.update(overrides)
    group = Group(**defaults)  # type: ignore[arg-type]
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_court(session: AsyncSession, group: Group, name: str = "1號場") -> Court:
    court = Court(group_id=group.id, name=name)
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def _make_roster_entry(session: AsyncSession, group: Group) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_reverts_score_status_and_creates_a_correction_score_event(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    win = await apply_score_delta(db_session, court, match.id, "A", 1)
    assert win.status == "completed"

    result = await undo_match_completion(db_session, court, match.id, "A")

    assert result.applied is True
    assert result.status == "in_progress"
    assert result.score_a == 0
    await db_session.refresh(match)
    assert match.status == "in_progress"
    assert match.winner_team is None
    assert match.ended_at is None

    events = (
        await db_session.execute(
            select(ScoreEvent)
            .where(ScoreEvent.match_id == match.id)
            .order_by(ScoreEvent.created_at)
        )
    ).scalars().all()
    assert len(events) == 2
    assert events[0].delta == 1
    assert events[1].delta == -1
    assert events[1].source == "cancel_score"


async def test_rejects_when_match_is_not_completed(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    with pytest.raises(ApiError) as excinfo:
        await undo_match_completion(db_session, court, match.id, "A")

    assert excinfo.value.error_code == "MATCH_NOT_COMPLETED"


async def test_rejects_when_side_did_not_win_this_match(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    await apply_score_delta(db_session, court, match.id, "A", 1)

    with pytest.raises(ApiError) as excinfo:
        await undo_match_completion(db_session, court, match.id, "B")

    assert excinfo.value.error_code == "SIDE_DID_NOT_WIN_THIS_MATCH"
    await db_session.refresh(match)
    assert match.status == "completed"


async def test_rejects_when_the_round_has_already_advanced(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    await apply_score_delta(db_session, court, match.id, "A", 1)

    # Something else (e.g. the round completing group-wide) moved the group
    # on to a new round since this match finished.
    group.current_round_number = 2
    await db_session.commit()

    with pytest.raises(ApiError) as excinfo:
        await undo_match_completion(db_session, court, match.id, "A")

    assert excinfo.value.error_code == "ROUND_ALREADY_ADVANCED"
    await db_session.refresh(match)
    assert match.status == "completed"


async def test_unpulls_an_untouched_replacement_match_pulled_onto_the_same_court(
    db_session: AsyncSession,
) -> None:
    """fair_rotation (non-manual): winning the active match lets
    advance_court_after_match_ends() pull the queued match onto the same
    court for real — undo_match_completion() must put that pulled match
    back to queued (untouched) so the original can retake the court."""
    group = await _make_group(db_session, scheduling_mechanism="fair_rotation")
    court = await _make_court(db_session, group)
    p1, p2, p3, p4 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p3.id], team_b=[p4.id],
    )
    await db_session.commit()

    win = await apply_score_delta(db_session, court, match.id, "A", 1)
    assert win.status == "completed"
    await db_session.refresh(queued)
    assert queued.status == "in_progress"
    assert queued.court_id == court.id

    result = await undo_match_completion(db_session, court, match.id, "A")

    assert result.applied is True
    assert result.status == "in_progress"
    await db_session.refresh(match)
    assert match.court_id == court.id
    assert match.status == "in_progress"

    await db_session.refresh(queued)
    assert queued.status == "queued"
    assert queued.court_id is None
    assert queued.started_at is None
    assert queued.serving_team is None


async def test_rejects_when_the_replacement_match_has_already_been_scored(
    db_session: AsyncSession,
) -> None:
    # cap_score=2 here (unlike the other tests' cap_score=1): the replacement
    # match must survive being scored once WITHOUT itself completing, so it's
    # still `in_progress` (and thus "touched but findable") when
    # undo_match_completion looks for it — a single point at cap_score=1
    # would finish it outright and make it invisible to that lookup.
    group = await _make_group(
        db_session, scheduling_mechanism="fair_rotation", target_score=2, cap_score=2
    )
    court = await _make_court(db_session, group)
    p1, p2, p3, p4 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p3.id], team_b=[p4.id],
    )
    await db_session.commit()

    await apply_score_delta(db_session, court, match.id, "A", 1)
    await apply_score_delta(db_session, court, match.id, "A", 1)
    await db_session.refresh(queued)
    # Someone has already started scoring the replacement match for real —
    # only one point, so it stays in_progress rather than completing too.
    await apply_score_delta(db_session, court, queued.id, "A", 1)

    with pytest.raises(ApiError) as excinfo:
        await undo_match_completion(db_session, court, match.id, "A")

    assert excinfo.value.error_code == "NEXT_MATCH_ALREADY_STARTED"
    await db_session.refresh(match)
    assert match.status == "completed"
