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
    ERROR_TYPES,
    ClutchResult,
    EndingStatsResult,
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
class EndingSample:
    """035-point-ending-type: my own split of a match's points — needs at
    least one of MY points (won or lost) to carry an ending (FR-020). The
    `*_unrecorded` buckets are deliberately absent: a rate's denominator
    only ever holds points whose ending was recorded."""

    winners: int
    opponent_errors: int
    beaten_by_winners: int
    own_errors: int
    own_errors_by_type: dict[str, int]


@dataclass(frozen=True)
class MatchSample:
    """Everything one match contributes. The final-score metrics are always
    available; the four optional blocks depend on what was recorded."""

    ended_at: datetime
    won: bool
    points_for: int
    points_against: int
    point_log: PointLogSample | None
    serve: ServeSample | None
    player: PlayerSample | None
    ending: EndingSample | None = None


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
class ErrorBreakdown:
    """035: my own errors by kind, summed over a range of matches."""

    out: int
    net: int
    serve_fault: int
    other_error: int

    def as_dict(self) -> dict[str, int]:
        return {kind: getattr(self, kind) for kind in ERROR_TYPES}


@dataclass(frozen=True)
class DashboardResult:
    total_matches: int
    recent_window: int
    has_comparison: bool
    metrics: list[MetricResult]
    trends: list[TrendSeries]
    landing: LandingResult | None
    # 035: None when not one of my errors was ever recorded; `recent` None
    # as well whenever there is no comparison (has_comparison False).
    error_breakdown_all: "ErrorBreakdown | None" = None
    error_breakdown_recent: "ErrorBreakdown | None" = None


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


def _from_ending(pick: Callable[[EndingSample], tuple[int, int]]) -> _Contribution:
    """035: a (numerator, denominator) pair read off the ending sample —
    used for rates and the ratio alike, so the denominator is whatever the
    metric says it is (recorded points, or own errors), never a match count."""
    return lambda s: pick(s.ending) if s.ending is not None else None


def _from_ending_per_match(pick: Callable[[EndingSample], int]) -> _Contribution:
    return _per_match(lambda s: pick(s.ending) if s.ending is not None else None)


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
    # 035-point-ending-type (data-model.md 新增指標): appended, never
    # reordered — the frontend's DASHBOARD_METRIC_KEYS is the same list. A
    # rate's denominator only holds points whose ending was recorded.
    _MetricSpec(
        "winner_share",
        "rate",
        "higher",
        _from_ending(lambda v: (v.winners, v.winners + v.opponent_errors)),
    ),
    _MetricSpec(
        "winners_per_match", "average", "higher", _from_ending_per_match(lambda v: v.winners)
    ),
    _MetricSpec(
        "errors_per_match", "average", "lower", _from_ending_per_match(lambda v: v.own_errors)
    ),
    _MetricSpec(
        "error_share_of_lost",
        "rate",
        "lower",
        _from_ending(lambda v: (v.own_errors, v.own_errors + v.beaten_by_winners)),
    ),
    _MetricSpec(
        "winner_error_ratio", "ratio", "higher", _from_ending(lambda v: (v.winners, v.own_errors))
    ),
)


