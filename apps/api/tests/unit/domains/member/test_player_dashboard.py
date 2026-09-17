"""Unit test: app.domains.member.player_dashboard —
034-clutch-points-player-dashboard. Pure functions, no database.

`build_sample()` is fed hand-built `match_stats` results (what the rules
produce is `test_match_stats.py`'s business); `aggregate()` is fed hand-built
`MatchSample`s, so each expectation can be checked by eye."""

import uuid
from datetime import UTC, datetime, timedelta

from app.domains.group.match_stats import (
    ClutchResult,
    MatchPointResult,
    PhaseCounts,
    PlayerLandingResult,
    ServeCounts,
    ServeStatsResult,
    StateCounts,
)
from app.domains.member.player_dashboard import (
    DashboardResult,
    MatchSample,
    MetricResult,
    PlayerSample,
    PointLogSample,
    Ratio,
    ServeSample,
    aggregate,
    build_sample,
    normalize_landing,
)

ME, PARTNER, OPP1, OPP2 = (uuid.uuid4() for _ in range(4))
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
NEVER = Ratio(0, 0)

METRIC_KEYS = [
    "team_serve",
    "team_receive",
    "own_serve",
    "own_receive",
    "points_scored",
    "points_lost",
    "scored_lost_ratio",
    "endgame",
    "deuce",
    "match_point_conversion",
    "match_points_saved",
    "when_leading",
    "when_tied",
    "when_trailing",
    "avg_points_for",
    "avg_points_against",
    "avg_win_margin",
    "avg_loss_margin",
]


# ---------------------------------------------------------------- build_sample (T016 a-d)


def _clutch() -> ClutchResult:
    return ClutchResult(
        endgame_from=18,
        endgame={"A": PhaseCounts(5, 11), "B": PhaseCounts(6, 11)},
        deuce={"A": PhaseCounts(2, 6), "B": PhaseCounts(4, 6)},
        match_points={
            "A": MatchPointResult(held=3, converted_on=None, saved=0),
            "B": MatchPointResult(held=1, converted_on=1, saved=3),
        },
        by_state={
            "A": StateCounts(PhaseCounts(10, 23), PhaseCounts(12, 23), PhaseCounts(0, 0)),
            "B": StateCounts(PhaseCounts(0, 0), PhaseCounts(11, 23), PhaseCounts(13, 23)),
        },
    )


def _serve() -> ServeStatsResult:
    return ServeStatsResult(
        teams={"A": ServeCounts(12, 22, 10, 23), "B": ServeCounts(13, 23, 10, 22)},
        players={
            ME: ServeCounts(7, 12, 6, 11),
            PARTNER: ServeCounts(6, 11, 4, 11),
            OPP1: ServeCounts(12, 22, 10, 23),
            OPP2: ServeCounts(0, 0, 0, 0),
        },
        excluded_points=1,
    )


def _build(**overrides: object) -> MatchSample:
    arguments: dict[str, object] = {
        "ended_at": T0,
        "won": True,
        "points_for": 24,
        "points_against": 22,
        "my_team": "B",
        "my_entry_id": ME,
        "is_doubles": True,
        "clutch": _clutch(),
        "serve": _serve(),
        "landings": None,
    }
    arguments.update(overrides)
    return build_sample(**arguments)  # type: ignore[arg-type]


def test_build_sample_reads_my_teams_side_of_the_clutch_result() -> None:
    log = _build().point_log
    assert log is not None
    assert log.endgame == Ratio(6, 11)
    assert log.deuce == Ratio(4, 6)
    assert (log.match_points_held, log.match_point_converted) == (1, True)
    assert log.match_points_saved == 3
    assert (log.leading, log.tied, log.trailing) == (Ratio(0, 0), Ratio(11, 23), Ratio(13, 23))

    other = _build(my_team="A", won=False).point_log
    assert other is not None
    assert (other.match_points_held, other.match_point_converted) == (3, False)
    assert other.trailing == Ratio(0, 0)


