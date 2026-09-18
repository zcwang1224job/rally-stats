"""036-match-insights-benchmarks US1: turn a dashboard into a few sentences —
what stands out as a strength, what to work on, what changed lately.

Pure functions, no ORM, no `AsyncSession` (same rule as `player_dashboard`).
Rules and thresholds live ONLY here; the response carries a rule code plus
the numbers behind it, never a sentence (Constitution VIII) — the frontend
owns the wording in both languages, so switching language can never change
which insights were picked (US1-10).

`derive()` runs AFTER `player_dashboard.aggregate()` and only reads its
result: not one of the 23 metrics is recomputed or redefined here (FR-002).

The baseline — "what would this number be if the situation made no
difference to me" — was chosen by measurement, not by argument (FR-011,
research.md Decision 1). Simulating players who win every point of a match
with one fixed probability, for weak / even / strong players:

- Serve and receive have two opposite biases. Whoever wins a rally serves
  next, so matches I dominate hold more of my serve points (pooling all
  matches reads ~+1pp too high on serve). But a serve point is by definition
  "the point after one I won": with my match total fixed, one win is already
  spent, so the chance of winning it is (won − 1) / (played − 1), not
  won / played (weighting each match's plain share reads ~−1.5pp, which is
  WORSE than pooling). Using that exact conditional expectation per match —
  won / (played − 1) for receive points — measures ±0.06pp. 033 FR-012
  already keeps each match's first point out of both denominators, which is
  what makes it exact.
- Endgame is within ±0.5pp whatever the baseline; the pooled share is used.
- `when_tied` cannot be fixed: how often a match is tied depends on the same
  luck that decides its score, and every baseline tried leaves a fixed
  ±0.9–1.7pp. It is excluded, like `when_leading` / `when_trailing`
  (FR-012): score-state metrics are only ever compared with themselves over
  time, or with other players'."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.domains.group.match_stats import ERROR_TYPES
from app.domains.member.player_dashboard import (
    DashboardResult,
    MatchSample,
    MetricResult,
    MetricValue,
    metric_specs,
)
from app.domains.member.player_identity import PlayerRef

InsightRule = Literal[
    "rate_vs_overall",
    "deuce_vs_even",
    "error_share_high",
    "winner_share_high",
    "recent_change",
    "partner_above_overall",
    "opponent_below_overall",
    "benchmark_quartile",
]
InsightBucket = Literal["strength", "weakness", "recent", "matchup"]
InsightLevel = Literal["strong", "mild"]
InsightSource = Literal["benchmark", "self", "trend", "matchup"]
InsightStatus = Literal["ok", "insufficient_data", "balanced"]
ParamValue = float | int | str | None

# --- thresholds (spec Assumptions; adjust here + the matching tests only) ---
RATE_GAP_MILD = 0.05
RATE_GAP_STRONG = 0.10
RATE_MIN_POINTS = 30
RATE_MIN_MATCHES = 3
ENDING_MIN_POINTS = 20
ERROR_SHARE_MILD = 0.60
ERROR_SHARE_STRONG = 0.70
WINNER_SHARE_MILD = 0.50
WINNER_SHARE_STRONG = 0.60
DOMINANT_ERROR_ABOVE = 0.50
RELATIVE_CHANGE_MILD = 0.15
RELATIVE_CHANGE_STRONG = 0.30

MAX_STRENGTHS = 3
MAX_WEAKNESSES = 3
MAX_RECENT = 2

# FR-011. Deliberately NOT here: when_leading, when_tied, when_trailing,
# match_point_conversion (FR-012) and match_points_saved (no direction).
RATE_VS_OVERALL_KEYS: tuple[str, ...] = (
    "team_serve",
    "team_receive",
    "own_serve",
    "own_receive",
    "endgame",
)
_SERVE_KEYS = frozenset({"team_serve", "own_serve"})
_RECEIVE_KEYS = frozenset({"team_receive", "own_receive"})
# FR-016: the two halves of a pair mirror each other around the baseline, so
# saying both would be saying one thing twice.
_PAIRS: tuple[tuple[str, str], ...] = (("team_serve", "team_receive"), ("own_serve", "own_receive"))
_DEUCE_BASELINE = 0.5

_LEVEL_ORDER: dict[InsightLevel, int] = {"strong": 0, "mild": 1}
_SOURCE_ORDER: dict[InsightSource, int] = {"benchmark": 0, "self": 1, "trend": 2, "matchup": 3}
_SPECS = {spec.key: spec for spec in metric_specs()}
_METRIC_ORDER = {spec.key: index for index, spec in enumerate(metric_specs())}


@dataclass(frozen=True)
class Insight:
    # `bucket`, not `list`: the JSON field is called "list" (contract), but a
    # dataclass field of that name would shadow the builtin below it.
    bucket: InsightBucket
    rule: InsightRule
    level: InsightLevel
    source: InsightSource
    metric_key: str | None
    player: PlayerRef | None
    params: dict[str, ParamValue]
    # Ordering only (FR-015) — compared within one source, never shown.
    sample_size: int = field(default=0, compare=False)


@dataclass(frozen=True)
class InsightsResult:
    status: InsightStatus
    strengths: list[Insight]
    weaknesses: list[Insight]
    recent: list[Insight]
    matchups: list[Insight]
    benchmark_group_name: str | None = None


def expected_rate(key: str, samples: Sequence[MatchSample]) -> float | None:
    """The rate this metric would show if the situation made no difference
    to me — see the module docstring for why each metric gets the baseline
    it does. Only matches that carry the metric's data take part, each
    weighted by how many of the metric's points it holds. None when there is
    nothing to weigh."""
    contribution = _SPECS[key].contribution
    expected = 0.0
    weight = 0
    won = played_total = 0
    for sample in samples:
        part = contribution(sample)
        played = sample.points_for + sample.points_against
        if part is None or part[1] == 0 or played < 2:
            continue
        if key in _SERVE_KEYS:
            rate = max(sample.points_for - 1, 0) / (played - 1)
        elif key in _RECEIVE_KEYS:
            rate = min(sample.points_for / (played - 1), 1.0)
        else:
            won += sample.points_for
            played_total += played
            continue
        expected += part[1] * rate
        weight += part[1]
    if key in _SERVE_KEYS or key in _RECEIVE_KEYS:
        return round(expected / weight, 4) if weight else None
    return round(won / played_total, 4) if played_total else None


def _level(gap: float, mild: float, strong: float) -> InsightLevel | None:
    if gap >= strong:
        return "strong"
    return "mild" if gap >= mild else None


def _value_params(value: MetricValue) -> dict[str, ParamValue]:
    return {
        "value": value.value,
        "numerator": value.numerator,
        "denominator": value.denominator,
        "matches_used": value.matches_used,
    }


def _rate_insights(
    metrics: dict[str, MetricResult], samples: Sequence[MatchSample]
) -> tuple[list[Insight], bool]:
    """→ (candidates, whether any rule had enough data to be judged at all)."""
    found: list[Insight] = []
    judged = False
    for key in (*RATE_VS_OVERALL_KEYS, "deuce"):
        metric = metrics.get(key)
        value = metric.all if metric is not None else None
        if (
            value is None
            or value.value is None
            or value.denominator < RATE_MIN_POINTS
            or value.matches_used < RATE_MIN_MATCHES
        ):
            continue
        baseline = _DEUCE_BASELINE if key == "deuce" else expected_rate(key, samples)
        if baseline is None:
            continue
        judged = True
        diff = round(value.value - baseline, 4)
        level = _level(abs(diff), RATE_GAP_MILD, RATE_GAP_STRONG)
        if level is None:
            continue
        found.append(
            Insight(
                bucket="strength" if diff > 0 else "weakness",
                rule="deuce_vs_even" if key == "deuce" else "rate_vs_overall",
                level=level,
                source="self",
                metric_key=key,
                player=None,
                params={**_value_params(value), "baseline": baseline, "diff": diff},
                sample_size=value.denominator,
            )
        )
    return _one_per_pair(found), judged


def _one_per_pair(found: list[Insight]) -> list[Insight]:
    dropped: set[str] = set()
    by_key = {insight.metric_key: insight for insight in found}
    for first, second in _PAIRS:
        a, b = by_key.get(first), by_key.get(second)
        if a is None or b is None:
            continue
        gap_a, gap_b = abs(_number(a.params["diff"])), abs(_number(b.params["diff"]))
        if gap_a != gap_b:
            loser = b if gap_a > gap_b else a
        else:
            loser = a if a.bucket == "strength" else b  # equal gaps: keep the weakness
        dropped.add(str(loser.metric_key))
    return [insight for insight in found if insight.metric_key not in dropped]


def _number(value: ParamValue) -> float:
    assert isinstance(value, int | float)
    return float(value)


def _ending_insights(
    metrics: dict[str, MetricResult], dashboard: DashboardResult
) -> tuple[list[Insight], bool]:
    found: list[Insight] = []
    judged = False

    errors = metrics.get("error_share_of_lost")
    value = errors.all if errors is not None else None
    if value is not None and value.value is not None and value.denominator >= ENDING_MIN_POINTS:
        judged = True
        level = _level(value.value, ERROR_SHARE_MILD, ERROR_SHARE_STRONG)
        if level is not None:
            dominant, share = _dominant_error(dashboard)
            found.append(
                Insight(
                    bucket="weakness",
                    rule="error_share_high",
                    level=level,
                    source="self",
                    metric_key="error_share_of_lost",
                    player=None,
                    params={
                        **_value_params(value),
                        "dominant_error": dominant,
                        "dominant_share": share,
                    },
                    sample_size=value.denominator,
                )
            )

    winners = metrics.get("winner_share")
    value = winners.all if winners is not None else None
    if value is not None and value.value is not None and value.denominator >= ENDING_MIN_POINTS:
        judged = True
        level = _level(value.value, WINNER_SHARE_MILD, WINNER_SHARE_STRONG)
        if level is not None:
            found.append(
                Insight(
                    bucket="strength",
                    rule="winner_share_high",
                    level=level,
                    source="self",
                    metric_key="winner_share",
                    player=None,
                    params=_value_params(value),
                    sample_size=value.denominator,
                )
            )
    return found, judged


def _dominant_error(dashboard: DashboardResult) -> tuple[str | None, float | None]:
    breakdown = dashboard.error_breakdown_all
    if breakdown is None:
        return None, None
    counts = breakdown.as_dict()
    total = sum(counts.values())
    if total == 0:
        return None, None
    kind = max(ERROR_TYPES, key=lambda name: counts[name])
    share = round(counts[kind] / total, 4)
    return (kind, share) if share > DOMINANT_ERROR_ABOVE else (None, None)


def _recent_insights(metrics: Sequence[MetricResult]) -> tuple[list[Insight], bool]:
    found: list[Insight] = []
    judged = False
    for metric in metrics:
        if metric.verdict is None or metric.verdict == "insufficient":
            continue
        judged = True
        if metric.verdict == "unchanged" or metric.all is None or metric.recent is None:
            continue
        overall, recent = metric.all.value, metric.recent.value
        if overall is None or recent is None:
            continue
        diff = round(recent - overall, 4)
        if metric.kind == "rate":
            level = _level(abs(diff), RATE_GAP_MILD, RATE_GAP_STRONG)
        elif overall == 0:
            level = None  # a relative change from nothing is not defined
        else:
            level = _level(abs(diff) / abs(overall), RELATIVE_CHANGE_MILD, RELATIVE_CHANGE_STRONG)
        if level is None:
            continue
        found.append(
            Insight(
                bucket="recent",
                rule="recent_change",
                level=level,
                source="trend",
                metric_key=metric.key,
                player=None,
                params={
                    "direction": metric.verdict,
                    "all_value": overall,
                    "recent_value": recent,
                    "diff": diff,
                    "recent_matches_used": metric.recent.matches_used,
                    "kind": metric.kind,
                },
                sample_size=metric.recent.matches_used,
            )
        )
    ranked = _ranked(found)
    top = ranked[:MAX_RECENT]
    # FR-014: bad news never crowds out the good news entirely.
    if len(top) == MAX_RECENT and all(i.params["direction"] == "declined" for i in top):
        improved = next((i for i in ranked if i.params["direction"] == "improved"), None)
        if improved is not None:
            top[-1] = improved
    return top, judged


def _ranked(found: list[Insight]) -> list[Insight]:
    """FR-015: strong first, then the more informative source, then the
    bigger sample (only ever compared within one source), then a fixed order
    so that the same data always yields the same list."""
    return sorted(
        found,
        key=lambda i: (
            _LEVEL_ORDER[i.level],
            _SOURCE_ORDER[i.source],
            -i.sample_size,
            _METRIC_ORDER.get(i.metric_key or "", len(_METRIC_ORDER)),
            i.player.key if i.player is not None else "",
        ),
    )


def derive(samples: Sequence[MatchSample], dashboard: DashboardResult) -> InsightsResult:
    metrics = {metric.key: metric for metric in dashboard.metrics}

    rate, rate_judged = _rate_insights(metrics, samples)
    endings, ending_judged = _ending_insights(metrics, dashboard)
    recent, recent_judged = _recent_insights(dashboard.metrics)

    contrasts = _ranked(rate + endings)
    strengths = [i for i in contrasts if i.bucket == "strength"][:MAX_STRENGTHS]
    weaknesses = [i for i in contrasts if i.bucket == "weakness"][:MAX_WEAKNESSES]

    status: InsightStatus
    if strengths or weaknesses or recent:
        status = "ok"
    elif rate_judged or ending_judged or recent_judged:
        status = "balanced"
    else:
        status = "insufficient_data"
    return InsightsResult(
        status=status, strengths=strengths, weaknesses=weaknesses, recent=recent, matchups=[]
    )