def normalize_landing(x: float, y: float, my_team: Team) -> Landing:
    """research.md Decision 10. Stored coordinates are absolute — x runs
    from team A's baseline (0) to team B's (1) — so the same player's
    landings point opposite ways depending on which team they were on.
    Turning team B's court 180 degrees puts "my side" on the left for every
    match. It has to be a ROTATION: flipping x alone would mirror the court
    and swap my forehand side with my backhand side. Out-of-bounds values
    (the stored range is [-0.3, 1.3]) stay out of bounds, on the other
    side."""
    if my_team == "A":
        return (x, y)
    return (round(1 - x, 6), round(1 - y, 6))


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
    ending: EndingStatsResult | None,
) -> MatchSample:
    """One match, from the dashboard owner's side. Each of `clutch` / `serve`
    / `landings` / `ending` is None when the match has no usable data of
    that kind — the caller decides that with the same rules the match
    detail uses."""
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
        own_serve = serve.players.get(my_entry_id) if is_doubles else None
        serve_sample = ServeSample(
            team_serve=Ratio(team.serve_points_won, team.serve_points_total),
            team_receive=Ratio(team.receive_points_won, team.receive_points_total),
            own_serve=(
                Ratio(own_serve.serve_points_won, own_serve.serve_points_total)
                if own_serve
                else None
            ),
            own_receive=(
                Ratio(own_serve.receive_points_won, own_serve.receive_points_total)
                if own_serve
                else None
            ),
        )

    # "Players were recorded in this match" is a property of the match, not
    # of me: a match where only my partner got credited still counts, as 0.
    player: PlayerSample | None = None
    if landings is not None and any(r.scored_total + r.lost_total for r in landings.values()):
        own = landings.get(my_entry_id) or PlayerLandingResult(my_entry_id, my_team)
        player = PlayerSample(
            scored=own.scored_total,
            lost=own.lost_total,
            scored_landings=[normalize_landing(x, y, my_team) for x, y in own.scored],
            lost_landings=[normalize_landing(x, y, my_team) for x, y in own.lost],
        )

    # 035 FR-020: unlike the player block, this is about ME — a match where
    # only my partner's points carry an ending says nothing about mine.
    ending_sample: EndingSample | None = None
    if ending is not None:
        own_ending = ending.players.get(my_entry_id)
        if own_ending is not None and (
            own_ending.winners
            + own_ending.opponent_errors
            + own_ending.beaten_by_winners
            + own_ending.own_errors
        ):
            ending_sample = EndingSample(
                winners=own_ending.winners,
                opponent_errors=own_ending.opponent_errors,
                beaten_by_winners=own_ending.beaten_by_winners,
                own_errors=own_ending.own_errors,
                own_errors_by_type={
                    str(kind): count for kind, count in own_ending.own_errors_by_type.items()
                },
            )

    return MatchSample(
        ended_at=ended_at,
        won=won,
        points_for=points_for,
        points_against=points_against,
        point_log=point_log,
        serve=serve_sample,
        player=player,
        ending=ending_sample,
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


# Differences smaller than this are reported as "unchanged" rather than as
# progress or decline (research.md Decision 9): one percentage point for a
# rate, a tenth for anything counted per match.
_UNCHANGED_BELOW: dict[MetricKind, float] = {"rate": 0.01, "average": 0.1, "ratio": 0.1}


def _verdict(
    spec: _MetricSpec, overall: MetricValue | None, recent: MetricValue | None, min_recent: int
) -> Verdict | None:
    """Whether a bigger number is good news is a rule, not presentation
    (FR-026), so it is decided here once rather than in two page templates."""
    if overall is None or spec.better_when is None:
        return None
    if (
        recent is None
        or recent.matches_used < min_recent
        or recent.value is None
        or overall.value is None
    ):
        return "insufficient"
    difference = recent.value - overall.value
    if abs(difference) < _UNCHANGED_BELOW[spec.kind]:
        return "unchanged"
    return "improved" if (difference > 0) == (spec.better_when == "higher") else "declined"


def _trend(
    spec: _MetricSpec, samples_oldest_first: Sequence[MatchSample], window: int, cap: int
) -> TrendSeries | None:
    """research.md Decision 12: a moving window over the matches that HAVE
    this metric's data, summed the same way as the headline number. A single
    match's serve rate is ~20 points of noise; five matches' is a trend.
    None below two points — one dot is not a trend."""
    eligible = [
        (sample.ended_at, contribution)
        for sample in samples_oldest_first
        if (contribution := spec.contribution(sample)) is not None
    ]
    if len(eligible) <= window:
        return None
    points: list[TrendPoint] = []
    for end in range(window, len(eligible) + 1):
        chunk = eligible[end - window : end]
        numerator = sum(n for _, (n, _) in chunk)
        denominator = sum(d for _, (_, d) in chunk)
        points.append(
            TrendPoint(
                from_ended_at=chunk[0][0],
                to_ended_at=chunk[-1][0],
                value=round(numerator / denominator, 4) if denominator else None,
                numerator=numerator,
                denominator=denominator,
            )
        )
    return TrendSeries(spec.key, points[-cap:])


def _landing(
    samples_newest_first: Sequence[MatchSample], recent_window: int
) -> LandingResult | None:
    """research.md Decision 11. One newest-first array per kind plus the
    length of its recent prefix, instead of a second copy of the recent
    points. None when nothing was ever plotted, even if players were
    recorded — an empty court is not a picture."""
    scored: list[Landing] = []
    lost: list[Landing] = []
    totals = {"scored": 0, "lost": 0, "matches": 0}
    recent = {"scored_count": 0, "lost_count": 0, "scored": 0, "lost": 0, "matches": 0}
    for index, sample in enumerate(samples_newest_first):
        player = sample.player
        if player is None:
            continue
        scored.extend((round(x, 3), round(y, 3)) for x, y in player.scored_landings)
        lost.extend((round(x, 3), round(y, 3)) for x, y in player.lost_landings)
        totals["scored"] += player.scored
        totals["lost"] += player.lost
        totals["matches"] += 1
        if index < recent_window:
            recent["scored_count"] = len(scored)
            recent["lost_count"] = len(lost)
            recent["scored"] = totals["scored"]
            recent["lost"] = totals["lost"]
            recent["matches"] = totals["matches"]
    if not scored and not lost:
        return None
    return LandingResult(
        scored=scored,
        lost=lost,
        scored_total=totals["scored"],
        lost_total=totals["lost"],
        matches_used=totals["matches"],
        recent_scored_count=recent["scored_count"],
        recent_lost_count=recent["lost_count"],
        recent_scored_total=recent["scored"],
        recent_lost_total=recent["lost"],
        recent_matches_used=recent["matches"],
    )


def _error_breakdown(samples: Sequence[MatchSample]) -> ErrorBreakdown | None:
    """035: my own errors by kind over `samples`; None when there is not a
    single one — four zeros are not a breakdown."""
    counts = dict.fromkeys(ERROR_TYPES, 0)
    for sample in samples:
        if sample.ending is None:
            continue
        for kind in ERROR_TYPES:
            counts[kind] += sample.ending.own_errors_by_type.get(kind, 0)
    if not any(counts.values()):
        return None
    return ErrorBreakdown(
        out=counts["out"],
        net=counts["net"],
        serve_fault=counts["serve_fault"],
        other_error=counts["other_error"],
    )


def aggregate(
    samples_newest_first: Sequence[MatchSample],
    *,
    recent_window: int = 10,
    min_recent: int = 3,
    trend_window: int = 5,
    trend_cap: int = 60,
) -> DashboardResult:
    """`recent` is the newest `recent_window` matches of the whole (already
    filtered) set, each metric then taking whichever of those have its data
    (FR-025). With `recent_window` matches or fewer the two ranges are the
    same matches, so nothing is compared at all (FR-027)."""
    samples = samples_newest_first
    if not samples:
        return DashboardResult(0, recent_window, False, [], [], None)

    has_comparison = len(samples) > recent_window
    recent_samples = samples[:recent_window]
    oldest_first = list(reversed(samples))

    metrics: list[MetricResult] = []
    trends: list[TrendSeries] = []
    for spec in _METRICS:
        overall = _metric_value(spec, samples)
        recent = _metric_value(spec, recent_samples) if has_comparison else None
        metrics.append(
            MetricResult(
                key=spec.key,
                kind=spec.kind,
                better_when=spec.better_when,
                all=overall,
                recent=recent,
                verdict=_verdict(spec, overall, recent, min_recent) if has_comparison else None,
            )
        )
        series = _trend(spec, oldest_first, trend_window, trend_cap)
        if series is not None:
            trends.append(series)

    return DashboardResult(
        total_matches=len(samples),
        recent_window=recent_window,
        has_comparison=has_comparison,
        metrics=metrics,
        trends=trends,
        landing=_landing(samples, recent_window),
        error_breakdown_all=_error_breakdown(samples),
        error_breakdown_recent=_error_breakdown(recent_samples) if has_comparison else None,
    )
