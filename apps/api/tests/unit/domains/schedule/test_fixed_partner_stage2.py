"""Unit test: team-matchup pairing minimizes summed cross-team individual
pair_history (spec FR-019)."""

import uuid

from app.domains.schedule.algorithms import team_matchup_stage2


def _id() -> uuid.UUID:
    return uuid.uuid4()


def test_matches_teams_with_lowest_cross_pair_sum() -> None:
    a1, a2 = _id(), _id()
    b1, b2 = _id(), _id()
    c1, c2 = _id(), _id()
    team_a = (a1, a2)
    team_b = (b1, b2)
    team_c = (c1, c2)

    # a-vs-b cross pairs have played a lot; a-vs-c have never played.
    high_cost_pairs = {
        frozenset((a1, b1)),
        frozenset((a1, b2)),
        frozenset((a2, b1)),
        frozenset((a2, b2)),
    }

    def pair_count(x: uuid.UUID, y: uuid.UUID) -> int:
        return 3 if frozenset((x, y)) in high_cost_pairs else 0

    matchups = team_matchup_stage2([team_a, team_b, team_c], pair_count)
    assert len(matchups) == 1
    matched_teams = set(matchups[0])
    assert matched_teams == {team_a, team_c}


def test_all_teams_matched_exactly_once() -> None:
    teams = [(_id(), _id()) for _ in range(6)]

    def pair_count(_x: uuid.UUID, _y: uuid.UUID) -> int:
        return 0

    matchups = team_matchup_stage2(teams, pair_count)
    assert len(matchups) == 3
    flattened = {team for pair in matchups for team in pair}
    assert flattened == set(teams)
