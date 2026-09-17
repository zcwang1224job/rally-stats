"""Unit tests for attach_shot_placement() (032-score-then-record):
attaches landing/player detail to a `+1` that's already been applied via a
plain apply_score_delta() call — pressing "+" bumps the score immediately
(match pace never waits on this dialog), and this function is what the
picker's confirm() calls afterward, pinned to the exact ScoreEvent that "+"
created.

Covers: score_event lookup/ownership validation, detailed_scoring_enabled /
landing coordinate validation (FR-004/FR-010, Constitution X — server-side,
not just a UI filter), the scoring/losing player team constraints derived
from official badminton rules — the credited side is now GIVEN by the
ScoreEvent rather than inferred from a freely-picked player, so an in-bounds
landing must be consistent with it (on the OTHER side's half, since that
side failed to return it) — and singles-vs-doubles bounds
(032-out-of-bounds-by-match-mode)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import ScoreEvent, ShotPlacementRecord
from app.domains.schedule.schemas import Team
from app.domains.schedule.service import (
    apply_score_delta,
    attach_shot_placement,
    create_match_with_participants,
)

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Shot Placement Test",
        "max_members": 4,
        "match_mode": "singles",
        "scheduling_mechanism": "fair_rotation",
        "current_member_count": 1,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
        "target_score": 21,
        "deuce_threshold": 20,
        "cap_score": 30,
        "detailed_scoring_enabled": True,
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


async def _score_and_get_event_id(
    session: AsyncSession, court: Court, match_id: uuid.UUID, side: Team
) -> uuid.UUID:
    result = await apply_score_delta(session, court, match_id, side, 1)
    assert result.score_event_id is not None
    return uuid.UUID(result.score_event_id)


async def test_rejects_unknown_score_event(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match.id, uuid.uuid4(), p1.id, p2.id, 0.8, 0.5
        )

    assert excinfo.value.error_code == "SCORE_EVENT_NOT_FOUND"


async def test_rejects_score_event_from_a_different_match(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2, p3, p4 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    other_court = await _make_court(db_session, group, name="2號場")
    other_match = await create_match_with_participants(
        db_session, group, court_id=other_court.id, round_number=1, status="in_progress",
        team_a=[p3.id], team_b=[p4.id],
    )
    await db_session.commit()
    other_event_id = await _score_and_get_event_id(db_session, other_court, other_match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match.id, other_event_id, p1.id, p2.id, 0.8, 0.5
        )

    assert excinfo.value.error_code == "SCORE_EVENT_NOT_FOUND"


async def test_rejects_a_correction_score_event(db_session: AsyncSession) -> None:
    """A -1 correction also creates a ScoreEvent (with delta=-1) — that's
    not a point, so it can never carry a ShotPlacementRecord."""
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    await apply_score_delta(db_session, court, match.id, "A", 1)
    correction = await apply_score_delta(db_session, court, match.id, "A", -1)
    assert correction.score_event_id is not None

    correction_event_id = uuid.UUID(correction.score_event_id)
    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match.id, correction_event_id, p1.id, p2.id, 0.8, 0.5
        )

    assert excinfo.value.error_code == "SCORE_EVENT_NOT_A_POINT"


async def test_rejects_attaching_twice_to_the_same_score_event(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")
    await attach_shot_placement(db_session, court, match.id, event_id, p1.id, p2.id, 0.8, 0.5)

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(db_session, court, match.id, event_id, p1.id, p2.id, 0.9, 0.5)

    assert excinfo.value.error_code == "SHOT_PLACEMENT_ALREADY_RECORDED"


async def test_rejects_when_detailed_scoring_not_enabled(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, detailed_scoring_enabled=False)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(db_session, court, match.id, event_id, p1.id, p2.id, 0.8, 0.5)

    assert excinfo.value.error_code == "DETAILED_SCORING_NOT_ENABLED"


@pytest.mark.parametrize(
    "landing_x,landing_y", [(-0.31, 0.5), (1.31, 0.5), (0.5, -0.31), (0.5, 1.31)]
)
async def test_rejects_out_of_range_landing_coordinates(
    db_session: AsyncSession, landing_x: float, landing_y: float
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match.id, event_id, p1.id, p2.id, landing_x, landing_y
        )

    assert excinfo.value.error_code == "INVALID_LANDING_COORDINATES"
    records = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalars().all()
    assert records == []


async def test_rejects_scoring_roster_entry_not_in_match(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match.id, event_id, uuid.uuid4(), p2.id, 0.8, 0.5
        )

    assert excinfo.value.error_code == "PARTICIPANT_NOT_IN_MATCH"


async def test_rejects_losing_roster_entry_not_in_match(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match.id, event_id, p1.id, uuid.uuid4(), 0.8, 0.5
        )

    assert excinfo.value.error_code == "PARTICIPANT_NOT_IN_MATCH"


async def test_rejects_scoring_player_not_on_the_credited_side(db_session: AsyncSession) -> None:
    """Team A was credited (side='A') — a team B player can't be the
    "scoring player" for that point, even though they're a real participant."""
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(db_session, court, match.id, event_id, p2.id, p1.id, 0.8, 0.5)

    assert excinfo.value.error_code == "SCORING_PLAYER_NOT_ON_CREDITED_SIDE"


