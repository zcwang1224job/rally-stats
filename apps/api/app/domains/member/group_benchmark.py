"""036-match-insights-benchmarks US3: where I stand among the people I play
with — for each dashboard metric, the group's average, how many players it
is an average of, and my rank. Pure functions, no ORM.

Anonymous by construction (FR-032, Clarifications 2026-09-18): every other
player's value comes IN as `PlayerValues` and nothing about them goes OUT —
`BenchmarkMetric` has no field that could carry a name, a key or an
individual number. The response schema mirrors it, so there is nothing for a
handler to forget to strip."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.domains.member.player_dashboard import (
    BetterWhen,
    MetricKind,
    MetricValue,
    metric_specs,
)

# A player counts toward a metric only with this many matches carrying its
# data in THIS group; an average needs this many such players to mean anything
# (and to not simply be one other person's number).
MIN_MATCHES_PER_PLAYER = 5
MIN_POOL = 3

BenchmarkStatus = Literal["ok", "pool_too_small", "self_below_minimum", "no_direction"]


@dataclass(frozen=True)
class PlayerValues:
    """One player's overall values in the group, keyed by metric. Input only."""

    player_key: str
    values: dict[str, MetricValue]


@dataclass(frozen=True)
class BenchmarkMetric:
    key: str
    kind: MetricKind
    better_when: BetterWhen | None
    mine: MetricValue | None  # None: I have no data for this metric in this group
    status: BenchmarkStatus
    group_average: float | None  # None iff pool_too_small
    pool_size: int  # eligible players; includes me only when I am eligible
    rank: int | None  # only when status is "ok"; ties share a rank (1224)
    # The same ranking read from the other end (two players tied for last are
    # both 1). For `insights` only — deliberately NOT in the response schema.
    rank_from_bottom: int | None


@dataclass(frozen=True)
class BenchmarkResult:
    metrics: list[BenchmarkMetric]  # all 23, in dashboard order


def _eligible(value: MetricValue | None) -> bool:
    return (
        value is not None
        and value.value is not None
        and value.matches_used >= MIN_MATCHES_PER_PLAYER
    )


def _competition_rank(mine: float, others: Sequence[float], *, best_is_high: bool) -> int:
    """Standard competition ranking ("1224"), the rule 018/019 use for the
    group standings: my rank is one more than the number of players strictly
    better than me."""
    better = sum(1 for other in others if (other > mine if best_is_high else other < mine))
    return better + 1


def build(me_key: str, players: Sequence[PlayerValues]) -> BenchmarkResult:
    mine_all = next((p.values for p in players if p.player_key == me_key), {})
    metrics: list[BenchmarkMetric] = []
    for spec in metric_specs():
        mine = mine_all.get(spec.key)
        pool: list[float] = []
        for player in players:
            value = player.values.get(spec.key)
            if value is not None and value.value is not None and _eligible(value):
                pool.append(value.value)
        average: float | None = None
        rank: int | None = None
        rank_from_bottom: int | None = None
        status: BenchmarkStatus
        if len(pool) < MIN_POOL:
            status = "pool_too_small"
        else:
            average = round(sum(pool) / len(pool), 4 if spec.kind == "rate" else 2)
            if spec.better_when is None:
                status = "no_direction"
            elif not _eligible(mine) or mine is None or mine.value is None:
                status = "self_below_minimum"
            else:
                status = "ok"
                high = spec.better_when == "higher"
                rank = _competition_rank(mine.value, pool, best_is_high=high)
                rank_from_bottom = _competition_rank(mine.value, pool, best_is_high=not high)
        metrics.append(
            BenchmarkMetric(
                key=spec.key,
                kind=spec.kind,
                better_when=spec.better_when,
                mine=mine,
                status=status,
                group_average=average,
                pool_size=len(pool),
                rank=rank,
                rank_from_bottom=rank_from_bottom,
            )
        )
    return BenchmarkResult(metrics=metrics)
