"""037-rest-ready-toggle US2 (FR-020, FR-031～FR-033, SC-006, SC-009): a
round whose only matches left are waiting on resting players, and the
reminder before a rest that would end the round on the spot."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.models import Court
from app.domains.group.models import Group, RoundHistory
from app.domains.roster.models import RosterEntry, RosterRestPeriod
from app.domains.schedule import rest as rest_module
from app.domains.schedule import service
from app.domains.schedule.models import Match
from app.domains.schedule.rest import set_rest_state
from app.domains.schedule.service import (
    _can_generate_any_match,
    check_round_complete_and_maybe_auto_advance,
    create_match_with_participants,
    round_is_stalled_by_rest,
)
from tests.unit.domains.schedule._rest_helpers import (
    finish_match,
    in_progress,
    make_courts,
    make_group,
    make_players,
    participants,
    set_resting,
)


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    events: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_publish(channel: str, event: str, payload: dict[str, Any]) -> None:
        events.append((channel, event, payload))

    monkeypatch.setattr(rest_module, "publish", fake_publish)
    return events


async def _queue(
    session: AsyncSession, group: Group, team_a: list[RosterEntry], team_b: list[RosterEntry]
) -> Match:
    match = await create_match_with_participants(
        session,
        group,
        court_id=None,
        round_number=group.current_round_number,
        status="queued",
        team_a=[p.id for p in team_a],
        team_b=[p.id for p in team_b],
    )
    await session.commit()
    return match


async def _on_court(
    session: AsyncSession, group: Group, court_id: object, team_a: list, team_b: list
) -> Match:
    match = await create_match_with_participants(
        session,
        group,
        court_id=court_id,  # type: ignore[arg-type]
        round_number=group.current_round_number,
        status="in_progress",
        team_a=[p.id for p in team_a],
        team_b=[p.id for p in team_b],
    )
    await session.commit()
    return match


async def _singles_waiting_on(
    session: AsyncSession, *, auto_next_round: bool = True, players: int = 4
) -> tuple[Group, list[RosterEntry], Court]:
    """Singles round-robin, one court, nothing on court, two queued matches
    both with P0 in them — once P0 rests, the round can't go on. Round 1 is
    recorded as generated, so the next one is numbered 2."""
    group = await make_group(session, match_mode="singles", auto_next_round=auto_next_round)
    [court] = await make_courts(session, group, 1)
    session.add(RoundHistory(group_id=group.id, round_number=1, started_at=datetime.now(UTC)))
    await session.commit()
    roster = await make_players(session, group, players)
    await _queue(session, group, [roster[0]], [roster[1]])
    await _queue(session, group, [roster[0]], [roster[2]])
    return group, roster, court


# --- round_is_stalled_by_rest() ---


@pytest.mark.asyncio
async def test_stalled_when_every_queued_match_waits_on_a_resting_player(
    db_session: AsyncSession,
) -> None:
    group, roster, court = await _singles_waiting_on(db_session)
    await set_resting(db_session, roster[0])

    assert await round_is_stalled_by_rest(db_session, group) is True


@pytest.mark.asyncio
async def test_not_stalled_while_a_match_is_on_court(db_session: AsyncSession) -> None:
    group, roster, court = await _singles_waiting_on(db_session, players=5)
    await _on_court(db_session, group, court.id, [roster[3]], [roster[4]])
    await set_resting(db_session, roster[0])

    assert await round_is_stalled_by_rest(db_session, group) is False


@pytest.mark.asyncio
async def test_not_stalled_with_nothing_queued(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles", auto_next_round=True)
    await make_courts(db_session, group, 1)
    roster = await make_players(db_session, group, 3)
    await set_resting(db_session, roster[0])

    assert await round_is_stalled_by_rest(db_session, group) is False


@pytest.mark.asyncio
async def test_not_stalled_while_some_queued_match_can_play(db_session: AsyncSession) -> None:
    group, roster, court = await _singles_waiting_on(db_session)
    await _queue(db_session, group, [roster[1]], [roster[2]])
    await set_resting(db_session, roster[0])

    assert await round_is_stalled_by_rest(db_session, group) is False


@pytest.mark.asyncio
async def test_not_stalled_while_a_substitute_can_be_found(db_session: AsyncSession) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    await make_courts(db_session, group, 1)
    a, b, c, d, _sub = await make_players(db_session, group, 5)
    await _queue(db_session, group, [a, b], [c, d])
    await set_resting(db_session, a)

    assert await round_is_stalled_by_rest(db_session, group) is False


@pytest.mark.asyncio
async def test_fixed_partner_stalls_even_with_players_to_spare(
    db_session: AsyncSession,
) -> None:
    """Fixed partners keep the match whoever else is free."""
    group = await make_group(
        db_session, scheduling_mechanism="fixed_partner", partner_source="auto"
    )
    await make_courts(db_session, group, 1)
    a, b, c, d, *_idle = await make_players(db_session, group, 8)
    await _queue(db_session, group, [a, b], [c, d])
    await set_resting(db_session, a)

    assert await round_is_stalled_by_rest(db_session, group) is True


# --- _can_generate_any_match() ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mechanism", "mode", "ready", "expected"),
    [
        ("fair_rotation", "singles", 2, True),
        ("fair_rotation", "singles", 1, False),
        ("fair_rotation", "doubles", 4, True),
        ("fair_rotation", "doubles", 3, False),
        ("individual_mixed", "doubles", 4, True),
        ("individual_mixed", "doubles", 3, False),
        ("fixed_partner", "doubles", 4, True),
        ("fixed_partner", "doubles", 3, False),
    ],
)
async def test_can_generate_any_match(
    db_session: AsyncSession, mechanism: str, mode: str, ready: int, expected: bool
) -> None:
    group = await make_group(
        db_session, match_mode=mode, scheduling_mechanism=mechanism, partner_source="auto"
    )
    roster = await make_players(db_session, group, ready + 2)
    for resting in roster[ready:]:
        await set_resting(db_session, resting)

    assert await _can_generate_any_match(db_session, group) is expected


# --- check_round_complete_and_maybe_auto_advance() ---


@pytest.mark.asyncio
async def test_a_stalled_round_auto_advances_after_the_last_match(
    db_session: AsyncSession,
) -> None:
    """FR-020: the last other match ends; only matches waiting on P0 are
    left; the round ends, they're abandoned, and the new round leaves P0
    out."""
    group, roster, court = await _singles_waiting_on(db_session)
    last = await _on_court(db_session, group, court.id, [roster[1]], [roster[2]])
    await set_resting(db_session, roster[0])
    held = [m for m in await _queued(db_session, group)]

    await finish_match(db_session, last)

    await db_session.refresh(group)
    assert group.current_round_number == 2
    for match in held:
        await db_session.refresh(match)
        assert match.status == "abandoned"
        assert match.winner_team is None
    new_round = await _round(db_session, group, 2)
    assert new_round
    for match in new_round:
        assert roster[0].id not in await participants(db_session, match.id)


@pytest.mark.asyncio
async def test_no_empty_round_when_the_next_one_could_not_be_played(
    db_session: AsyncSession,
) -> None:
    """Two players, one resting: a new round would only abandon the kept
    match and have nothing in it — so the round stays, and the match waits."""
    group = await make_group(db_session, match_mode="singles", auto_next_round=True)
    [court] = await make_courts(db_session, group, 1)
    a, b, c = await make_players(db_session, group, 3)
    kept = await _queue(db_session, group, [a], [b])
    last = await _on_court(db_session, group, court.id, [b], [c])
    await set_resting(db_session, a)
    await set_resting(db_session, c)

    await finish_match(db_session, last)

    await db_session.refresh(group)
    await db_session.refresh(kept)
    assert group.current_round_number == 1
    assert kept.status == "queued"


@pytest.mark.asyncio
async def test_without_auto_next_round_nothing_advances(db_session: AsyncSession) -> None:
    group, roster, court = await _singles_waiting_on(db_session, auto_next_round=False)
    await set_resting(db_session, roster[0])

    assert await check_round_complete_and_maybe_auto_advance(db_session, group) is False
    await db_session.refresh(group)
    assert group.current_round_number == 1


# --- REST_ENDS_ROUND (FR-031～FR-033) ---


@pytest.mark.asyncio
async def test_a_rest_that_would_end_the_round_asks_first_and_changes_nothing(
    db_session: AsyncSession, published: list
) -> None:
    group, roster, court = await _singles_waiting_on(db_session)
    before = await _snapshot(db_session, group)

    with pytest.raises(ApiError) as caught:
        await set_rest_state(db_session, group, roster[0], resting=True)

    assert caught.value.error_code == "REST_ENDS_ROUND"
    assert caught.value.status_code == 409
    assert caught.value.detail == {"matches_to_cancel": 2, "immediate": True}
    entry = await _fresh(db_session, roster[0])
    assert entry.resting_since is None
    await db_session.refresh(group)
    assert group.current_round_number == 1
    after = await _snapshot(db_session, group)
    assert after == before
    periods = await db_session.execute(select(RosterRestPeriod))
    assert periods.scalars().all() == []
    assert published == []


@pytest.mark.asyncio
async def test_a_confirmed_rest_ends_the_round(db_session: AsyncSession, published: list) -> None:
    group, roster, court = await _singles_waiting_on(db_session)
    held = await _queued(db_session, group)

    response = await set_rest_state(
        db_session, group, roster[0], resting=True, confirm_round_end=True
    )

    assert response.resting is True
    await db_session.refresh(group)
    assert group.current_round_number == 2
    for match in held:
        await db_session.refresh(match)
        assert match.status == "abandoned"


@pytest.mark.asyncio
async def test_a_confirmation_is_not_an_order(db_session: AsyncSession, published: list) -> None:
    """FR-033: confirmed, but meanwhile a match P0 isn't in was queued, so
    resting no longer ends the round — it's an ordinary rest."""
    group, roster, court = await _singles_waiting_on(db_session)
    await _queue(db_session, group, [roster[1]], [roster[2]])

    response = await set_rest_state(
        db_session, group, roster[0], resting=True, confirm_round_end=True
    )

    assert response.resting is True
    await db_session.refresh(group)
    assert group.current_round_number == 1


