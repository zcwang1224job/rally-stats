"""037-rest-ready-toggle research.md Decisions 3 and 4, as pure functions:
matches that went on court while a player was resting don't count as
matches they sat out, and a returning player is credited with played
matches so "fewest played" doesn't keep them first in line all evening."""

import uuid
from datetime import UTC, datetime, timedelta

from app.domains.schedule.algorithms import (
    PlayerHistory,
    player_histories,
    returning_played_credit,
)

T0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def at(minute: int) -> datetime:
    return T0 + timedelta(minutes=minute)


P, Q, R = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

# P plays match 1, then five matches go on court without P.
AFTER_P = [
    (at(0), at(10), [P]),
    (at(10), at(20), [Q]),
    (at(20), at(30), [Q]),
    (at(30), at(40), [Q]),
    (at(40), at(50), [Q]),
    (at(50), None, [Q]),
]


def test_no_rest_periods_changes_nothing() -> None:
    """Same input as test_schedule_fairness.py's two-court case."""
    matches = [
        (at(0), at(10), [P]),
        (at(5), at(15), [Q]),
        (at(10), at(20), [P]),
        (at(20), at(30), [P]),
        (at(31), at(40), [Q]),
        (at(40), None, [R]),
    ]
    plain = player_histories(matches)
    assert plain[P] == PlayerHistory(played=3, rest=2, run=3)
    assert player_histories(matches, {}) == plain
    assert player_histories(matches, None) == plain


def test_matches_during_a_rest_period_are_not_rest() -> None:
    # Matches starting at 20, 30 and 40 fall inside [15, 45).
    histories = player_histories(AFTER_P, {P: [(at(15), at(45))]})
    assert histories[P].rest == 2  # the ones at 10 and 50


def test_matches_before_and_after_the_period_still_count() -> None:
    histories = player_histories(AFTER_P, {P: [(at(25), at(35))]})
    assert histories[P].rest == 4  # only the one at 30 is left out


def test_several_periods_are_all_left_out() -> None:
    histories = player_histories(AFTER_P, {P: [(at(5), at(15)), (at(35), at(45))]})
    assert histories[P].rest == 3  # 10 and 40 left out


def test_an_ongoing_period_leaves_out_everything_since() -> None:
    histories = player_histories(AFTER_P, {P: [(at(25), None)]})
    assert histories[P].rest == 2  # 10 and 20; 30, 40 and 50 left out


def test_a_period_started_while_on_court_only_counts_after_coming_off() -> None:
    """Pressed "rest" during match 1: rest is counted from its end anyway,
    so the overlap before that must not be subtracted a second time."""
    histories = player_histories(AFTER_P, {P: [(at(3), at(25))]})
    assert histories[P].rest == 3  # 10 and 20 left out; never negative
    assert player_histories(AFTER_P, {P: [(at(3), None)]})[P].rest == 0


def test_period_start_is_inclusive_and_end_exclusive() -> None:
    histories = player_histories(AFTER_P, {P: [(at(20), at(40))]})
    assert histories[P].rest == 3  # 20 and 30 left out, 40 counts


def test_played_and_run_are_untouched() -> None:
    plain = player_histories(AFTER_P)[P]
    rested = player_histories(AFTER_P, {P: [(at(5), None)]})[P]
    assert (rested.played, rested.run) == (plain.played, plain.run)


def test_someone_elses_period_does_not_affect_them() -> None:
    histories = player_histories(AFTER_P, {Q: [(at(0), None)]})
    assert histories[P].rest == 5


def test_credit_brings_a_returning_player_to_the_lower_median() -> None:
    assert returning_played_credit(1, [2, 4, 6, 8]) == 3  # target 4
    assert returning_played_credit(1, [2, 4, 6]) == 3  # target 4


def test_no_credit_without_anyone_else() -> None:
    assert returning_played_credit(1, []) == 0


def test_no_credit_when_already_at_or_above_the_target() -> None:
    assert returning_played_credit(4, [2, 4, 6, 8]) == 0
    assert returning_played_credit(9, [2, 4, 6, 8]) == 0


def test_a_fresh_newcomer_does_not_drag_the_target_to_zero() -> None:
    assert returning_played_credit(1, [0, 5, 6, 7]) == 4  # target 5


def test_credit_is_a_non_negative_int() -> None:
    for own in range(0, 12):
        credit = returning_played_credit(own, [3, 7, 7, 10, 2])
        assert isinstance(credit, int)
        assert credit >= 0
