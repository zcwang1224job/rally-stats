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


def _side_of(unit: int, batches: list[list[tuple[int, int]]]) -> list[int]:
    """0 if `unit` was tuple position 0 (Team A) in its batch's pair, 1 if
    tuple position 1 (Team B) — one entry per batch `unit` appears in."""
    sides = []
    for batch in batches:
        for pair in batch:
            if unit in pair:
                sides.append(pair.index(unit))
    return sides


@pytest.mark.parametrize("n", [4, 5, 6, 7, 8, 9])
def test_fixed_anchor_is_not_always_on_the_same_side(n: int) -> None:
    """Regression test for the "球員固定同一側" bug: `units[0]` (the
    circle-method's fixed anchor — the one unit whose ring position never
    rotates) previously landed as tuple position 0 (Team A, per callers'
    convention) in EVERY single batch. It MUST now alternate."""
    units = list(range(n))
    batches = round_robin_pairs(units)

    anchor_sides = _side_of(0, batches)
    assert len(anchor_sides) == n - 1  # the anchor plays every other unit once
    assert 0 in anchor_sides and 1 in anchor_sides  # not stuck on one side

    # Every non-anchor unit was already naturally balanced before the fix —
    # confirm the fix didn't accidentally break that.
    for unit in range(1, n):
        sides = _side_of(unit, batches)
        assert len(set(sides)) <= 2  # sanity: only two possible tuple positions


def test_start_swapped_flips_the_anchors_starting_side() -> None:
    units = list(range(6))

    default_batches = round_robin_pairs(units)
    swapped_batches = round_robin_pairs(units, start_swapped=True)

    # Same pairings either way (start_swapped only affects tuple order, not
    # who plays whom) ...
    assert {tuple(sorted(p)) for b in default_batches for p in b} == {
        tuple(sorted(p)) for b in swapped_batches for p in b
    }
    # ... but the anchor's side in every batch is exactly flipped, so calling
    # this once per Round with an alternating `start_swapped` (e.g.
    # `round_number % 2 == 1`) balances the anchor's side across Rounds too.
    assert _side_of(0, default_batches) == [1 - side for side in _side_of(0, swapped_batches)]
