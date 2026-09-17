"""034-clutch-points-player-dashboard: a member's cross-match technique
dashboard, as pure functions — no ORM model, no `AsyncSession`
(research.md Decision 8), so every rule here is unit-testable without a
database.

Two steps, deliberately separate:

- `build_sample()` turns ONE match's single-match derivations
  (`group.match_stats` results — the same ones the match detail dialog
  shows) into "my" point of view: my team's counts, my own serve/receive
  counts, my own landings with the court turned so my side is always on
  the left.
- `aggregate()` only sums, compares and windows those samples. It knows
  nothing about badminton: what makes a point an "endgame" point or a
  match point was already decided upstream.

Every metric is a numerator/denominator pair per match (`_MetricSpec`), so a
rate is always "sum of won / sum of played" across matches (FR-022) — never
an average of per-match percentages, which would let a 3-point endgame weigh
as much as a 12-point one."""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.domains.group.match_stats import (
    ClutchResult,
    PhaseCounts,
    PlayerLandingResult,
    ServeStatsResult,
    Team,
)

MetricKind = Literal["rate", "average", "ratio"]
BetterWhen = Literal["higher", "lower"]
Verdict = Literal["improved", "declined", "unchanged", "insufficient"]
Landing = tuple[float, float]


@dataclass(frozen=True)
class Ratio:
    won: int
    total: int


@dataclass(frozen=True)
class PointLogSample:
    """Needs a complete point log. `endgame` None: the match's target was
    too low for the phase to apply; `deuce` None: it never got there."""

    endgame: Ratio | None
    deuce: Ratio | None
    match_points_held: int
    match_point_converted: bool
    match_points_saved: int
    leading: Ratio
    tied: Ratio
    trailing: Ratio


@dataclass(frozen=True)
class ServeSample:
    """Needs serve records. `own_*` only exist in doubles — in singles they
    would just repeat the team numbers."""

    team_serve: Ratio
    team_receive: Ratio
    own_serve: Ratio | None
    own_receive: Ratio | None


@dataclass(frozen=True)
class PlayerSample:
    """Needs a match where the scorer recorded players at all. Landings are
    already normalized (`normalize_landing()`)."""

    scored: int
    lost: int
    scored_landings: list[Landing] = field(default_factory=list)
    lost_landings: list[Landing] = field(default_factory=list)


@dataclass(frozen=True)
class MatchSample:
    """Everything one match contributes. The final-score metrics are always
    available; the three optional blocks depend on what was recorded."""

    ended_at: datetime
    won: bool
    points_for: int
    points_against: int
    point_log: PointLogSample | None
    serve: ServeSample | None
    player: PlayerSample | None


@dataclass(frozen=True)
class MetricValue:
    """`value` None with `matches_used > 0`: the metric applies but its
    denominator is 0 (e.g. never trailed) — shown as "0/0 —"."""

    value: float | None
    numerator: int
    denominator: int
    matches_used: int


@dataclass(frozen=True)
class MetricResult:
    key: str
    kind: MetricKind
    better_when: BetterWhen | None
    all: MetricValue | None  # None: no match has the data this metric needs
    recent: MetricValue | None  # None: no comparison is shown
    verdict: Verdict | None


@dataclass(frozen=True)
class TrendPoint:
    from_ended_at: datetime
    to_ended_at: datetime
    value: float | None
    numerator: int
    denominator: int


@dataclass(frozen=True)
class TrendSeries:
    key: str
    points: list[TrendPoint]  # oldest first


@dataclass(frozen=True)
class LandingResult:
    """`scored`/`lost` are newest match first, so the recent window is a
    prefix: `scored[:recent_scored_count]` (research.md Decision 11)."""

    scored: list[Landing]
    lost: list[Landing]
    scored_total: int
    lost_total: int
    matches_used: int
    recent_scored_count: int
    recent_lost_count: int
    recent_scored_total: int
    recent_lost_total: int
    recent_matches_used: int


@dataclass(frozen=True)
class DashboardResult:
    total_matches: int
    recent_window: int
    has_comparison: bool
    metrics: list[MetricResult]
    trends: list[TrendSeries]
    landing: LandingResult | None


