"""043 research Decision 3: the parameterised win rule.

The badminton grid is copied from tests/unit/domains/schedule/test_match_wins.py
with win_by=2 to prove the generalised rule is equivalent to the old one; the
remaining cases cover the new parameters (win_by=1 for frames, cap=None for
table tennis and friends).
"""

import pytest

from app.sports.scoring import match_wins

TARGET_21, CAP_30 = 21, 30
TARGET_15, CAP_21 = 15, 21


@pytest.mark.parametrize(
    ("score_x", "score_y", "target", "cap", "expected"),
    [
        (20, 18, TARGET_21, CAP_30, False),
        (21, 19, TARGET_21, CAP_30, True),
        (21, 20, TARGET_21, CAP_30, False),
        (22, 20, TARGET_21, CAP_30, True),
        (29, 29, TARGET_21, CAP_30, False),
        (30, 29, TARGET_21, CAP_30, True),
        (30, 28, TARGET_21, CAP_30, True),
        (15, 13, TARGET_15, CAP_21, True),
        (20, 20, TARGET_15, CAP_21, False),
        (21, 20, TARGET_15, CAP_21, True),
        (14, 14, TARGET_15, CAP_21, False),
        (9, 5, 10, 15, False),
        (10, 8, 10, 15, True),
        (10, 9, 10, 15, False),
        (15, 14, 10, 15, True),
    ],
)
def test_badminton_grid_is_unchanged_with_win_by_two(
    score_x: int, score_y: int, target: int, cap: int, expected: bool
) -> None:
    assert match_wins(score_x, score_y, target=target, win_by=2, cap=cap) is expected


@pytest.mark.parametrize(
    ("score_x", "score_y", "expected"),
    [
        (4, 4, False),
        (5, 4, True),  # first to five frames, a one-frame lead is enough
        (5, 0, True),
        (4, 0, False),
    ],
)
def test_frames_first_to_n_with_win_by_one(score_x: int, score_y: int, expected: bool) -> None:
    assert match_wins(score_x, score_y, target=5, win_by=1, cap=None) is expected


@pytest.mark.parametrize(
    ("score_x", "score_y", "expected"),
    [
        (11, 9, True),
        (11, 10, False),
        (14, 14, False),
        (15, 14, False),
        (15, 13, True),  # table tennis 10:10 then alternate: ends only on a 2-point lead
        (40, 38, True),  # no cap: never ends on a one-point lead however long it runs
        (40, 39, False),
    ],
)
def test_no_cap_only_the_lead_ends_the_match(score_x: int, score_y: int, expected: bool) -> None:
    assert match_wins(score_x, score_y, target=11, win_by=2, cap=None) is expected


def test_win_by_larger_than_the_lead_does_not_end() -> None:
    assert match_wins(21, 19, target=21, win_by=3, cap=None) is False
    assert match_wins(22, 19, target=21, win_by=3, cap=None) is True


def test_legacy_positional_call_still_means_win_by_two() -> None:
    from app.domains.schedule.service import match_wins as legacy

    assert legacy(21, 20, 21, 30) is False
    assert legacy(21, 19, 21, 30) is True
