"""Unit tests for 030-score-serve-record's serve-state primitives:
`_compute_station()` (pure station formula, research.md Decision 3),
`_initialize_serve_state()` (random assignment on match start, Decision
4/5), and the side-out transition rule inside
`_advance_serve_state_and_snapshot()` (Decision 2)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import (
    _advance_serve_state_and_snapshot,
    _compute_station,
    _initialize_serve_state,
    create_match_with_participants,
)

# --- _compute_station() — pure function, no DB needed -----------------------


def test_compute_station_singles_even_score_right_slot() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    station = _compute_station("A", [a], [b], a, b, score_a=0, score_b=2)

    assert station.server_roster_entry_id == a
    assert station.server_team == "A"
    assert station.team_a_right_roster_entry_id == a
    assert station.team_a_left_roster_entry_id is None
    assert station.team_b_right_roster_entry_id == b
    assert station.team_b_left_roster_entry_id is None


def test_compute_station_singles_odd_score_left_slot() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    station = _compute_station("B", [a], [b], a, b, score_a=1, score_b=3)

    assert station.team_a_right_roster_entry_id is None
    assert station.team_a_left_roster_entry_id == a
    assert station.team_b_right_roster_entry_id is None
    assert station.team_b_left_roster_entry_id == b
    assert station.server_roster_entry_id == b
    assert station.server_team == "B"


def test_compute_station_doubles_even_score_reference_server_right() -> None:
    a1, a2, b1, b2 = (uuid.uuid4() for _ in range(4))
    station = _compute_station("A", [a1, a2], [b1, b2], a1, b1, score_a=4, score_b=1)

    assert station.team_a_right_roster_entry_id == a1
    assert station.team_a_left_roster_entry_id == a2
    # B's score is odd -> reference server (b1) is on the left, b2 on the right.
    assert station.team_b_left_roster_entry_id == b1
    assert station.team_b_right_roster_entry_id == b2
    assert station.server_roster_entry_id == a1


def test_compute_station_doubles_odd_score_reference_server_left() -> None:
    a1, a2, b1, b2 = (uuid.uuid4() for _ in range(4))
    station = _compute_station("B", [a1, a2], [b1, b2], a1, b1, score_a=3, score_b=6)

    assert station.team_a_left_roster_entry_id == a1
    assert station.team_a_right_roster_entry_id == a2
    assert station.team_b_right_roster_entry_id == b1
    assert station.team_b_left_roster_entry_id == b2
    assert station.server_roster_entry_id == b1
    assert station.server_team == "B"


# --- _initialize_serve_state() — random assignment (needs a real match) -----


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Serve State Test",
        "max_members": 8,
        "match_mode": "doubles",
        "scheduling_mechanism": "fair_rotation",
        "current_member_count": 1,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
        "target_score": 21,
        "deuce_threshold": 20,
        "cap_score": 30,
    }
    defaults.update(overrides)
    group = Group(**defaults)  # type: ignore[arg-type]
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_roster_entry(session: AsyncSession, group: Group) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_initialize_serve_state_singles_always_resolves_to_sole_participant(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, match_mode="singles")
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    match = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    assert match.serving_team in ("A", "B")
    assert match.team_a_reference_server_id == p1.id
    assert match.team_b_reference_server_id == p2.id


@pytest.mark.asyncio
async def test_initialize_serve_state_is_not_guaranteed_identical(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a1, a2, b1, b2 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )
    await db_session.commit()

    results = set()
    for _ in range(30):
        await _initialize_serve_state(db_session, match)
        results.add(
            (match.serving_team, match.team_a_reference_server_id, match.team_b_reference_server_id)
        )
    # Both the serving team and (doubles) each team's reference server are
    # randomly chosen (research.md Decision 4/5) — 30 draws landing on the
    # exact same combination every time would indicate `random.choice`
    # isn't actually being used.
    assert len(results) > 1


# --- Side-out transition rule (research.md Decision 2) ----------------------


@pytest.mark.asyncio
async def test_advance_serve_state_same_team_scoring_keeps_same_server(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a1, a2, b1, b2 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="in_progress",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )
    await db_session.commit()
    match.serving_team = "A"
    match.team_a_reference_server_id = a1.id
    match.team_b_reference_server_id = b1.id

    await _advance_serve_state_and_snapshot(db_session, match, "A", score_a=1, score_b=0)

    assert match.serving_team == "A"
    assert match.team_a_reference_server_id == a1.id
    assert match.team_b_reference_server_id == b1.id


@pytest.mark.asyncio
async def test_advance_serve_state_side_out_switches_server_and_swaps_teammate(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a1, a2, b1, b2 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    match = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="in_progress",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )
    await db_session.commit()
    match.serving_team = "A"
    match.team_a_reference_server_id = a1.id
    match.team_b_reference_server_id = b1.id

    await _advance_serve_state_and_snapshot(db_session, match, "B", score_a=0, score_b=1)

    assert match.serving_team == "B"
    # B regained serve — their reference server alternates to the teammate
    # who wasn't holding it (b1 -> b2).
    assert match.team_b_reference_server_id == b2.id
    # A wasn't involved in this side-out — their reference server is frozen.
    assert match.team_a_reference_server_id == a1.id
