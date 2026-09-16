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