# (numerator, denominator) this match adds to a metric, or None when the
# match lacks what the metric needs and so doesn't count toward
# `matches_used`.
_Contribution = Callable[[MatchSample], tuple[int, int] | None]


@dataclass(frozen=True)
class _MetricSpec:
    key: str
    kind: MetricKind
    better_when: BetterWhen | None
    contribution: _Contribution


def _rate(pick: Callable[[MatchSample], Ratio | None]) -> _Contribution:
    def contribution(sample: MatchSample) -> tuple[int, int] | None:
        ratio = pick(sample)
        return (ratio.won, ratio.total) if ratio is not None else None

    return contribution


def _per_match(pick: Callable[[MatchSample], int | None]) -> _Contribution:
    """An average over matches: each eligible match adds its count to the
    numerator and 1 to the denominator."""

    def contribution(sample: MatchSample) -> tuple[int, int] | None:
        count = pick(sample)
        return (count, 1) if count is not None else None

    return contribution


def _conversion(sample: MatchSample) -> tuple[int, int] | None:
    log = sample.point_log
    if log is None or log.match_points_held == 0:
        return None
    return (int(log.match_point_converted), 1)


def _scored_lost(sample: MatchSample) -> tuple[int, int] | None:
    return (sample.player.scored, sample.player.lost) if sample.player is not None else None


def _from_serve(pick: Callable[[ServeSample], Ratio | None]) -> _Contribution:
    return _rate(lambda s: pick(s.serve) if s.serve is not None else None)


def _from_log(pick: Callable[[PointLogSample], Ratio | None]) -> _Contribution:
    return _rate(lambda s: pick(s.point_log) if s.point_log is not None else None)


def _from_player(pick: Callable[[PlayerSample], int]) -> _Contribution:
    return _per_match(lambda s: pick(s.player) if s.player is not None else None)


# The order here IS the order of `DashboardResult.metrics` (data-model.md
# 指標目錄) — the frontend groups by key but keeps this order within a group.
_METRICS: tuple[_MetricSpec, ...] = (
    _MetricSpec("team_serve", "rate", "higher", _from_serve(lambda v: v.team_serve)),
    _MetricSpec("team_receive", "rate", "higher", _from_serve(lambda v: v.team_receive)),
    _MetricSpec("own_serve", "rate", "higher", _from_serve(lambda v: v.own_serve)),
    _MetricSpec("own_receive", "rate", "higher", _from_serve(lambda v: v.own_receive)),
    _MetricSpec("points_scored", "average", "higher", _from_player(lambda v: v.scored)),
    _MetricSpec("points_lost", "average", "lower", _from_player(lambda v: v.lost)),
    _MetricSpec("scored_lost_ratio", "ratio", "higher", _scored_lost),
    _MetricSpec("endgame", "rate", "higher", _from_log(lambda v: v.endgame)),
    _MetricSpec("deuce", "rate", "higher", _from_log(lambda v: v.deuce)),
    _MetricSpec("match_point_conversion", "rate", "higher", _conversion),
    # No direction: saving many also means facing many (research.md
    # Decision 9). Per match, so that 10 matches compare with 300.
    _MetricSpec(
        "match_points_saved",
        "average",
        None,
        _per_match(
            lambda s: s.point_log.match_points_saved if s.point_log is not None else None
        ),
    ),
    _MetricSpec("when_leading", "rate", "higher", _from_log(lambda v: v.leading)),
    _MetricSpec("when_tied", "rate", "higher", _from_log(lambda v: v.tied)),
    _MetricSpec("when_trailing", "rate", "higher", _from_log(lambda v: v.trailing)),
    _MetricSpec("avg_points_for", "average", "higher", _per_match(lambda s: s.points_for)),
    _MetricSpec("avg_points_against", "average", "lower", _per_match(lambda s: s.points_against)),
    _MetricSpec(
        "avg_win_margin",
        "average",
        "higher",
        _per_match(lambda s: s.points_for - s.points_against if s.won else None),
    ),
    _MetricSpec(
        "avg_loss_margin",
        "average",
        "lower",
        _per_match(lambda s: s.points_against - s.points_for if not s.won else None),
    ),
)


