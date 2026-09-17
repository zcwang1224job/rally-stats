"""Unit test: load_match_stat_inputs() — 034-clutch-points-player-dashboard
research.md Decision 7. The batch loader behind the cross-match dashboard:
many matches' point-level history in a fixed number of queries."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.service import load_match_stat_inputs
from app.domains.schedule.models import Match
from tests.unit.domains._match_history import Shot, make_entry, make_group, make_played_match

pytestmark = pytest.mark.asyncio


@contextmanager
def count_selects(session: AsyncSession) -> Iterator[list[str]]:
    statements: list[str] = []

    def _record(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _record)


async def _matches(session: AsyncSession, count: int) -> list[Match]:
    group = await make_group(session, match_mode="singles")
    a = await make_entry(session, group, "小明")
    b = await make_entry(session, group, "小美")
    sides = "AAB" + "A" * 19
    return [
        await make_played_match(session, group, team_a=[a.id], team_b=[b.id], sides=sides)
        for _ in range(count)
    ]


async def test_empty_input_needs_no_query(db_session: AsyncSession) -> None:
    with count_selects(db_session) as statements:
        assert await load_match_stat_inputs(db_session, []) == {}
    assert statements == []


async def test_each_match_gets_its_own_ordered_history(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles")
    a = await make_entry(db_session, group, "小明")
    b = await make_entry(db_session, group, "小美")
    first = await make_played_match(
        db_session, group, team_a=[a.id], team_b=[b.id], sides="AB" + "A" * 20,
        shots={0: Shot(scorer=a.id, loser=b.id, landing=(0.8, 0.2))},
    )
    second = await make_played_match(
        db_session, group, team_a=[a.id], team_b=[b.id], sides="B" * 21, serve_records=False
    )

    inputs = await load_match_stat_inputs(db_session, [first, second])

    assert set(inputs) == {first.id, second.id}
    one, two = inputs[first.id], inputs[second.id]
    assert one.completeness == "complete" and two.completeness == "complete"
    assert [(e.side, e.score_a, e.score_b) for e in one.raw_events[:3]] == [
        ("A", 1, 0),
        ("B", 1, 1),
        ("A", 2, 1),
    ]
    assert [e.at_seconds for e in one.raw_events] == sorted(e.at_seconds for e in one.raw_events)
    assert len(one.raw_events) == 22 and len(two.raw_events) == 21
    assert len(one.snapshots) == 22 and two.snapshots == {}
    first_event_id = one.raw_events[0].event_id
    assert one.placements[first_event_id].landing == (0.8, 0.2)
    assert two.placements == {}


async def test_match_without_events_still_gets_an_entry(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles")
    a = await make_entry(db_session, group, "小明")
    b = await make_entry(db_session, group, "小美")
    silent = await make_played_match(
        db_session, group, team_a=[a.id], team_b=[b.id], sides="A" * 21, log="none"
    )
    late = await make_played_match(
        db_session, group, team_a=[a.id], team_b=[b.id], sides="A" * 21, log="partial"
    )

    inputs = await load_match_stat_inputs(db_session, [silent, late])

    assert inputs[silent.id].completeness == "none" and inputs[silent.id].raw_events == []
    assert inputs[late.id].completeness == "partial"


async def test_query_count_does_not_grow_with_the_number_of_matches(
    db_session: AsyncSession,
) -> None:
    matches = await _matches(db_session, 12)

    with count_selects(db_session) as few:
        await load_match_stat_inputs(db_session, matches[:2])
    with count_selects(db_session) as many:
        await load_match_stat_inputs(db_session, matches)

    assert len(few) == len(many) == 3
