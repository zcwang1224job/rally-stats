"""Unit test: stage 2 greedy pairing minimizes pair_history, independent of
who made the stage-1 cut (spec FR-008)."""

import uuid

from app.domains.schedule.algorithms import greedy_pair_by_cost, stage2_pair_players


def _id() -> uuid.UUID:
    return uuid.uuid4()


def test_pairs_lowest_cost_partners_first() -> None:
    a, b, c, d = _id(), _id(), _id(), _id()
    # a-b have played together a lot; a-c have never played.
    counts = {
        frozenset((a, b)): 5,
        frozenset((a, c)): 0,
        frozenset((a, d)): 2,
        frozenset((b, c)): 1,
        frozenset((b, d)): 3,
        frozenset((c, d)): 4,
    }

    def pair_count(x: uuid.UUID, y: uuid.UUID) -> int:
        return counts[frozenset((x, y))]

    pairs = stage2_pair_players([a, b, c, d], pair_count)
    assert (a, c) in pairs or (c, a) in pairs
    assert len(pairs) == 2


def test_all_players_are_paired_exactly_once() -> None:
    ids = [_id() for _ in range(6)]

    def pair_count(_x: uuid.UUID, _y: uuid.UUID) -> int:
        return 0

    pairs = stage2_pair_players(ids, pair_count)
    assert len(pairs) == 3
    flattened = {p for pair in pairs for p in pair}
    assert flattened == set(ids)


def test_greedy_pair_by_cost_is_generic_over_unit_type() -> None:
    # Same primitive reused for team-matchup pairing (US4/US5) — here just
    # exercised with plain ints to confirm it isn't UUID-specific.
    pairs = greedy_pair_by_cost([1, 2, 3, 4], cost=lambda x, y: abs(x - y))
    assert len(pairs) == 2
    assert (1, 2) in pairs
