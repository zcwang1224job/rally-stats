"""Unit test: round_robin_pairs() (circle method) per
011-round-robin-scheduling research.md #1 — every unique pair appears
exactly once, batches are internally conflict-free, odd counts are handled
via a silently-dropped bye."""

import math

import pytest

from app.domains.schedule.algorithms import round_robin_pairs


def _all_pairs_flat(batches: list[list[tuple[int, int]]]) -> list[tuple[int, int]]:
    return [pair for batch in batches for pair in batch]


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7, 8, 9])
def test_covers_every_pair_exactly_once(n: int) -> None:
    units = list(range(n))
    batches = round_robin_pairs(units)

    pairs = _all_pairs_flat(batches)
    normalized = {tuple(sorted(p)) for p in pairs}

    assert len(pairs) == math.comb(n, 2)
    assert len(normalized) == math.comb(n, 2)
    for a, b in normalized:
        assert a != b


@pytest.mark.parametrize("n", [4, 5, 6, 7, 8])
def test_batches_are_internally_conflict_free(n: int) -> None:
    units = list(range(n))
    batches = round_robin_pairs(units)

    for batch in batches:
        seen: set[int] = set()
        for a, b in batch:
            assert a not in seen
            assert b not in seen
            seen.add(a)
            seen.add(b)


def test_single_unit_produces_no_pairs() -> None:
    assert round_robin_pairs([1]) == []


def test_empty_input_produces_no_pairs() -> None:
    assert round_robin_pairs([]) == []
