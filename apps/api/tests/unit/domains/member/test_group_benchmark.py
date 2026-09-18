"""Unit test: group_benchmark.build() — 036-match-insights-benchmarks US3.
No database."""

from dataclasses import asdict

import pytest

from app.domains.group.service import _assign_standard_competition_ranks
from app.domains.member import group_benchmark
from app.domains.member.group_benchmark import BenchmarkMetric, PlayerValues
from app.domains.member.player_dashboard import MetricValue, metric_specs

KEYS = [spec.key for spec in metric_specs()]


def value(number: float | None, matches: int = 10) -> MetricValue:
    return MetricValue(value=number, numerator=0, denominator=100, matches_used=matches)


def player(key: str, **metrics: MetricValue) -> PlayerValues:
    return PlayerValues(player_key=key, values=dict(metrics))


def metric(result: group_benchmark.BenchmarkResult, key: str) -> BenchmarkMetric:
    return next(m for m in result.metrics if m.key == key)


def test_every_metric_is_reported_in_dashboard_order() -> None:
    result = group_benchmark.build("m:me", [])
    assert [m.key for m in result.metrics] == KEYS
    assert all(m.status == "pool_too_small" for m in result.metrics)


@pytest.mark.parametrize(("matches", "counted"), [(4, False), (5, True)])
def test_a_player_needs_five_matches_with_the_metrics_data(matches: int, counted: bool) -> None:
    players = [
        player("m:me", team_serve=value(0.5)),
        player("m:a", team_serve=value(0.6)),
        player("m:b", team_serve=value(0.7)),
        player("m:thin", team_serve=value(0.9, matches)),
    ]
    result = metric(group_benchmark.build("m:me", players), "team_serve")
    assert result.pool_size == (4 if counted else 3)
    assert result.group_average == (0.675 if counted else 0.6)


def test_a_missing_value_does_not_count() -> None:
    players = [
        player("m:me", team_serve=value(0.5)),
        player("m:a", team_serve=value(0.6)),
        player("m:zero", team_serve=value(None)),  # applies, but 0/0
        player("m:none"),  # no such data at all
    ]
    assert metric(group_benchmark.build("m:me", players), "team_serve").pool_size == 2


@pytest.mark.parametrize(("others", "status"), [(1, "pool_too_small"), (2, "ok")])
def test_the_pool_needs_three_players(others: int, status: str) -> None:
    players = [player("m:me", team_serve=value(0.5))] + [
        player(f"m:{i}", team_serve=value(0.6)) for i in range(others)
    ]
    result = metric(group_benchmark.build("m:me", players), "team_serve")
    assert result.status == status
    if status == "pool_too_small":
        assert (result.group_average, result.rank, result.rank_from_bottom) == (None, None, None)
        assert result.mine == value(0.5)  # my own number is still mine to see


def test_status_order_pool_then_direction_then_self() -> None:
    thin_me = [player("m:me", match_points_saved=value(1.0, 2))] + [
        player(f"m:{i}", match_points_saved=value(1.0)) for i in range(2)
    ]
    # Two eligible players: too small wins over everything else.
    assert metric(group_benchmark.build("m:me", thin_me), "match_points_saved").status == (
        "pool_too_small"
    )

    enough = thin_me + [player("m:9", match_points_saved=value(2.0))]
    no_direction = metric(group_benchmark.build("m:me", enough), "match_points_saved")
    assert no_direction.status == "no_direction"  # even though I am below the minimum too
    assert no_direction.group_average == 1.33
    assert (no_direction.rank, no_direction.rank_from_bottom) == (None, None)


def test_below_the_minimum_myself_i_see_the_average_but_no_rank() -> None:
    players = [player("m:me", team_serve=value(0.9, 4))] + [
        player(f"m:{i}", team_serve=value(0.5 + i / 10)) for i in range(3)
    ]
    result = metric(group_benchmark.build("m:me", players), "team_serve")
    assert result.status == "self_below_minimum"
    assert result.pool_size == 3  # I am not in it
    assert result.group_average == 0.6
    assert (result.rank, result.rank_from_bottom) == (None, None)
    assert result.mine == value(0.9, 4)


def test_i_am_not_in_this_group_at_all_for_a_metric() -> None:
    players = [player("m:me")] + [player(f"m:{i}", team_serve=value(0.5)) for i in range(3)]
    result = metric(group_benchmark.build("m:me", players), "team_serve")
    assert result.mine is None
    assert result.status == "self_below_minimum"


