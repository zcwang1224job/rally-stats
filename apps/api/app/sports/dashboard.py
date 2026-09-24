"""Building blocks for sport types' per-activity dashboards (spec 043
contracts/sections-manifest.md §2–§3). Core: sport-agnostic, used by
plugins; the plugin decides which metrics and sections an activity shows.

A metric is computed over a player's `DashboardRow`s. `metric_grid()` adds
the group average (FR-027): the mean of the same metric over every player of
the member's groups who has data for it, reported once at least
`MIN_PEERS` players do — below that an "average" would mostly be the member.
"""

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from app.sports.plugin import DashboardContext, DashboardRow
from app.sports.presentation import Section

MIN_PEERS = 3

MetricKind = Literal["rate", "average", "ratio", "count"]
Value = tuple[float | None, int | None, int | None]  # value, numerator, denominator


@dataclass(frozen=True)
class MetricDef:
    key: str
    label_key: str
    kind: MetricKind
    better_when: Literal["higher", "lower"] | None
    compute: Callable[[Sequence[DashboardRow]], Value]


def rate(numerator: int, denominator: int) -> Value:
    return (numerator / denominator if denominator else None, numerator, denominator)


def average(total: float, count: int) -> Value:
    return (total / count if count else None, None, None)


def count(value: int) -> Value:
    return (float(value), None, None)


def _wins(rows: Sequence[DashboardRow]) -> int:
    return sum(1 for row in rows if row.result == "win")


def _losses(rows: Sequence[DashboardRow]) -> int:
    return sum(1 for row in rows if row.result == "loss")


def _draws(rows: Sequence[DashboardRow]) -> int:
    return sum(1 for row in rows if row.result == "draw")


# Every sport type's dashboard starts from these (FR-023/FR-024).
MATCH_WIN_RATE = MetricDef(
    "match_win_rate",
    "sections.metric.match_win_rate",
    "rate",
    "higher",
    lambda rows: rate(_wins(rows), len(rows)),
)
MATCHES = MetricDef(
    "matches", "sections.metric.matches", "count", None, lambda rows: count(len(rows))
)
WINS = MetricDef("wins", "sections.metric.wins", "count", "higher", lambda rows: count(_wins(rows)))
LOSSES = MetricDef(
    "losses", "sections.metric.losses", "count", "lower", lambda rows: count(_losses(rows))
)
DRAWS = MetricDef("draws", "sections.metric.draws", "count", None, lambda rows: count(_draws(rows)))


def my_score(row: DashboardRow) -> int:
    return row.match.score_a if row.my_team == "A" else row.match.score_b


def their_score(row: DashboardRow) -> int:
    return row.match.score_b if row.my_team == "A" else row.match.score_a


def metric_grid(
    defs: Sequence[MetricDef], ctx: DashboardContext, *, title_key: str | None = None
) -> Section:
    metrics = []
    for spec in defs:
        value, numerator, denominator = spec.compute(ctx.mine)
        peer_values = [
            peer_value
            for rows in ctx.peers.values()
            if rows
            for peer_value in (spec.compute(rows)[0],)
            if peer_value is not None
        ]
        group_average = (
            sum(peer_values) / len(peer_values)
            if len(peer_values) >= MIN_PEERS and spec.kind != "count"
            else None
        )
        metrics.append(
            {
                "key": spec.key,
                "label_key": spec.label_key,
                "kind": spec.kind,
                "value": value,
                "numerator": numerator,
                "denominator": denominator,
                "better_when": spec.better_when,
                "group_average": group_average,
                "delta": (
                    value - group_average
                    if value is not None and group_average is not None
                    else None
                ),
            }
        )
    return Section(kind="metric_grid", title_key=title_key, data={"metrics": metrics})


def opponent_table(rows: Sequence[DashboardRow]) -> Section:
    """Head-to-head against each opponent, most-played first (FR-027)."""
    tally: dict[str, dict[str, int | str]] = defaultdict(
        lambda: {"name": "", "matches": 0, "wins": 0, "losses": 0, "draws": 0}
    )
    for row in rows:
        for key, name in zip(row.opponent_keys, row.opponent_names, strict=True):
            entry = tally[key]
            entry["name"] = name
            entry["matches"] = int(entry["matches"]) + 1
            outcome = {"win": "wins", "loss": "losses", "draw": "draws"}[row.result]
            entry[outcome] = int(entry[outcome]) + 1
    ordered = sorted(tally.items(), key=lambda item: (-int(item[1]["matches"]), item[0]))
    return Section(
        kind="stat_table",
        title_key="sections.opponents",
        data={
            "columns": [
                {"key": "name", "label_key": "sections.column.opponent"},
                {"key": "matches", "label_key": "sections.metric.matches"},
                {"key": "wins", "label_key": "sections.metric.wins"},
                {"key": "losses", "label_key": "sections.metric.losses"},
                {"key": "draws", "label_key": "sections.metric.draws"},
            ],
            "rows": [entry for _key, entry in ordered],
        },
    )


def empty_dashboard() -> list[Section]:
    return [Section(kind="text_note", data={"text_key": "playerDashboard.empty"})]