def test_build_sample_keeps_not_applicable_phases_as_none() -> None:
    clutch = _clutch()
    no_phases = ClutchResult(None, None, None, clutch.match_points, clutch.by_state)
    log = _build(clutch=no_phases).point_log
    assert log is not None
    assert log.endgame is None and log.deuce is None


def test_build_sample_without_point_log_or_serve_records() -> None:
    sample = _build(clutch=None, serve=None)
    assert sample.point_log is None and sample.serve is None
    assert (sample.won, sample.points_for, sample.points_against) == (True, 24, 22)


def test_build_sample_serve_is_team_level_plus_my_own_in_doubles() -> None:
    serve = _build().serve
    assert serve is not None
    assert (serve.team_serve, serve.team_receive) == (Ratio(13, 23), Ratio(10, 22))
    assert (serve.own_serve, serve.own_receive) == (Ratio(7, 12), Ratio(6, 11))


def test_build_sample_has_no_own_serve_in_singles() -> None:
    singles = ServeStatsResult(
        teams={"A": ServeCounts(5, 10, 4, 9), "B": ServeCounts(5, 9, 5, 10)},
        players={},
        excluded_points=1,
    )
    serve = _build(serve=singles, is_doubles=False).serve
    assert serve is not None
    assert serve.team_serve == Ratio(5, 9)
    assert serve.own_serve is None and serve.own_receive is None


def test_build_sample_player_block_needs_someone_to_have_been_recorded() -> None:
    nobody = {pid: PlayerLandingResult(pid, "B") for pid in (ME, PARTNER)}
    assert _build(landings=nobody).player is None
    assert _build(landings=None).player is None

    # Recorded for my partner only: the match still counts for me, as 0 / 0.
    partner_only = dict(nobody)
    partner_only[PARTNER] = PlayerLandingResult(PARTNER, "B", scored_total=4)
    player = _build(landings=partner_only).player
    assert player is not None and (player.scored, player.lost) == (0, 0)

    mine = dict(nobody)
    mine[ME] = PlayerLandingResult(ME, "B", scored_total=7, lost_total=5)
    player = _build(landings=mine).player
    assert player is not None and (player.scored, player.lost) == (7, 5)


# ---------------------------------------------------------------- aggregate: `all` (T016 e-l)


def _log(
    *,
    endgame: Ratio | None = None,
    deuce: Ratio | None = None,
    held: int = 1,
    converted: bool = True,
    saved: int = 0,
    leading: Ratio = NEVER,
    tied: Ratio = NEVER,
    trailing: Ratio = NEVER,
) -> PointLogSample:
    return PointLogSample(endgame, deuce, held, converted, saved, leading, tied, trailing)


def _sample(
    days_ago: int = 0,
    *,
    won: bool = True,
    points_for: int = 21,
    points_against: int = 15,
    point_log: PointLogSample | None = None,
    serve: ServeSample | None = None,
    player: PlayerSample | None = None,
) -> MatchSample:
    return MatchSample(
        ended_at=T0 - timedelta(days=days_ago),
        won=won,
        points_for=points_for,
        points_against=points_against,
        point_log=point_log,
        serve=serve,
        player=player,
    )


def _metric(result: DashboardResult, key: str) -> MetricResult:
    return next(metric for metric in result.metrics if metric.key == key)


def test_no_matches_is_one_empty_state_not_eighteen_blank_metrics() -> None:
    result = aggregate([])
    assert (result.total_matches, result.has_comparison) == (0, False)
    assert result.metrics == [] and result.trends == [] and result.landing is None


def test_all_eighteen_metrics_come_back_in_a_fixed_order() -> None:
    result = aggregate([_sample()])
    assert [metric.key for metric in result.metrics] == METRIC_KEYS
    assert _metric(result, "team_serve").kind == "rate"
    assert _metric(result, "points_lost").better_when == "lower"
    assert _metric(result, "scored_lost_ratio").kind == "ratio"
    saves = _metric(result, "match_points_saved")
    assert (saves.kind, saves.better_when) == ("average", None)