def normalize_landing(x: float, y: float, my_team: Team) -> Landing:
    """research.md Decision 10."""
    raise NotImplementedError


def _ratio(counts: PhaseCounts | None) -> Ratio | None:
    return Ratio(counts.won, counts.total) if counts is not None else None


def build_sample(
    *,
    ended_at: datetime,
    won: bool,
    points_for: int,
    points_against: int,
    my_team: Team,
    my_entry_id: uuid.UUID,
    is_doubles: bool,
    clutch: ClutchResult | None,
    serve: ServeStatsResult | None,
    landings: dict[uuid.UUID, PlayerLandingResult] | None,
) -> MatchSample:
    """One match, from the dashboard owner's side. Each of `clutch` / `serve`
    / `landings` is None when the match has no usable data of that kind —
    the caller decides that with the same rules the match detail uses."""
    point_log: PointLogSample | None = None
    if clutch is not None:
        mine = clutch.match_points[my_team]
        state = clutch.by_state[my_team]
        point_log = PointLogSample(
            endgame=_ratio(clutch.endgame[my_team]) if clutch.endgame is not None else None,
            deuce=_ratio(clutch.deuce[my_team]) if clutch.deuce is not None else None,
            match_points_held=mine.held,
            match_point_converted=mine.converted_on is not None,
            match_points_saved=mine.saved,
            leading=Ratio(state.leading.won, state.leading.total),
            tied=Ratio(state.tied.won, state.tied.total),
            trailing=Ratio(state.trailing.won, state.trailing.total),
        )

    serve_sample: ServeSample | None = None
    if serve is not None:
        team = serve.teams[my_team]
        own = serve.players.get(my_entry_id) if is_doubles else None
        serve_sample = ServeSample(
            team_serve=Ratio(team.serve_points_won, team.serve_points_total),
            team_receive=Ratio(team.receive_points_won, team.receive_points_total),
            own_serve=Ratio(own.serve_points_won, own.serve_points_total) if own else None,
            own_receive=Ratio(own.receive_points_won, own.receive_points_total) if own else None,
        )

    # "Players were recorded in this match" is a property of the match, not
    # of me: a match where only my partner got credited still counts, as 0.
    player: PlayerSample | None = None
    if landings is not None and any(r.scored_total + r.lost_total for r in landings.values()):
        my_landings = landings.get(my_entry_id)
        player = PlayerSample(
            scored=my_landings.scored_total if my_landings else 0,
            lost=my_landings.lost_total if my_landings else 0,
        )

    return MatchSample(
        ended_at=ended_at,
        won=won,
        points_for=points_for,
        points_against=points_against,
        point_log=point_log,
        serve=serve_sample,
        player=player,
    )


def _metric_value(spec: _MetricSpec, samples: Sequence[MatchSample]) -> MetricValue | None:
    contributions = [c for c in map(spec.contribution, samples) if c is not None]
    if not contributions:
        return None
    numerator = sum(n for n, _ in contributions)
    denominator = sum(d for _, d in contributions)
    return MetricValue(
        value=round(numerator / denominator, 4) if denominator else None,
        numerator=numerator,
        denominator=denominator,
        matches_used=len(contributions),
    )


def aggregate(
    samples_newest_first: Sequence[MatchSample],
    *,
    recent_window: int = 10,
    min_recent: int = 3,
    trend_window: int = 5,
    trend_cap: int = 60,
) -> DashboardResult:
    samples = samples_newest_first
    has_comparison = len(samples) > recent_window
    if not samples:
        return DashboardResult(0, recent_window, False, [], [], None)

    metrics = [
        MetricResult(
            key=spec.key,
            kind=spec.kind,
            better_when=spec.better_when,
            all=_metric_value(spec, samples),
            recent=None,
            verdict=None,
        )
        for spec in _METRICS
    ]
    return DashboardResult(
        total_matches=len(samples),
        recent_window=recent_window,
        has_comparison=has_comparison,
        metrics=metrics,
        trends=[],
        landing=None,
    )