def test_higher_is_better_ranks_the_largest_first() -> None:
    players = [
        player("m:me", team_serve=value(0.6)),
        player("m:a", team_serve=value(0.7)),
        player("m:b", team_serve=value(0.5)),
    ]
    result = metric(group_benchmark.build("m:me", players), "team_serve")
    assert (result.rank, result.rank_from_bottom, result.pool_size) == (2, 2, 3)


def test_lower_is_better_ranks_the_smallest_first() -> None:
    players = [
        player("m:me", errors_per_match=value(2.0)),
        player("m:a", errors_per_match=value(5.0)),
        player("m:b", errors_per_match=value(9.0)),
    ]
    result = metric(group_benchmark.build("m:me", players), "errors_per_match")
    assert (result.rank, result.rank_from_bottom) == (1, 3)


def test_ties_share_a_rank_and_the_next_one_skips() -> None:
    players = [
        player("m:top", team_serve=value(0.9)),
        player("m:me", team_serve=value(0.7)),
        player("m:twin", team_serve=value(0.7)),
        player("m:last", team_serve=value(0.1)),
    ]
    mine = metric(group_benchmark.build("m:me", players), "team_serve")
    last = metric(group_benchmark.build("m:last", players), "team_serve")
    assert (mine.rank, mine.rank_from_bottom) == (2, 2)
    assert (last.rank, last.rank_from_bottom) == (4, 1)


def test_two_players_tied_for_last_are_both_last() -> None:
    players = [
        player("m:a", team_serve=value(0.9)),
        player("m:b", team_serve=value(0.8)),
        player("m:me", team_serve=value(0.2)),
        player("m:twin", team_serve=value(0.2)),
    ]
    result = metric(group_benchmark.build("m:me", players), "team_serve")
    assert (result.rank, result.rank_from_bottom) == (3, 1)


def test_everyone_equal_is_first_and_last_at_once() -> None:
    players = [player(f"m:{i}", team_serve=value(0.5)) for i in range(4)]
    result = metric(group_benchmark.build("m:0", players), "team_serve")
    assert (result.rank, result.rank_from_bottom) == (1, 1)


def test_ranks_follow_the_same_rule_as_the_group_standings() -> None:
    wins = [9, 7, 7, 4, 4, 4, 1]
    expected = _assign_standard_competition_ranks(wins)
    players = [player(f"m:{i}", avg_points_for=value(float(w))) for i, w in enumerate(wins)]
    ranks = [
        metric(group_benchmark.build(f"m:{i}", players), "avg_points_for").rank
        for i in range(len(wins))
    ]
    assert ranks == expected


def test_the_average_weighs_every_player_equally() -> None:
    players = [
        player("m:me", team_serve=MetricValue(0.9, 9, 10, 5)),  # few points
        player("m:a", team_serve=MetricValue(0.5, 500, 1000, 40)),  # many
        player("m:b", team_serve=MetricValue(0.4, 400, 1000, 40)),
    ]
    result = metric(group_benchmark.build("m:me", players), "team_serve")
    assert result.group_average == 0.6  # (0.9 + 0.5 + 0.4) / 3, not 909 / 2010


def test_average_rounding_follows_the_metric_kind() -> None:
    rates = [player(f"m:{i}", team_serve=value(v)) for i, v in enumerate([0.3333, 0.3333, 0.3335])]
    assert metric(group_benchmark.build("m:0", rates), "team_serve").group_average == 0.3334
    counts = [player(f"m:{i}", avg_points_for=value(v)) for i, v in enumerate([15.0, 16.0, 16.0])]
    assert metric(group_benchmark.build("m:0", counts), "avg_points_for").group_average == 15.67


def test_the_result_holds_nothing_about_anyone_else() -> None:
    """FR-032: whatever leaves this module is mine, or an aggregate."""
    players = [
        player("m:me", team_serve=value(0.61)),
        player("m:SECRET-A", team_serve=value(0.7777)),
        player("r:SECRET-B", team_serve=value(0.2222)),
    ]
    dumped = repr(asdict(group_benchmark.build("m:me", players)))
    assert "SECRET" not in dumped
    assert "0.7777" not in dumped and "0.2222" not in dumped