def test_rate_is_the_sum_of_won_over_the_sum_of_played() -> None:
    serve_a = ServeSample(Ratio(3, 4), Ratio(0, 0), None, None)
    serve_b = ServeSample(Ratio(10, 40), Ratio(0, 0), None, None)
    result = aggregate([_sample(serve=serve_a), _sample(1, serve=serve_b)])
    value = _metric(result, "team_serve").all
    assert value is not None
    assert (value.numerator, value.denominator, value.matches_used) == (13, 44, 2)
    assert value.value == round(13 / 44, 4)
    assert value.value != round((3 / 4 + 10 / 40) / 2, 4)  # NOT the mean of percentages


def test_each_metric_only_counts_matches_that_have_its_data() -> None:
    doubles_serve = ServeSample(Ratio(5, 10), Ratio(4, 10), Ratio(3, 5), Ratio(2, 5))
    singles_serve = ServeSample(Ratio(6, 10), Ratio(5, 10), None, None)
    samples = [
        _sample(0, won=True, points_for=21, points_against=19, serve=doubles_serve,
                point_log=_log(endgame=Ratio(3, 5), deuce=None, held=1, converted=True)),
        _sample(1, won=False, points_for=15, points_against=21, serve=singles_serve,
                point_log=_log(endgame=None, deuce=Ratio(1, 4), held=0, converted=False, saved=2)),
        _sample(2, won=False, points_for=10, points_against=21),  # final score only
    ]
    result = aggregate(samples)

    def used(key: str) -> int:
        value = _metric(result, key).all
        return value.matches_used if value is not None else 0

    assert result.total_matches == 3
    assert used("team_serve") == 2 and used("own_serve") == 1  # singles has no own_*
    assert used("endgame") == 1 and used("deuce") == 1
    assert used("match_point_conversion") == 1  # only where I held one
    assert used("match_points_saved") == 2
    assert used("when_leading") == 2
    assert used("points_scored") == 0
    assert used("avg_points_for") == 3
    assert used("avg_win_margin") == 1 and used("avg_loss_margin") == 2

    loss_margin = _metric(result, "avg_loss_margin").all
    assert loss_margin is not None
    assert (loss_margin.numerator, loss_margin.denominator, loss_margin.value) == (17, 2, 8.5)
    saves = _metric(result, "match_points_saved").all
    assert saves is not None
    assert (saves.numerator, saves.denominator, saves.value) == (2, 2, 1.0)  # per match


def test_zero_denominator_is_a_value_of_none_not_zero() -> None:
    never_trailed = _log(leading=Ratio(15, 20), tied=Ratio(6, 7), trailing=Ratio(0, 0))
    trailing = _metric(aggregate([_sample(point_log=never_trailed)]), "when_trailing").all
    assert trailing is not None
    assert (trailing.value, trailing.denominator, trailing.matches_used) == (None, 0, 1)


def test_metric_nobody_has_data_for_is_none_altogether() -> None:
    result = aggregate([_sample(), _sample(1)])
    for key in ("team_serve", "own_serve", "endgame", "points_scored", "scored_lost_ratio"):
        assert _metric(result, key).all is None, key
    assert _metric(result, "avg_win_margin").all is not None
    assert _metric(result, "avg_loss_margin").all is None  # no losses at all


def test_scored_lost_ratio_without_any_lost_point_has_no_value() -> None:
    result = aggregate([_sample(player=PlayerSample(scored=6, lost=0))])
    ratio = _metric(result, "scored_lost_ratio").all
    assert ratio is not None
    assert (ratio.value, ratio.numerator, ratio.denominator, ratio.matches_used) == (None, 6, 0, 1)
    scored = _metric(result, "points_scored").all
    assert scored is not None and scored.value == 6.0


def test_match_point_conversion_is_matches_closed_out_of_matches_with_a_chance() -> None:
    samples = [
        _sample(0, point_log=_log(held=2, converted=True)),
        _sample(1, won=False, point_log=_log(held=1, converted=False)),
        _sample(2, won=False, point_log=_log(held=0, converted=False)),
    ]
    value = _metric(aggregate(samples), "match_point_conversion").all
    assert value is not None
    assert (value.numerator, value.denominator, value.matches_used) == (1, 2, 2)