@pytest.mark.asyncio
async def test_held_matches_that_may_be_cancelled_later_ask_first_too(
    db_session: AsyncSession, published: list
) -> None:
    """User decision 2026-09-19: remind on pressing rest whenever the
    player's kept matches would be cancelled if the round ends before they
    are back — not only when it ends on the spot. A match is on court, so
    nothing ends now (`immediate: False`), and only their own matches
    count."""
    group, roster, court = await _singles_waiting_on(db_session, players=5)
    await _on_court(db_session, group, court.id, [roster[3]], [roster[4]])
    await _queue(db_session, group, [roster[1]], [roster[2]])

    with pytest.raises(ApiError) as caught:
        await set_rest_state(db_session, group, roster[0], resting=True)

    assert caught.value.error_code == "REST_ENDS_ROUND"
    assert caught.value.detail == {"matches_to_cancel": 2, "immediate": False}
    await db_session.refresh(roster[0])
    assert roster[0].resting_since is None
    await db_session.refresh(group)  # the refusal rolled the session back

    response = await set_rest_state(
        db_session, group, roster[0], resting=True, confirm_round_end=True
    )
    assert response.resting is True
    await db_session.refresh(group)
    assert group.current_round_number == 1  # nothing ends yet


@pytest.mark.asyncio
async def test_fixed_partners_are_reminded_too(db_session: AsyncSession, published: list) -> None:
    group = await make_group(
        db_session,
        scheduling_mechanism="fixed_partner",
        partner_source="auto",
        auto_next_round=True,
    )
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, e, f, g, h = await make_players(db_session, group, 8)
    await _on_court(db_session, group, court.id, [e, f], [g, h])
    await _queue(db_session, group, [a, b], [c, d])

    with pytest.raises(ApiError) as caught:
        await set_rest_state(db_session, group, a, resting=True)
    assert caught.value.detail == {"matches_to_cancel": 1, "immediate": False}