async def test_rejects_scoring_and_losing_player_on_same_team(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, match_mode="doubles")
    court = await _make_court(db_session, group)
    a1, a2, b1, b2 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(db_session, court, match.id, event_id, a1.id, a2.id, 0.8, 0.5)

    assert excinfo.value.error_code == "SCORING_AND_LOSING_PLAYER_SAME_TEAM"


async def test_rejects_in_bounds_landing_on_the_credited_sides_own_half(
    db_session: AsyncSession,
) -> None:
    """Team A was credited — an in-bounds landing must be on B's half
    (x>=0.5, since that's the side that failed to return it); a landing on
    A's own half (x<0.5) would mean A itself failed to return it, which
    contradicts A having scored."""
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(db_session, court, match.id, event_id, p1.id, p2.id, 0.2, 0.5)

    assert excinfo.value.error_code == "SCORING_PLAYER_WRONG_TEAM_FOR_LANDING"


# --- 032-serve-fault-landing: a serve fault favors the credited side too --


async def test_allows_short_serve_fault_landing_on_the_credited_sides_own_half(
    db_session: AsyncSession,
) -> None:
    """x=0.45 is between the net (0.5) and A's short service line (~0.3522)
    — the serve never crossed it, so A (the receiver) wins the point on a
    service fault without ever needing to return anything. This must not be
    flagged as A having contradictorily failed to return the shuttle."""
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    await attach_shot_placement(db_session, court, match.id, event_id, p1.id, p2.id, 0.45, 0.5)

    record = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalar_one()
    assert record.team == "A"


async def test_allows_long_serve_fault_landing_for_doubles_only(db_session: AsyncSession) -> None:
    """x=0.03 is past A's long service line (~0.0567, doubles only) but
    still short of A's own baseline — a doubles serve landing there never
    crossed into the legal box, so it's a service fault favoring A."""
    group = await _make_group(db_session, match_mode="doubles")
    court = await _make_court(db_session, group)
    a1, a2, b1, b2 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    await attach_shot_placement(db_session, court, match.id, event_id, a1.id, b1.id, 0.03, 0.5)

    record = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalar_one()
    assert record.team == "A"


async def test_rejects_deep_landing_for_singles_since_there_is_no_long_fault_zone(
    db_session: AsyncSession,
) -> None:
    """Singles serves are legal all the way back to the baseline, so x=0.03
    on A's own half is just a normal (deep) landing spot — for a singles
    match this is NOT a service-fault exemption, and still contradicts A
    having been credited the point."""
    group = await _make_group(db_session, match_mode="singles")
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(db_session, court, match.id, event_id, p1.id, p2.id, 0.03, 0.5)

    assert excinfo.value.error_code == "SCORING_PLAYER_WRONG_TEAM_FOR_LANDING"


async def test_allows_out_of_bounds_landing_regardless_of_credited_side(
    db_session: AsyncSession,
) -> None:
    """An out-of-bounds landing doesn't reveal which side hit it out, so it
    never conflicts with whichever side was credited."""
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    await attach_shot_placement(db_session, court, match.id, event_id, p1.id, p2.id, -0.1, 0.5)

    record = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalar_one()
    assert record.roster_entry_id == p1.id
    assert record.losing_roster_entry_id == p2.id


async def test_success_creates_a_record_linked_to_the_given_score_event(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, match_mode="doubles")
    court = await _make_court(db_session, group)
    a1, a2, b1, b2 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "B")

    # Team B credited -> in-bounds landing must be on A's half (x<0.5).
    await attach_shot_placement(db_session, court, match.id, event_id, b2.id, a1.id, 0.3, 0.6)

    event = (
        await db_session.execute(select(ScoreEvent).where(ScoreEvent.id == event_id))
    ).scalar_one()
    record = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalar_one()
    assert record.score_event_id == event.id
    assert record.roster_entry_id == b2.id
    assert record.losing_roster_entry_id == a1.id
    assert record.team == "B"
    assert record.landing_x == 0.3
    assert record.landing_y == 0.6
    assert record.group_id == group.id


# --- 032-out-of-bounds-by-match-mode: singles uses the narrower sideline ----