def test_ten_matches_or_fewer_have_nothing_to_compare() -> None:
    result = aggregate([_sample(day) for day in range(10)])
    assert result.has_comparison is False
    assert all(metric.recent is None and metric.verdict is None for metric in result.metrics)
    assert aggregate([_sample(day) for day in range(11)]).has_comparison is True


# ---------------------------------------------------------------- recent / verdict (T025 a-f)


def _serve_sample(won: int, total: int) -> ServeSample:
    return ServeSample(Ratio(won, total), Ratio(0, 0), None, None)


def test_recent_is_the_newest_ten_then_filtered_per_metric() -> None:
    # 12 matches, newest first; only the even days have serve data.
    samples = [
        _sample(day, serve=_serve_sample(6, 10) if day % 2 == 0 else None) for day in range(12)
    ]
    result = aggregate(samples)
    assert result.has_comparison is True

    serve = _metric(result, "team_serve")
    assert serve.all is not None and serve.recent is not None
    assert serve.all.matches_used == 6  # days 0,2,4,6,8,10
    assert serve.recent.matches_used == 5  # days 0..9 -> 0,2,4,6,8
    points = _metric(result, "avg_points_for")
    assert points.recent is not None and points.recent.matches_used == 10


def test_fewer_than_three_recent_matches_with_data_is_insufficient() -> None:
    samples = [_sample(day, serve=_serve_sample(6, 10) if day in (0, 1, 11) else None)
               for day in range(12)]
    serve = _metric(aggregate(samples), "team_serve")
    assert serve.recent is not None and serve.recent.matches_used == 2
    assert serve.verdict == "insufficient"


def test_no_recent_data_at_all_is_insufficient_too() -> None:
    samples = [_sample(day, serve=_serve_sample(6, 10) if day >= 10 else None)
               for day in range(12)]
    serve = _metric(aggregate(samples), "team_serve")
    assert serve.all is not None and serve.recent is None
    assert serve.verdict == "insufficient"


def test_value_of_none_on_either_side_is_insufficient() -> None:
    never = _log(trailing=NEVER, leading=Ratio(5, 10))
    samples = [_sample(day, point_log=never) for day in range(12)]
    assert _metric(aggregate(samples), "when_trailing").verdict == "insufficient"


def test_higher_is_better_for_rates() -> None:
    recent_good = [_sample(day, serve=_serve_sample(8, 10)) for day in range(10)]
    older_bad = [_sample(day, serve=_serve_sample(3, 10)) for day in range(10, 20)]
    assert _metric(aggregate(recent_good + older_bad), "team_serve").verdict == "improved"

    recent_bad = [_sample(day, serve=_serve_sample(3, 10)) for day in range(10)]
    older_good = [_sample(day, serve=_serve_sample(8, 10)) for day in range(10, 20)]
    assert _metric(aggregate(recent_bad + older_good), "team_serve").verdict == "declined"


def test_lower_is_better_for_loss_margin_points_lost_and_points_against() -> None:
    """The user's own example: still losing, but by less — that is progress."""
    close_losses = [
        _sample(day, won=False, points_for=19, points_against=21,
                player=PlayerSample(scored=6, lost=3))
        for day in range(10)
    ]
    heavy_losses = [
        _sample(day, won=False, points_for=9, points_against=21,
                player=PlayerSample(scored=6, lost=9))
        for day in range(10, 20)
    ]
    result = aggregate(close_losses + heavy_losses)
    loss_margin = _metric(result, "avg_loss_margin")
    assert loss_margin.all is not None and loss_margin.recent is not None
    assert loss_margin.recent.value == 2.0 and loss_margin.all.value == 7.0
    assert loss_margin.verdict == "improved"
    assert _metric(result, "points_lost").verdict == "improved"
    assert _metric(result, "avg_points_for").verdict == "improved"
    # Opponents scored 21 either way.
    assert _metric(result, "avg_points_against").verdict == "unchanged"