@pytest.mark.asyncio
async def test_no_reminder_where_a_substitute_would_play(
    db_session: AsyncSession, published: list
) -> None:
    """Individual-mixed and fair-rotation doubles substitute instead of
    cancelling, so there's nothing to warn about."""
    group = await make_group(
        db_session, scheduling_mechanism="individual_mixed", auto_next_round=True
    )
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, e, f, g, h = await make_players(db_session, group, 8)
    await _on_court(db_session, group, court.id, [e, f], [g, h])
    await _queue(db_session, group, [a, b], [c, d])

    response = await set_rest_state(db_session, group, a, resting=True)

    assert response.resting is True


@pytest.mark.asyncio
async def test_no_reminder_without_matches_to_lose(
    db_session: AsyncSession, published: list
) -> None:
    group, roster, court = await _singles_waiting_on(db_session, players=5)
    await _on_court(db_session, group, court.id, [roster[3]], [roster[4]])

    response = await set_rest_state(db_session, group, roster[3], resting=True)

    assert response.resting is True  # on court now, nothing queued


@pytest.mark.asyncio
async def test_no_reminder_without_auto_next_round(
    db_session: AsyncSession, published: list
) -> None:
    group, roster, court = await _singles_waiting_on(db_session, auto_next_round=False)

    response = await set_rest_state(db_session, group, roster[0], resting=True)

    assert response.resting is True
    await db_session.refresh(group)
    assert group.current_round_number == 1


@pytest.mark.asyncio
async def test_no_reminder_when_the_next_round_could_not_be_played(
    db_session: AsyncSession, published: list
) -> None:
    group, roster, court = await _singles_waiting_on(db_session, players=3)
    await set_resting(db_session, roster[1])

    response = await set_rest_state(db_session, group, roster[0], resting=True)

    assert response.resting is True
    await db_session.refresh(group)
    assert group.current_round_number == 1