async def test_singles_landing_beyond_singles_sideline_is_out_of_bounds(
    db_session: AsyncSession,
) -> None:
    """y=0.03 is inside the doubles width [0, 1] but outside the singles
    sideline (~0.0754) — for a singles match this must be treated as
    out-of-bounds, so it never conflicts with the credited side."""
    group = await _make_group(db_session, match_mode="singles")
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    # x=0.2 (<0.5) would conflict with A being credited if this landing were
    # in bounds — it only works here because it's out (for singles).
    await attach_shot_placement(db_session, court, match.id, event_id, p1.id, p2.id, 0.2, 0.03)

    record = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalar_one()
    assert record.team == "A"


async def test_doubles_landing_at_same_narrow_y_is_in_bounds(db_session: AsyncSession) -> None:
    """The identical (x, y) that's out-of-bounds for singles above is still
    inside the doubles court, so the landing-side consistency check applies
    as normal."""
    group = await _make_group(db_session, match_mode="doubles")
    court = await _make_court(db_session, group)
    a1, a2, b1, b2 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(db_session, court, match.id, event_id, a1.id, b1.id, 0.2, 0.03)

    assert excinfo.value.error_code == "SCORING_PLAYER_WRONG_TEAM_FOR_LANDING"


# --- 032-optional-shot-placement-detail: every field is independently ------
# --- optional — confirming with only some of them picked must still work ---


async def test_allows_confirming_with_only_landing_no_players(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    await attach_shot_placement(db_session, court, match.id, event_id, None, None, 0.8, 0.5)

    record = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalar_one()
    assert record.roster_entry_id is None
    assert record.losing_roster_entry_id is None
    assert record.landing_x == 0.8
    assert record.landing_y == 0.5
    assert record.team == "A"  # always the credited side, even with no player chosen


async def test_allows_confirming_with_only_players_no_landing(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    await attach_shot_placement(db_session, court, match.id, event_id, p1.id, p2.id, None, None)

    record = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalar_one()
    assert record.roster_entry_id == p1.id
    assert record.losing_roster_entry_id == p2.id
    assert record.landing_x is None
    assert record.landing_y is None


async def test_allows_confirming_with_nothing_at_all(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    await attach_shot_placement(db_session, court, match.id, event_id, None, None, None, None)

    record = (
        await db_session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
        )
    ).scalar_one()
    assert record.roster_entry_id is None
    assert record.losing_roster_entry_id is None
    assert record.landing_x is None
    assert record.landing_y is None
    assert record.team == "A"


async def test_rejects_landing_x_without_landing_y(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(db_session, court, match.id, event_id, None, None, 0.5, None)

    assert excinfo.value.error_code == "INVALID_LANDING_COORDINATES"


async def test_landing_conflict_check_still_applies_without_any_player_chosen(
    db_session: AsyncSession,
) -> None:
    """The landing-vs-credited-side rule is derived from the ScoreEvent's
    own side, not from a specific chosen player — it still fires even when
    the scorer only picked a landing point."""
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()
    event_id = await _score_and_get_event_id(db_session, court, match.id, "A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(db_session, court, match.id, event_id, None, None, 0.2, 0.5)

    assert excinfo.value.error_code == "SCORING_PLAYER_WRONG_TEAM_FOR_LANDING"


# ---------------------------------------------------------------- 035 ending_type (T005)

_INSET = 0.46 / 6.1

# specs/035-point-ending-type/data-model.md「界內／界外的邊界測試向量」— copied
# verbatim. The picker's spec (shot-placement-picker.component.spec.ts) runs
# the SAME table: in/out is judged once on each side, and a request this
# function rejects silently loses the whole detail row (the callers have no
# error handler), so the two judgements must never disagree.
BOUNDS_VECTORS: list[tuple[str, float, float, bool]] = [
    ("doubles", 0.0, 0.5, True),
    ("doubles", 1.0, 0.5, True),
    ("doubles", 0.5, 0.0, True),
    ("doubles", 0.5, 1.0, True),
    ("doubles", -0.0001, 0.5, False),
    ("doubles", 1.0001, 0.5, False),
    ("doubles", 0.5, -0.0001, False),
    ("doubles", 0.5, 1.0001, False),
    ("singles", 0.5, _INSET, True),
    ("singles", 0.5, 1 - _INSET, True),
    ("singles", 0.5, _INSET - 0.0001, False),
    ("singles", 0.5, 1 - _INSET + 0.0001, False),
    ("singles", 0.5, 0.03, False),
]


async def _new_point(
    session: AsyncSession, *, mode: str = "singles", side: Team = "A", **group: object
) -> tuple[Court, uuid.UUID, uuid.UUID]:
    """A fresh in-progress match with one point already scored by `side`."""
    made = await _make_group(session, match_mode=mode, **group)
    court = await _make_court(session, made)
    per_team = 1 if mode == "singles" else 2
    players = [await _make_roster_entry(session, made) for _ in range(per_team * 2)]
    match = await create_match_with_participants(
        session, made, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p.id for p in players[:per_team]], team_b=[p.id for p in players[per_team:]],
    )
    await session.commit()
    return court, match.id, await _score_and_get_event_id(session, court, match.id, side)


async def _stored_ending(session: AsyncSession, event_id: uuid.UUID) -> str | None:
    record = (
        await session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.score_event_id == event_id)
        )
    ).scalar_one()
    return record.ending_type


@pytest.mark.parametrize("ending", ["winner", "out", "net", "serve_fault", "other_error"])
async def test_each_ending_type_is_stored_on_its_own(db_session: AsyncSession, ending: str) -> None:
    """FR-010: no landing, no players — the ending alone is a valid record."""
    court, match_id, event_id = await _new_point(db_session)

    await attach_shot_placement(
        db_session, court, match_id, event_id, None, None, None, None, ending_type=ending
    )

    assert await _stored_ending(db_session, event_id) == ending


async def test_ending_type_defaults_to_not_recorded(db_session: AsyncSession) -> None:
    court, match_id, event_id = await _new_point(db_session)

    await attach_shot_placement(db_session, court, match_id, event_id, None, None, 0.8, 0.5)

    assert await _stored_ending(db_session, event_id) is None


async def test_rejects_an_unknown_ending_type(db_session: AsyncSession) -> None:
    court, match_id, event_id = await _new_point(db_session)

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match_id, event_id, None, None, None, None, ending_type="smash"
        )

    assert excinfo.value.error_code == "INVALID_ENDING_TYPE"


