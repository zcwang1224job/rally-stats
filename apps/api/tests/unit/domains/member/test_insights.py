"""Unit test: insights.derive() — 036-match-insights-benchmarks US1.
No database: samples are built by hand and aggregated by the real
`player_dashboard.aggregate()`, so every number an insight quotes can be
compared with the dashboard's own."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.member import group_benchmark, insights, matchups
from app.domains.member.insights import Insight, InsightsResult
from app.domains.member.player_dashboard import (
    EndingSample,
    MatchSample,
    MetricValue,
    PointLogSample,
    Ratio,
    ServeSample,
    aggregate,
)
from app.domains.member.player_identity import PlayerRef

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
EVEN = Ratio(0, 0)


def serve(
    team_serve: tuple[int, int],
    team_receive: tuple[int, int],
    own_serve: tuple[int, int] | None = None,
    own_receive: tuple[int, int] | None = None,
) -> ServeSample:
    return ServeSample(
        team_serve=Ratio(*team_serve),
        team_receive=Ratio(*team_receive),
        own_serve=Ratio(*own_serve) if own_serve else None,
        own_receive=Ratio(*own_receive) if own_receive else None,
    )


def log(
    *,
    endgame: tuple[int, int] | None = None,
    deuce: tuple[int, int] | None = None,
    leading: tuple[int, int] = (0, 0),
    tied: tuple[int, int] = (0, 0),
    trailing: tuple[int, int] = (0, 0),
) -> PointLogSample:
    return PointLogSample(
        endgame=Ratio(*endgame) if endgame else None,
        deuce=Ratio(*deuce) if deuce else None,
        match_points_held=0,
        match_point_converted=False,
        match_points_saved=0,
        leading=Ratio(*leading),
        tied=Ratio(*tied),
        trailing=Ratio(*trailing),
    )


def ending(
    winners: int, opponent_errors: int, beaten: int, own_errors: int, by_type: dict[str, int]
) -> EndingSample:
    return EndingSample(winners, opponent_errors, beaten, own_errors, by_type)


def sample(
    age_days: int,
    points_for: int = 20,
    points_against: int = 20,
    *,
    serve_: ServeSample | None = None,
    log_: PointLogSample | None = None,
    ending_: EndingSample | None = None,
) -> MatchSample:
    return MatchSample(
        ended_at=NOW - timedelta(days=age_days),
        won=points_for > points_against,
        points_for=points_for,
        points_against=points_against,
        point_log=log_,
        serve=serve_,
        player=None,
        ending=ending_,
    )


def derive(samples: list[MatchSample]) -> InsightsResult:
    return insights.derive(samples, aggregate(samples))


def only(items: list[Insight]) -> Insight:
    assert len(items) == 1, items
    return items[0]


def three_even_matches_with_endgame(won_of_3000: int) -> list[MatchSample]:
    """Three 20:20 matches — the endgame baseline (my pooled point share) is
    exactly 0.5 — with 1000 endgame points each."""
    per_match = [won_of_3000 // 3 + (1 if i < won_of_3000 % 3 else 0) for i in range(3)]
    return [sample(i, log_=log(endgame=(won, 1000))) for i, won in enumerate(per_match)]


# --- (a) rate_vs_overall: mild / strong boundaries, both directions -------


@pytest.mark.parametrize(
    ("won", "expected"),
    [
        (1649, None),  # 0.5497 − 0.5 = 0.0497
        (1650, ("strength", "mild")),  # exactly 0.05
        (1799, ("strength", "mild")),  # 0.0997
        (1800, ("strength", "strong")),  # exactly 0.10
        (1350, ("weakness", "mild")),
        (1200, ("weakness", "strong")),
        (1351, None),
    ],
)
def test_rate_vs_overall_boundaries(won: int, expected: tuple[str, str] | None) -> None:
    result = derive(three_even_matches_with_endgame(won))
    found = [i for i in result.strengths + result.weaknesses if i.metric_key == "endgame"]
    if expected is None:
        assert found == []
        return
    insight = only(found)
    assert (insight.bucket, insight.level) == expected
    assert insight.rule == "rate_vs_overall"
    assert insight.source == "self"
    assert insight.params["baseline"] == 0.5


@pytest.mark.parametrize("key", ["team_serve", "team_receive", "own_serve", "own_receive"])
def test_every_serve_metric_is_covered(key: str) -> None:
    strong = (700, 1000)
    flat = (500, 1000)
    parts = {k: (strong if k == key else flat) for k in insights.RATE_VS_OVERALL_KEYS[:4]}
    samples = [
        sample(
            i,
            serve_=serve(
                parts["team_serve"], parts["team_receive"], parts["own_serve"], parts["own_receive"]
            ),
        )
        for i in range(3)
    ]
    assert only(derive(samples).strengths).metric_key == key


def test_endgame_is_covered() -> None:
    samples = [sample(i, log_=log(endgame=(70, 100))) for i in range(3)]
    assert only(derive(samples).strengths).metric_key == "endgame"


# --- (b) the baseline (FR-011, research.md Decision 1) --------------------


def test_serve_baseline_is_the_conditional_expectation_per_match() -> None:
    samples = [
        sample(0, 21, 7, serve_=serve((20, 30), (5, 10))),  # a match I dominated
        sample(1, 7, 21, serve_=serve((3, 10), (5, 30))),  # and one I lost badly
    ]
    # A serve point follows a point I won, so one of my wins is spent:
    # (21−1)/27 for the 30 serve points of match 1, (7−1)/27 for the 10 of
    # match 2 → (30·20 + 10·6) / (27·40).
    assert insights.expected_rate("team_serve", samples) == round(660 / 1080, 4)
    # A receive point follows a point I lost: 21/27 and 7/27, weights 10 and 30.
    assert insights.expected_rate("team_receive", samples) == round(420 / 1080, 4)
    # Neither is the pooled share (28 / 56), nor each match's plain share
    # weighted by its serve points (0.625) — both measurably biased.
    assert insights.expected_rate("team_serve", samples) not in (0.5, 0.625)


def test_endgame_baseline_is_my_pooled_share_of_the_matches_that_had_one() -> None:
    samples = [
        sample(0, 21, 7, log_=log(endgame=(3, 4))),
        sample(1, 7, 21, log_=log(endgame=(1, 4))),
        sample(2, 21, 0),  # no point log: takes no part
    ]
    assert insights.expected_rate("endgame", samples) == 0.5


def test_baseline_ignores_matches_without_the_metrics_data() -> None:
    with_serve = [sample(i, 20, 20, serve_=serve((600, 1000), (500, 1000))) for i in range(3)]
    blowouts_without_serve_records = [sample(10 + i, 21, 3) for i in range(5)]
    assert insights.expected_rate("team_serve", with_serve) == round(19 / 39, 4)
    assert insights.expected_rate(
        "team_serve", with_serve + blowouts_without_serve_records
    ) == round(19 / 39, 4)


def test_baseline_is_none_without_any_weight() -> None:
    assert insights.expected_rate("team_serve", [sample(0)]) is None


def test_a_whitewash_does_not_break_the_baseline() -> None:
    assert (
        insights.expected_rate("team_receive", [sample(0, 21, 0, serve_=serve((20, 20), (0, 0)))])
        is None
    )
    assert (
        insights.expected_rate("team_serve", [sample(0, 21, 0, serve_=serve((20, 20), (0, 0)))])
        == 1.0
    )


# --- (c) minimum sample --------------------------------------------------


@pytest.mark.parametrize(("total", "expected"), [(29, 0), (30, 1)])
def test_needs_thirty_points(total: int, expected: int) -> None:
    per_match = total // 3
    extra = total - per_match * 3
    samples = [
        sample(
            i,
            serve_=serve(
                (per_match + (extra if i == 0 else 0), per_match + (extra if i == 0 else 0)),
                (5, 10),
            ),
        )
        for i in range(3)
    ]
    found = [i for i in derive(samples).strengths if i.metric_key == "team_serve"]
    assert len(found) == expected


@pytest.mark.parametrize(("matches", "expected"), [(2, 0), (3, 1)])
def test_needs_three_matches(matches: int, expected: int) -> None:
    samples = [sample(i, serve_=serve((700, 1000), (500, 1000))) for i in range(matches)]
    assert len(derive(samples).strengths) == expected


# --- (d) deuce against an even split -------------------------------------


def test_deuce_is_measured_against_fifty_percent() -> None:
    # A player who wins 70% of all points: 0.6 at deuce is BELOW their own
    # rate but above even — and even is what deuce is measured against.
    samples = [sample(i, 21, 9, log_=log(deuce=(60, 100))) for i in range(3)]
    insight = only(derive(samples).strengths)
    assert (insight.rule, insight.metric_key, insight.level) == ("deuce_vs_even", "deuce", "strong")
    assert insight.params["baseline"] == 0.5


# --- (e) metrics that must never be self-contrasted (FR-012, SC-003) ------


def test_score_state_metrics_and_conversion_never_produce_a_self_insight() -> None:
    samples = [
        sample(i, log_=log(leading=(900, 1000), tied=(900, 1000), trailing=(100, 1000)))
        for i in range(3)
    ]
    result = derive(samples)
    assert result.strengths == []
    assert result.weaknesses == []
    assert not set(insights.RATE_VS_OVERALL_KEYS) & {
        "when_leading",
        "when_tied",
        "when_trailing",
        "match_point_conversion",
        "match_points_saved",
    }


# --- (f) paired metrics speak once ---------------------------------------


def test_serve_and_receive_produce_one_sentence_the_larger_gap() -> None:
    samples = [sample(i, serve_=serve((580, 1000), (380, 1000))) for i in range(3)]
    result = derive(samples)
    assert result.strengths == []
    assert only(result.weaknesses).metric_key == "team_receive"


def test_equal_gaps_keep_the_weakness() -> None:
    # 20:20 → serve baseline 19/39 = 0.4872, receive 20/39 = 0.5128: both
    # exactly 0.10 away.
    samples = [sample(i, serve_=serve((5872, 10000), (4128, 10000))) for i in range(3)]
    result = derive(samples)
    assert result.strengths == []
    assert only(result.weaknesses).metric_key == "team_receive"


def test_the_two_pairs_are_independent() -> None:
    samples = [
        sample(i, serve_=serve((600, 1000), (500, 1000), (500, 1000), (380, 1000)))
        for i in range(3)
    ]
    result = derive(samples)
    assert only(result.strengths).metric_key == "team_serve"
    assert only(result.weaknesses).metric_key == "own_receive"


# --- (g) ending rules ----------------------------------------------------


@pytest.mark.parametrize(
    ("own_errors", "beaten", "expected_level"),
    [(59, 41, None), (60, 40, "mild"), (69, 31, "mild"), (70, 30, "strong")],
)
def test_error_share_thresholds(own_errors: int, beaten: int, expected_level: str | None) -> None:
    samples = [sample(0, ending_=ending(10, 90, beaten, own_errors, {"out": 1, "net": 1}))]
    found = [i for i in derive(samples).weaknesses if i.rule == "error_share_high"]
    if expected_level is None:
        assert found == []
    else:
        assert only(found).level == expected_level


def test_error_share_needs_twenty_recorded_lost_points() -> None:
    assert derive([sample(0, ending_=ending(0, 0, 4, 15, {"out": 15}))]).weaknesses == []
    assert len(derive([sample(0, ending_=ending(0, 0, 5, 15, {"out": 15}))]).weaknesses) == 1


def test_dominant_error_only_when_it_is_more_than_half() -> None:
    half = derive([sample(0, ending_=ending(0, 0, 10, 40, {"out": 20, "net": 20}))])
    assert only(half.weaknesses).params["dominant_error"] is None

    most = derive([sample(0, ending_=ending(0, 0, 10, 40, {"out": 21, "net": 19}))])
    insight = only(most.weaknesses)
    assert insight.params["dominant_error"] == "out"
    assert insight.params["dominant_share"] == 0.525


@pytest.mark.parametrize(
    ("winners", "gifted", "expected_level"),
    [(49, 51, None), (50, 50, "mild"), (60, 40, "strong")],
)
def test_winner_share_thresholds(winners: int, gifted: int, expected_level: str | None) -> None:
    samples = [sample(0, ending_=ending(winners, gifted, 50, 50, {"net": 50}))]
    found = [i for i in derive(samples).strengths if i.rule == "winner_share_high"]
    if expected_level is None:
        assert found == []
    else:
        assert only(found).level == expected_level


# --- (h) recent change ---------------------------------------------------


def history(
    recent_margin: int, old_margin: int, recent: int = 10, old: int = 10
) -> list[MatchSample]:
    """All losses; `avg_loss_margin` (lower is better) moves with the margin."""
    newest = [sample(i, 21 - recent_margin, 21) for i in range(recent)]
    oldest = [sample(100 + i, 21 - old_margin, 21) for i in range(old)]
    return newest + oldest


def test_no_recent_list_without_a_comparison() -> None:
    assert derive(history(2, 10, recent=5, old=5)).recent == []


def test_a_lower_is_better_metric_improves_when_it_falls() -> None:
    result = derive(history(recent_margin=2, old_margin=10))
    by_key = {i.metric_key: i for i in result.recent}
    assert by_key["avg_loss_margin"].params["direction"] == "improved"
    assert by_key["avg_loss_margin"].source == "trend"
    assert by_key["avg_loss_margin"].rule == "recent_change"


@pytest.mark.parametrize(
    ("recent_margin", "expected_level"),
    # all = (recent + 10) / 2; relative change = |recent − all| / all
    [(9, None), (7, "mild"), (4, "strong")],
)
def test_relative_change_thresholds(recent_margin: int, expected_level: str | None) -> None:
    result = derive(history(recent_margin=recent_margin, old_margin=10))
    found = [i for i in result.recent if i.metric_key == "avg_loss_margin"]
    if expected_level is None:
        assert found == []
    else:
        assert only(found).level == expected_level


def test_zero_overall_value_is_not_a_division_error() -> None:
    samples = [
        sample(i, ending_=ending(0, 5, 5, 0, {})) for i in range(20)
    ]  # winners_per_match is 0 everywhere
    assert [i for i in derive(samples).recent if i.metric_key == "winners_per_match"] == []


def test_recent_list_keeps_at_least_one_improvement() -> None:
    # Points for fall hard (two strong declines) while serve improves a
    # little (0.50 → 0.56: mild), so on merit it would rank third.
    newest = [sample(i, 8, 21, serve_=serve((56, 100), (40, 100))) for i in range(10)]
    oldest = [sample(100 + i, 19, 21, serve_=serve((44, 100), (40, 100))) for i in range(10)]
    result = derive(newest + oldest)
    assert len(result.recent) == 2
    directions = [i.params["direction"] for i in result.recent]
    assert directions[0] == "declined"
    assert directions[1] == "improved"


# --- (i) ordering and caps -----------------------------------------------


def test_strong_before_mild_then_bigger_sample_then_metric_order() -> None:
    samples = [
        sample(
            i,
            serve_=serve((560, 1000), (500, 1000), (280, 400), (200, 400)),
            log_=log(endgame=(140, 200)),
        )
        for i in range(3)
    ]
    keys = [i.metric_key for i in derive(samples).strengths]
    # own_serve (strong, 1200 pts) before endgame (strong, 600 pts), both
    # before team_serve (mild, though it has the biggest sample of all).
    assert keys == ["own_serve", "endgame", "team_serve"]


def test_lists_are_capped() -> None:
    result = derive(
        [
            sample(
                i,
                serve_=serve((700, 1000), (500, 1000), (700, 1000), (500, 1000)),
                log_=log(endgame=(70, 100), tied=(70, 100), deuce=(70, 100)),
                ending_=ending(70, 30, 50, 50, {"net": 50}),
            )
            for i in range(3)
        ]
    )
    assert len(result.strengths) == 3


# --- (j) status ----------------------------------------------------------


def test_no_matches_is_insufficient_data() -> None:
    result = derive([])
    assert result.status == "insufficient_data"
    assert (result.strengths, result.weaknesses, result.recent, result.matchups) == ([], [], [], [])


def test_too_few_matches_is_insufficient_data() -> None:
    assert derive([sample(0, serve_=serve((9, 10), (1, 10)))]).status == "insufficient_data"


def test_enough_data_but_nothing_stands_out_is_balanced() -> None:
    samples = [sample(i, serve_=serve((510, 1000), (490, 1000))) for i in range(3)]
    assert derive(samples).status == "balanced"


def test_any_insight_makes_it_ok() -> None:
    assert derive(three_even_matches_with_endgame(1800)).status == "ok"


# --- (k)(l)(m) reproducible, consistent with the dashboard ---------------


def test_same_input_same_output() -> None:
    samples = three_even_matches_with_endgame(1800) + history(2, 10)
    assert derive(samples) == derive(samples)


def test_params_are_the_dashboards_own_numbers() -> None:
    samples = three_even_matches_with_endgame(1700)
    dashboard = aggregate(samples)
    insight = only(insights.derive(samples, dashboard).strengths)
    metric = next(m for m in dashboard.metrics if m.key == "endgame")
    assert metric.all is not None
    assert insight.params["value"] == metric.all.value
    assert insight.params["numerator"] == metric.all.numerator
    assert insight.params["denominator"] == metric.all.denominator
    assert insight.params["matches_used"] == metric.all.matches_used


def test_without_matchups_or_benchmark() -> None:
    result = derive(three_even_matches_with_endgame(1800))
    assert result.matchups == []
    assert result.benchmark_group_name is None


# --- (n) zero bias on synthetic data (SC-003, research.md Decision 1) -----


def _simulate(rng: random.Random, p: float) -> MatchSample:
    """One rally-scoring match to 21 (cap 30) where I win every point with
    the same probability `p`, whoever serves and whatever the score. As in
    033 FR-012, the first point counts toward neither serve nor receive."""
    mine = theirs = 0
    i_serve = rng.random() < 0.5
    first = True
    counts = {"serve": [0, 0], "receive": [0, 0], "endgame": [0, 0]}
    while True:
        won = rng.random() < p
        for name, applies in (
            ("serve", i_serve and not first),
            ("receive", not i_serve and not first),
            ("endgame", max(mine, theirs) >= 18),
        ):
            if applies:
                counts[name][0] += int(won)
                counts[name][1] += 1
        mine, theirs = mine + int(won), theirs + int(not won)
        i_serve, first = won, False
        top, low = max(mine, theirs), min(mine, theirs)
        if top == 30 or (top >= 21 and top - low >= 2):
            break
    return sample(
        0,
        mine,
        theirs,
        serve_=serve(
            (counts["serve"][0], counts["serve"][1]), (counts["receive"][0], counts["receive"][1])
        ),
        log_=log(endgame=(counts["endgame"][0], counts["endgame"][1])),
    )


@pytest.mark.parametrize(
    ("label", "low", "high"),
    [("weak", 0.30, 0.50), ("even", 0.35, 0.65), ("strong", 0.50, 0.70)],
)
def test_a_player_with_no_situational_skill_gets_no_self_insight(
    label: str, low: float, high: float
) -> None:
    """The null hypothesis, for three kinds of player: nothing about serving,
    receiving or the endgame makes any difference to them, so an honest
    baseline must sit on top of the metric and no sentence may come out."""
    rng = random.Random(36)
    samples = [_simulate(rng, rng.uniform(low, high)) for _ in range(1500)]

    result = derive(samples)
    assert [i for i in result.strengths + result.weaknesses if i.rule == "rate_vs_overall"] == []

    dashboard = aggregate(samples)
    for key, tolerance in (("team_serve", 0.01), ("team_receive", 0.01), ("endgame", 0.015)):
        metric = next(m for m in dashboard.metrics if m.key == key)
        assert metric.all is not None and metric.all.value is not None
        baseline = insights.expected_rate(key, samples)
        assert baseline is not None
        assert abs(metric.all.value - baseline) < tolerance, (label, key)


def test_the_naive_serve_baselines_are_measurably_worse() -> None:
    """Why `expected_rate()` is not simply "my overall point share": both
    obvious choices are off by more than a point on serve, in opposite
    directions, for a player who serves no better than they receive."""
    rng = random.Random(36)
    samples = [_simulate(rng, rng.uniform(0.35, 0.65)) for _ in range(1500)]
    metric = next(m for m in aggregate(samples).metrics if m.key == "team_serve").all
    assert metric is not None and metric.value is not None

    pooled = sum(s.points_for for s in samples) / sum(
        s.points_for + s.points_against for s in samples
    )
    serve_points = [s.serve.team_serve.total for s in samples if s.serve is not None]
    plain_share_weighted = sum(
        points * s.points_for / (s.points_for + s.points_against)
        for points, s in zip(serve_points, samples, strict=True)
    ) / sum(serve_points)
    exact = insights.expected_rate("team_serve", samples)
    assert exact is not None

    assert metric.value - pooled > 0.008  # reads serving as a strength
    assert metric.value - plain_share_weighted < -0.008  # reads it as a weakness
    assert abs(metric.value - exact) < 0.004


# --- US2 (FR-025): notable partners and opponents -------------------------


def _matchup_inputs(
    *, partner_wins: int, partner_losses: int, other_wins: int, other_losses: int
) -> "list[matchups.MatchupInput]":
    """Doubles matches with partner m:p (vs. rivals r:1/r:2) and with partner
    m:q (vs. rivals r:3/r:4), so the overall doubles win rate is a mix."""

    def ref(key: str) -> PlayerRef:
        return PlayerRef(key=key, nickname=key, member_id=key[2:] if key[0] == "m" else None)

    def some(
        partner: str, rivals: tuple[str, str], wins: int, losses: int
    ) -> "list[matchups.MatchupInput]":
        return [
            matchups.MatchupInput(
                ended_at=NOW - timedelta(days=index),
                won=index < wins,
                margin=3 if index < wins else -3,
                is_doubles=True,
                partners=(ref(partner),),
                opponents=(ref(rivals[0]), ref(rivals[1])),
            )
            for index in range(wins + losses)
        ]

    return some("m:p", ("r:1", "r:2"), partner_wins, partner_losses) + some(
        "m:q", ("r:3", "r:4"), other_wins, other_losses
    )


def derive_with(inputs: "list[matchups.MatchupInput]") -> InsightsResult:
    return insights.derive([], aggregate([]), matchups.build(inputs))


def test_a_partner_well_above_my_doubles_win_rate_is_named() -> None:
    # With m:p 9/10, with m:q 1/10 → doubles overall 0.50.
    result = derive_with(
        _matchup_inputs(partner_wins=9, partner_losses=1, other_wins=1, other_losses=9)
    )
    partner = next(i for i in result.matchups if i.rule == "partner_above_overall")
    assert (partner.bucket, partner.source, partner.metric_key) == ("matchup", "matchup", None)
    assert partner.player == PlayerRef(key="m:p", nickname="m:p", member_id="p")
    assert partner.level == "strong"  # 0.90 − 0.50 = 0.40
    assert partner.params == {
        "win_rate": 0.9,
        "matches": 10,
        "wins": 9,
        "losses": 1,
        "baseline": 0.5,
        "diff": 0.4,
    }
    assert result.status == "ok"


def test_an_opponent_well_below_my_overall_win_rate_is_named() -> None:
    result = derive_with(
        _matchup_inputs(partner_wins=9, partner_losses=1, other_wins=1, other_losses=9)
    )
    opponent = next(i for i in result.matchups if i.rule == "opponent_below_overall")
    # r:3 and r:4 tie at 0.10; the smaller key is named, and only one of them.
    assert opponent.player is not None and opponent.player.key == "r:3"
    assert opponent.params["diff"] == -0.4
    assert len(result.matchups) == 2  # one partner, one opponent, never more


@pytest.mark.parametrize(("matches", "expected"), [(4, 0), (5, 1)])
def test_matchup_insights_need_five_matches_together(matches: int, expected: int) -> None:
    result = derive_with(
        _matchup_inputs(partner_wins=matches, partner_losses=0, other_wins=0, other_losses=20)
    )
    assert len([i for i in result.matchups if i.rule == "partner_above_overall"]) == expected


@pytest.mark.parametrize(
    ("wins", "level"),
    # other partner 5/10 → doubles overall = (wins + 5) / 20
    [(7, None), (8, "mild"), (10, "mild")],
)
def test_matchup_gap_thresholds(wins: int, level: str | None) -> None:
    result = derive_with(
        _matchup_inputs(partner_wins=wins, partner_losses=10 - wins, other_wins=5, other_losses=5)
    )
    found = [i for i in result.matchups if i.rule == "partner_above_overall"]
    if level is None:
        assert found == []
    else:
        assert only(found).level == level


def test_nothing_notable_about_anyone_is_balanced_not_insufficient() -> None:
    result = derive_with(
        _matchup_inputs(partner_wins=5, partner_losses=5, other_wins=5, other_losses=5)
    )
    assert result.matchups == []
    assert result.status == "balanced"


# --- US3 (FR-033): where I stand in a group ---------------------------------


def _pool(
    key: str, mine: float, others: list[float], matches: int = 10
) -> insights.BenchmarkContext:
    """A group benchmark where I have `mine` for `key` and the others have
    `others` — built by the real `group_benchmark.build()`."""

    def value(number: float) -> MetricValue:
        return MetricValue(value=number, numerator=0, denominator=100, matches_used=matches)

    players = [group_benchmark.PlayerValues("m:me", {key: value(mine)})] + [
        group_benchmark.PlayerValues(f"m:{index}", {key: value(number)})
        for index, number in enumerate(others)
    ]
    return insights.BenchmarkContext("週三羽球", group_benchmark.build("m:me", players))


def derive_in_group(
    context: insights.BenchmarkContext, samples: list[MatchSample] | None = None
) -> InsightsResult:
    samples = samples or []
    return insights.derive(samples, aggregate(samples), None, context)


@pytest.mark.parametrize(("others", "expected"), [(2, 0), (3, 1)])
def test_quartile_sentences_need_four_players(others: int, expected: int) -> None:
    result = derive_in_group(_pool("team_serve", 0.9, [0.5] * others))
    assert len(result.strengths) == expected


def test_first_of_four_is_a_mild_strength_with_the_groups_numbers() -> None:
    result = derive_in_group(_pool("team_serve", 0.62, [0.5, 0.48, 0.46]))
    strength = only(result.strengths)
    assert (strength.rule, strength.source, strength.bucket) == (
        "benchmark_quartile",
        "benchmark",
        "strength",
    )
    assert strength.level == "mild"  # a group of four is never "strong"
    assert strength.metric_key == "team_serve"
    assert strength.params == {
        "mine": 0.62,
        "group_average": 0.515,
        "diff": 0.105,
        "rank": 1,
        "pool_size": 4,
        "kind": "rate",
    }
    assert result.benchmark_group_name == "週三羽球"
    assert result.status == "ok"


@pytest.mark.parametrize(
    ("pool", "top", "bottom"),
    # q = pool // 4: never more than a quarter of the group
    [(5, {1}, {5}), (8, {1, 2}, {7, 8}), (9, {1, 2}, {8, 9})],
)
def test_the_quartile_cut(pool: int, top: set[int], bottom: set[int]) -> None:
    ladder = [round(0.9 - 0.05 * step, 2) for step in range(pool)]  # rank 1 … rank `pool`
    for rank in range(1, pool + 1):
        mine = ladder[rank - 1]
        others = ladder[: rank - 1] + ladder[rank:]
        result = derive_in_group(_pool("team_serve", mine, others))
        assert bool(result.strengths) == (rank in top), (pool, rank)
        assert bool(result.weaknesses) == (rank in bottom), (pool, rank)


def test_strong_needs_first_or_last_place_in_a_group_of_eight() -> None:
    ladder = [round(0.9 - 0.05 * step, 2) for step in range(8)]
    first = derive_in_group(_pool("team_serve", ladder[0], ladder[1:]))
    second = derive_in_group(_pool("team_serve", ladder[1], ladder[:1] + ladder[2:]))
    last = derive_in_group(_pool("team_serve", ladder[7], ladder[:7]))
    assert only(first.strengths).level == "strong"
    assert only(second.strengths).level == "mild"
    assert only(last.weaknesses).level == "strong"


def test_two_players_tied_for_last_are_both_flagged() -> None:
    result = derive_in_group(_pool("team_serve", 0.2, [0.9, 0.8, 0.2]))
    assert only(result.weaknesses).params["rank"] == 3


def test_everyone_equal_says_nothing() -> None:
    result = derive_in_group(_pool("team_serve", 0.5, [0.5, 0.5, 0.5]))
    assert result.strengths == [] and result.weaknesses == []
    assert result.status == "balanced"


def test_lower_is_better_metrics_rank_the_right_way_round() -> None:
    result = derive_in_group(_pool("errors_per_match", 1.0, [4.0, 5.0, 6.0]))
    strength = only(result.strengths)
    assert strength.params["rank"] == 1 and strength.params["kind"] == "average"


def test_metrics_without_a_rank_are_skipped() -> None:
    assert derive_in_group(_pool("match_points_saved", 9.0, [1.0, 1.0, 1.0])).strengths == []
    thin = derive_in_group(_pool("team_serve", 0.9, [0.5, 0.5, 0.5], matches=4))
    assert thin.strengths == []


def test_score_state_metrics_may_speak_through_the_group(  # FR-012 only bars SELF-contrast
) -> None:
    result = derive_in_group(_pool("when_trailing", 0.30, [0.5, 0.5, 0.5]))
    assert only(result.weaknesses).metric_key == "when_trailing"


def test_the_group_wins_over_a_self_contrast_on_the_same_metric() -> None:
    # On my own, endgame (0.70 vs. a 0.50 baseline) is a strong strength…
    samples = [sample(i, log_=log(endgame=(70, 100))) for i in range(3)]
    assert only(derive(samples).strengths).source == "self"
    # …but in this group 0.70 is the worst of four: that is what gets said.
    result = derive_in_group(_pool("endgame", 0.70, [0.9, 0.85, 0.8]), samples)
    assert result.strengths == []
    weakness = only(result.weaknesses)
    assert (weakness.source, weakness.metric_key) == ("benchmark", "endgame")


def test_group_sentences_come_before_my_own_at_the_same_level() -> None:
    samples = [sample(i, log_=log(endgame=(56, 100))) for i in range(3)]  # mild, self
    result = derive_in_group(_pool("team_serve", 0.62, [0.5, 0.48, 0.46]), samples)  # mild, group
    assert [(i.source, i.metric_key) for i in result.strengths] == [
        ("benchmark", "team_serve"),
        ("self", "endgame"),
    ]


def test_recent_changes_are_untouched_by_the_group() -> None:
    samples = history(recent_margin=2, old_margin=10)
    alone = derive(samples).recent
    in_group = derive_in_group(_pool("avg_loss_margin", 6.0, [9.0, 9.5, 10.0]), samples)
    assert in_group.recent == alone
    assert only(in_group.strengths).metric_key == "avg_loss_margin"  # and still said here


# --- the Literal sets are the ones the response schema declares ----------


def test_rule_literals() -> None:
    from typing import get_args

    assert get_args(insights.InsightRule) == (
        "rate_vs_overall",
        "deuce_vs_even",
        "error_share_high",
        "winner_share_high",
        "recent_change",
        "partner_above_overall",
        "opponent_below_overall",
        "benchmark_quartile",
    )
