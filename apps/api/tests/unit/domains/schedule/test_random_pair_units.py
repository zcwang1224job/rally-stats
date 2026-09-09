"""Unit test: random_pair_units() (017-fixed-partner-autofill research.md
#3) — coverage completeness, correct even pairing, and that repeated calls
aren't guaranteed to produce the same result (randomness actually exists)."""

from app.domains.schedule.algorithms import random_pair_units


def test_every_unit_appears_exactly_once() -> None:
    units = [f"P{i}" for i in range(10)]
    pairs = random_pair_units(units)

    assert len(pairs) == 5
    seen: list[str] = []
    for a, b in pairs:
        seen.append(a)
        seen.append(b)
    assert sorted(seen) == sorted(units)


def test_two_units_produce_one_pair() -> None:
    pairs = random_pair_units(["A", "B"])
    assert len(pairs) == 1
    assert set(pairs[0]) == {"A", "B"}


def test_empty_input_produces_no_pairs() -> None:
    assert random_pair_units([]) == []


def test_repeated_calls_are_not_guaranteed_identical() -> None:
    units = [f"P{i}" for i in range(20)]
    results = {
        tuple(sorted(frozenset(pair) for pair in random_pair_units(units))) for _ in range(50)
    }
    # With 20 units there are astronomically many possible pairings — 50
    # calls landing on the exact same one every time would indicate
    # random.shuffle isn't actually being used.
    assert len(results) > 1
