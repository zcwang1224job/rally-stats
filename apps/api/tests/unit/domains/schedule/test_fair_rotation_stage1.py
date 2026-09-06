"""Unit test: stage 1 selection — wait_count DESC (NULL = infinite) with
joined_at ASC tiebreak; partial-court handling when players are insufficient
(spec FR-004/005/006)."""

import uuid
from datetime import UTC, datetime, timedelta

from app.domains.schedule.algorithms import stage1_select_players


def _id() -> uuid.UUID:
    return uuid.uuid4()


def test_higher_wait_count_selected_first() -> None:
    a, b, c = _id(), _id(), _id()
    now = datetime.now(UTC)
    roster = [(a, 1, now), (b, 5, now), (c, 3, now)]
    selected = stage1_select_players(roster, n=2)
    assert selected == [b, c]


def test_never_played_none_outranks_any_finite_wait_count() -> None:
    a, b = _id(), _id()
    now = datetime.now(UTC)
    roster = [(a, 100, now), (b, None, now)]
    selected = stage1_select_players(roster, n=1)
    assert selected == [b]


def test_tie_broken_by_earliest_joined_at() -> None:
    a, b, c = _id(), _id(), _id()
    t0 = datetime.now(UTC)
    roster = [
        (a, None, t0 + timedelta(minutes=2)),
        (b, None, t0),
        (c, None, t0 + timedelta(minutes=1)),
    ]
    selected = stage1_select_players(roster, n=2)
    assert selected == [b, c]


def test_selecting_more_than_available_returns_all() -> None:
    a, b = _id(), _id()
    now = datetime.now(UTC)
    roster = [(a, None, now), (b, None, now)]
    selected = stage1_select_players(roster, n=10)
    assert set(selected) == {a, b}
    assert len(selected) == 2


def test_selection_order_is_deterministic_and_reproducible() -> None:
    now = datetime.now(UTC)
    roster = [(_id(), i % 5, now) for i in range(20)]
    first = stage1_select_players(roster, n=8)
    second = stage1_select_players(roster, n=8)
    assert first == second