@pytest.mark.parametrize(("mode", "x", "y", "in_bounds"), BOUNDS_VECTORS)
async def test_winner_needs_an_in_bounds_landing_and_out_an_out_of_bounds_one(
    db_session: AsyncSession, mode: str, x: float, y: float, in_bounds: bool
) -> None:
    # The credited side is whichever makes an in-bounds point land on the
    # LOSER's half, so the older landing-vs-credited-side check stays quiet.
    side: Team = "B" if x < 0.5 else "A"
    court, match_id, event_id = await _new_point(db_session, mode=mode, side=side)
    fits, contradicts = ("winner", "out") if in_bounds else ("out", "winner")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match_id, event_id, None, None, x, y, ending_type=contradicts
        )
    assert excinfo.value.error_code == "ENDING_TYPE_CONTRADICTS_LANDING"

    # Nothing was written by the rejected call, so the same point still takes one.
    await attach_shot_placement(
        db_session, court, match_id, event_id, None, None, x, y, ending_type=fits
    )
    assert await _stored_ending(db_session, event_id) == fits


@pytest.mark.parametrize("ending", ["net", "serve_fault", "other_error"])
@pytest.mark.parametrize(("x", "y"), [(0.8, 0.5), (1.2, 0.5)])
async def test_other_errors_are_never_tied_to_the_landing(
    db_session: AsyncSession, ending: str, x: float, y: float
) -> None:
    """A netted shuttle or a fault can come down anywhere."""
    court, match_id, event_id = await _new_point(db_session)

    await attach_shot_placement(
        db_session, court, match_id, event_id, None, None, x, y, ending_type=ending
    )

    assert await _stored_ending(db_session, event_id) == ending


@pytest.mark.parametrize("ending", ["winner", "out"])
async def test_without_a_landing_nothing_can_contradict(
    db_session: AsyncSession, ending: str
) -> None:
    court, match_id, event_id = await _new_point(db_session)

    await attach_shot_placement(
        db_session, court, match_id, event_id, None, None, None, None, ending_type=ending
    )

    assert await _stored_ending(db_session, event_id) == ending


async def test_simple_scoring_match_still_refuses_an_ending_type(db_session: AsyncSession) -> None:
    court, match_id, event_id = await _new_point(db_session, detailed_scoring_enabled=False)

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match_id, event_id, None, None, None, None, ending_type="winner"
        )

    assert excinfo.value.error_code == "DETAILED_SCORING_NOT_ENABLED"


async def test_older_landing_check_still_answers_first(db_session: AsyncSession) -> None:
    """In-bounds on the CREDITED side's own half (and not a serve-fault band)
    is the existing contradiction; it must not turn into the new error."""
    court, match_id, event_id = await _new_point(db_session, side="A")

    with pytest.raises(ApiError) as excinfo:
        await attach_shot_placement(
            db_session, court, match_id, event_id, None, None, 0.2, 0.5, ending_type="out"
        )

    assert excinfo.value.error_code == "SCORING_PLAYER_WRONG_TEAM_FOR_LANDING"
