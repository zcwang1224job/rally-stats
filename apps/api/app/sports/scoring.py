"""Sport-agnostic win rule (spec 043 FR-016, research Decision 3).

One rule for every sport type in ``end_mode='target'``: a side wins once it
reaches ``target`` with a lead of at least ``win_by``, or once it reaches
``cap`` (when there is one). With target=21, win_by=2, cap=30 this is exactly
the badminton rule the product shipped with; ``deuce_threshold`` was never part
of the formula and still is not.
"""


def match_wins(score_x: int, score_y: int, *, target: int, win_by: int, cap: int | None) -> bool:
    """Whether a side on ``score_x`` has won against ``score_y``."""
    if cap is not None and score_x >= cap:
        return True
    return score_x >= target and score_x - score_y >= win_by