def test_small_differences_are_unchanged() -> None:
    # rate: 0.505 recent vs 0.5025 overall -> under one percentage point
    recent = [_sample(day, serve=_serve_sample(101, 200)) for day in range(10)]
    older = [_sample(day, serve=_serve_sample(100, 200)) for day in range(10, 20)]
    assert _metric(aggregate(recent + older), "team_serve").verdict == "unchanged"

    # average: 21.0 recent vs 20.95 overall -> under 0.1
    recent_points = [_sample(day, points_for=21) for day in range(10)]
    older_points = [_sample(day, points_for=21 if day % 10 else 20) for day in range(10, 20)]
    assert _metric(aggregate(recent_points + older_points), "avg_points_for").verdict == "unchanged"


def test_metric_without_a_direction_is_compared_but_never_judged() -> None:
    samples = [_sample(day, point_log=_log(saved=3 if day < 10 else 0)) for day in range(20)]
    saves = _metric(aggregate(samples), "match_points_saved")
    assert saves.all is not None and saves.recent is not None
    assert (saves.recent.value, saves.all.value) == (3.0, 1.5)  # per match, so comparable
    assert saves.recent.numerator == 30
    assert saves.verdict is None


# ---------------------------------------------------------------- trends (T025 g)


def _trend(result: DashboardResult, key: str) -> list[float | None] | None:
    series = next((trend for trend in result.trends if trend.key == key), None)
    return [point.value for point in series.points] if series is not None else None


def test_trend_is_a_five_match_moving_window_oldest_first() -> None:
    # days_ago 7 (oldest) .. 0 (newest); serve won = 8 - days_ago out of 10
    samples = [_sample(day, serve=_serve_sample(8 - day, 10)) for day in range(8)]
    result = aggregate(samples)

    values = _trend(result, "team_serve")
    assert values is not None and len(values) == 8 - 4
    # oldest window: days 7..3 -> won 1+2+3+4+5 = 15 of 50
    assert values[0] == 0.3 and values[-1] == 0.6  # newest: 4+5+6+7+8 = 30 of 50
    series = next(trend for trend in result.trends if trend.key == "team_serve")
    first = series.points[0]
    assert (first.numerator, first.denominator) == (15, 50)
    assert first.from_ended_at == T0 - timedelta(days=7)
    assert first.to_ended_at == T0 - timedelta(days=3)
    assert [p.to_ended_at for p in series.points] == sorted(p.to_ended_at for p in series.points)


def test_trend_windows_only_count_matches_that_have_the_metrics_data() -> None:
    # 12 matches, serve data on every other one -> 6 eligible -> 2 points
    samples = [
        _sample(day, serve=_serve_sample(5, 10) if day % 2 == 0 else None) for day in range(12)
    ]
    result = aggregate(samples)
    assert _trend(result, "team_serve") == [0.5, 0.5]
    assert len(_trend(result, "avg_points_for") or []) == 12 - 4


def test_fewer_than_six_eligible_matches_has_no_trend() -> None:
    result = aggregate([_sample(day, serve=_serve_sample(5, 10)) for day in range(5)])
    assert _trend(result, "team_serve") is None
    assert _trend(result, "own_serve") is None  # never any data
    assert _trend(aggregate([_sample(day) for day in range(6)]), "avg_points_for") is not None


def test_trend_keeps_only_the_newest_sixty_points() -> None:
    samples = [_sample(day, points_for=day % 21) for day in range(70)]
    series = next(t for t in aggregate(samples).trends if t.key == "avg_points_for")
    assert len(series.points) == 60
    assert series.points[-1].to_ended_at == T0  # the newest window survives the cap


def test_every_metric_kind_can_have_a_trend() -> None:
    samples = [
        _sample(day, point_log=_log(saved=1), player=PlayerSample(scored=4, lost=2))
        for day in range(6)
    ]
    result = aggregate(samples)
    assert _trend(result, "match_points_saved") == [1.0, 1.0]
    assert _trend(result, "scored_lost_ratio") == [2.0, 2.0]