@pytest.mark.asyncio
async def test_coming_back_never_asks(db_session: AsyncSession, published: list) -> None:
    group, roster, court = await _singles_waiting_on(db_session)
    await set_resting(db_session, roster[0])

    for confirm in (False, True):
        response = await set_rest_state(
            db_session, group, roster[0], resting=False, confirm_round_end=confirm
        )
        assert response.resting is False


@pytest.mark.asyncio
@pytest.mark.parametrize("would_advance", [True, False])
async def test_the_reminder_and_the_advance_share_one_rule(
    db_session: AsyncSession,
    published: list,
    monkeypatch: pytest.MonkeyPatch,
    would_advance: bool,
) -> None:
    # Auto Next Round off, so only the "ends on the spot" rule (the one
    # shared with the advance) can ask — not the "cancelled later" one.
    group, roster, court = await _singles_waiting_on(
        db_session, players=5, auto_next_round=False
    )
    await _on_court(db_session, group, court.id, [roster[3]], [roster[4]])

    async def fixed(*_args: object, **_kwargs: object) -> bool:
        return would_advance

    monkeypatch.setattr(service, "round_would_auto_advance", fixed)

    if would_advance:
        with pytest.raises(ApiError) as caught:
            await set_rest_state(db_session, group, roster[0], resting=True)
        assert caught.value.error_code == "REST_ENDS_ROUND"
    else:
        await set_rest_state(db_session, group, roster[0], resting=True)
        assert await check_round_complete_and_maybe_auto_advance(db_session, group) is False


@pytest.mark.asyncio
async def test_repeated_toggling_never_spins_the_round_counter(
    db_session: AsyncSession, published: list
) -> None:
    """SC-006: toggling doesn't burn through empty rounds."""
    group = await make_group(db_session, match_mode="singles", auto_next_round=True)
    await make_courts(db_session, group, 1)
    a, _b = await make_players(db_session, group, 2)

    for _ in range(5):
        await set_rest_state(db_session, group, a, resting=True, confirm_round_end=True)
        await set_rest_state(db_session, group, a, resting=False)

    await db_session.refresh(group)
    generated = await db_session.execute(
        select(Match.round_number).where(Match.group_id == group.id).distinct()
    )
    assert group.current_round_number <= max([1, *generated.scalars()])


@pytest.mark.asyncio
async def test_an_empty_round_advances_once_someone_is_back(
    db_session: AsyncSession, published: list
) -> None:
    """Round 1 was generated with nothing in it (one player ready); the
    other coming back makes a match possible, so it advances."""
    group = await make_group(db_session, match_mode="singles", auto_next_round=True)
    await make_courts(db_session, group, 1)
    db_session.add(RoundHistory(group_id=group.id, round_number=1, started_at=datetime.now(UTC)))
    await db_session.commit()
    a, b = await make_players(db_session, group, 2)
    await set_resting(db_session, a)

    await set_rest_state(db_session, group, a, resting=False)

    await db_session.refresh(group)
    assert group.current_round_number == 2
    [started] = await in_progress(db_session, group)
    assert await participants(db_session, started.id) == {a.id, b.id}


@pytest.mark.asyncio
async def test_a_group_nobody_has_started_never_starts_itself(
    db_session: AsyncSession, published: list
) -> None:
    """With Auto Next Round on but no round ever generated, resting and
    coming back must not start round 1 — only the admin does that."""
    group = await make_group(db_session, match_mode="singles", auto_next_round=True)
    await make_courts(db_session, group, 1)
    a, *_others = await make_players(db_session, group, 4)

    await set_rest_state(db_session, group, a, resting=True)
    await set_rest_state(db_session, group, a, resting=False)

    assert await in_progress(db_session, group) == []
    history = await db_session.execute(
        select(RoundHistory.round_number).where(RoundHistory.group_id == group.id)
    )
    assert history.scalars().all() == []


async def _queued(session: AsyncSession, group: Group) -> list[Match]:
    result = await session.execute(
        select(Match).where(Match.group_id == group.id, Match.status == "queued")
    )
    return list(result.scalars())


async def _round(session: AsyncSession, group: Group, number: int) -> list[Match]:
    result = await session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == number)
    )
    return list(result.scalars())


async def _snapshot(session: AsyncSession, group: Group) -> dict[object, tuple[str, set[object]]]:
    queued = await _queued(session, group)
    return {m.id: (m.status, await participants(session, m.id)) for m in queued}


async def _fresh(session: AsyncSession, entry: RosterEntry) -> RosterEntry:
    await session.refresh(entry)
    return entry