# ---------------------------------------------------------------- landings (T030)


def test_team_a_landings_are_left_alone() -> None:
    assert normalize_landing(0.82, 0.31, "A") == (0.82, 0.31)


def test_team_b_landings_are_rotated_not_mirrored() -> None:
    """Flipping x alone would swap my forehand and backhand sides — the
    court has to turn 180 degrees, so y flips too."""
    assert normalize_landing(0.82, 0.31, "B") == (0.18, 0.69)
    assert normalize_landing(0.5, 0.5, "B") == (0.5, 0.5)


def test_out_of_bounds_stays_out_of_bounds_on_the_other_side() -> None:
    assert normalize_landing(-0.3, 1.3, "B") == (1.3, -0.3)
    assert normalize_landing(1.04, -0.12, "B") == (-0.04, 1.12)


def test_same_physical_spot_is_the_same_point_whichever_team_i_was_on() -> None:
    # "The opponents' back corner on MY right": as team A (left half, facing
    # right) that is x=0.95, y=0.9; as team B (right half, facing left) the
    # raw coordinates of that same spot are x=0.05, y=0.1.
    as_a = normalize_landing(0.95, 0.9, "A")
    as_b = normalize_landing(0.05, 0.1, "B")
    assert as_a == as_b
    assert as_a[0] > 0.5  # my side is always the left half


def test_build_sample_normalizes_my_own_landings_only() -> None:
    landings = {
        ME: PlayerLandingResult(
            ME, "B", scored=[(0.1, 0.2)], scored_total=2, lost=[(0.9, 0.6)], lost_total=1
        ),
        PARTNER: PlayerLandingResult(PARTNER, "B", scored=[(0.3, 0.3)], scored_total=1),
    }
    player = _build(landings=landings).player
    assert player is not None
    assert (player.scored, player.lost) == (2, 1)
    assert player.scored_landings == [(0.9, 0.8)]
    assert player.lost_landings == [(0.1, 0.4)]


def _landed(days_ago: int, scored: list[tuple[float, float]], scored_total: int) -> MatchSample:
    return _sample(
        days_ago,
        player=PlayerSample(scored=scored_total, lost=1, scored_landings=scored, lost_landings=[]),
    )


def test_landing_is_newest_first_so_the_recent_range_is_a_prefix() -> None:
    samples = [_landed(day, [(0.6 + day / 100, 0.5)], scored_total=2) for day in range(12)]
    samples.append(_sample(12))  # no player data: not part of the landing picture
    landing = aggregate(samples).landing

    assert landing is not None
    assert [x for x, _ in landing.scored] == [round(0.6 + day / 100, 3) for day in range(12)]
    assert (landing.scored_total, landing.lost_total, landing.matches_used) == (24, 12, 12)
    assert landing.recent_scored_count == 10 and landing.recent_lost_count == 0
    assert (landing.recent_scored_total, landing.recent_lost_total) == (20, 10)
    assert landing.recent_matches_used == 10
    assert landing.scored[: landing.recent_scored_count] == landing.scored[:10]


def test_landing_coordinates_are_rounded_to_three_places() -> None:
    landing = aggregate([_landed(0, [(0.123456, 0.987654)], scored_total=1)]).landing
    assert landing is not None and landing.scored == [(0.123, 0.988)]


def test_ten_matches_or_fewer_report_the_recent_range_as_the_whole() -> None:
    landing = aggregate([_landed(day, [(0.7, 0.5)], scored_total=1) for day in range(4)]).landing
    assert landing is not None
    assert (landing.recent_scored_count, landing.recent_scored_total) == (4, 4)
    assert landing.recent_matches_used == landing.matches_used == 4


def test_no_plotted_point_anywhere_means_no_landing_block() -> None:
    assert aggregate([_landed(0, [], scored_total=5)]).landing is None  # players, no coordinates
    assert aggregate([_sample()]).landing is None
