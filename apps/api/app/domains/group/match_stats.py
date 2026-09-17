"""033-match-record-derived-stats: pure derivations over one completed
match's existing score/serve/placement history — serve & receive win rates,
momentum, per-point tempo, and per-player landing distribution.

Deliberately free of any ORM model or `AsyncSession` (research.md Decision
1): `build_match_record_detail()` does the querying and converts rows into
the plain inputs below, so every rule here is unit-testable without a
database."""

import uuid
from dataclasses import dataclass, field
from typing import Literal

Team = Literal["A", "B"]


@dataclass(frozen=True)
class RawEvent:
    """One `ScoreEvent` row. `score_a`/`score_b` are the totals RECORDED on
    the event (the live score right after it); `at_seconds` is the
    un-truncated offset from `Match.started_at`."""

    event_id: uuid.UUID
    side: Team
    delta: Literal[1, -1]
    score_a: int
    score_b: int
    at_seconds: float


@dataclass(frozen=True)
class ServeSnapshot:
    """One `ScoreServeRecord` row — the serve state AFTER its point was
    scored and any side-out applied (research.md Decision 3), i.e. the
    state the NEXT point is played under."""

    server_team: Team
    server_id: uuid.UUID
    team_a_right: uuid.UUID | None
    team_a_left: uuid.UUID | None
    team_b_right: uuid.UUID | None
    team_b_left: uuid.UUID | None


@dataclass(frozen=True)
class Placement:
    scorer_id: uuid.UUID | None
    loser_id: uuid.UUID | None
    landing: tuple[float, float] | None


@dataclass(frozen=True)
class Participant:
    roster_entry_id: uuid.UUID
    team: Team


@dataclass(frozen=True)
class EffectivePoint:
    """A +1 that still stands in the final score. `score_a`/`score_b` are
    RE-ACCUMULATED over the effective sequence (research.md Decision 2);
    `recorded_score_*` are what the event itself carried — the two differ
    only after an out-of-order correction. `gap_is_clean`: the raw event
    right before this one is itself an effective point (or this is the
    match's very first event), so the time since the previous effective
    point contains no correction (Decision 5)."""

    event_id: uuid.UUID
    side: Team
    score_a: int
    score_b: int
    recorded_score_a: int
    recorded_score_b: int
    at_seconds: float
    gap_is_clean: bool


@dataclass
class ServeCounts:
    serve_points_won: int = 0
    serve_points_total: int = 0
    receive_points_won: int = 0
    receive_points_total: int = 0


@dataclass(frozen=True)
class ServeStatsResult:
    teams: dict[Team, ServeCounts]
    # Insertion-ordered by the `participants` argument; empty for singles.
    players: dict[uuid.UUID, ServeCounts]
    excluded_points: int


@dataclass(frozen=True)
class ScoringRunResult:
    team: Team
    length: int
    start_score_a: int | None = None
    start_score_b: int | None = None
    end_score_a: int | None = None
    end_score_b: int | None = None


@dataclass(frozen=True)
class MaxLeadResult:
    team: Team
    margin: int
    score_a: int | None = None
    score_b: int | None = None


@dataclass(frozen=True)
class LeadChangeResult:
    new_leader: Team
    score_a: int
    score_b: int


@dataclass(frozen=True)
class MomentumResult:
    longest_runs: list[ScoringRunResult]
    max_leads: list[MaxLeadResult]
    lead_changes: list[LeadChangeResult]


@dataclass(frozen=True)
class TempoResult:
    average_seconds: float
    counted_points: int
    longest_seconds: float
    longest_score_a: int
    longest_score_b: int


@dataclass
class PlayerLandingResult:
    roster_entry_id: uuid.UUID
    team: Team
    scored: list[tuple[float, float]] = field(default_factory=list)
    scored_total: int = 0
    lost: list[tuple[float, float]] = field(default_factory=list)
    lost_total: int = 0


def effective_points(
    events: list[RawEvent], final_score_a: int, final_score_b: int
) -> list[EffectivePoint] | None:
    """research.md Decision 2. A `-1` voids that side's most recent
    not-yet-voided `+1` — the same "latest for this team" rule the write
    path's own correction already applies to shot placements. Returns None
    when the surviving points don't add up to the final score: every
    derived number would be built on a history that contradicts the result,
    so the caller reports "no data" instead."""
    voided: set[int] = set()
    standing: dict[Team, list[int]] = {"A": [], "B": []}
    for index, event in enumerate(events):
        if event.delta > 0:
            standing[event.side].append(index)
        elif standing[event.side]:
            voided.add(standing[event.side].pop())
        else:
            return None

    if len(standing["A"]) != final_score_a or len(standing["B"]) != final_score_b:
        return None

    def is_effective(index: int) -> bool:
        return events[index].delta > 0 and index not in voided

    points: list[EffectivePoint] = []
    score: dict[Team, int] = {"A": 0, "B": 0}
    for index, event in enumerate(events):
        if not is_effective(index):
            continue
        score[event.side] += 1
        points.append(
            EffectivePoint(
                event_id=event.event_id,
                side=event.side,
                score_a=score["A"],
                score_b=score["B"],
                recorded_score_a=event.score_a,
                recorded_score_b=event.score_b,
                at_seconds=event.at_seconds,
                gap_is_clean=index == 0 or is_effective(index - 1),
            )
        )
    return points


def _other(team: Team) -> Team:
    return "B" if team == "A" else "A"


def _receiver(
    snapshot: ServeSnapshot, receiving_team: Team, team_members: dict[Team, list[uuid.UUID]]
) -> uuid.UUID | None:
    """A serve goes diagonally, and each side's "right" court is diagonal
    to the other side's "right" — so the receiver is whoever the snapshot
    has in the receiving team's SAME-named court as the server. Singles
    stations each player by their own score parity, which can leave that
    court empty; the lone opponent is then the receiver regardless."""
    stations: dict[Team, tuple[uuid.UUID | None, uuid.UUID | None]] = {
        "A": (snapshot.team_a_right, snapshot.team_a_left),
        "B": (snapshot.team_b_right, snapshot.team_b_left),
    }
    serving_right, serving_left = stations[snapshot.server_team]
    receiving_right, receiving_left = stations[receiving_team]
    receiver: uuid.UUID | None = None
    if snapshot.server_id == serving_right:
        receiver = receiving_right
    elif snapshot.server_id == serving_left:
        receiver = receiving_left
    if receiver is None and len(team_members[receiving_team]) == 1:
        receiver = team_members[receiving_team][0]
    return receiver


def serve_stats(
    points: list[EffectivePoint],
    snapshots: dict[uuid.UUID, ServeSnapshot],
    participants: list[Participant],
) -> ServeStatsResult | None:
    """research.md Decision 3/4. A snapshot is written AFTER its point
    (side-out already applied), so it describes the NEXT point: point i is
    played under point i-1's snapshot. That snapshot is only trusted when
    the score it was taken at is the score point i actually starts from —
    one rule that drops the match's first point (no predecessor; the
    pre-match draw was never persisted), points right after an
    out-of-order correction, and points whose predecessor predates 030."""
    if not snapshots:
        return None

    team_members: dict[Team, list[uuid.UUID]] = {"A": [], "B": []}
    for participant in participants:
        team_members[participant.team].append(participant.roster_entry_id)
    is_doubles = any(len(members) > 1 for members in team_members.values())

    teams: dict[Team, ServeCounts] = {"A": ServeCounts(), "B": ServeCounts()}
    players: dict[uuid.UUID, ServeCounts] = (
        {p.roster_entry_id: ServeCounts() for p in participants} if is_doubles else {}
    )

    excluded = 0
    for index, point in enumerate(points):
        previous = points[index - 1] if index > 0 else None
        snapshot = snapshots.get(previous.event_id) if previous is not None else None
        if (
            previous is None
            or snapshot is None
            or (previous.recorded_score_a, previous.recorded_score_b)
            != (previous.score_a, previous.score_b)
        ):
            excluded += 1
            continue

        serving, receiving = snapshot.server_team, _other(snapshot.server_team)
        server_won = point.side == serving
        teams[serving].serve_points_total += 1
        teams[receiving].receive_points_total += 1
        if server_won:
            teams[serving].serve_points_won += 1
        else:
            teams[receiving].receive_points_won += 1

        server = players.get(snapshot.server_id)
        if server is not None:
            server.serve_points_total += 1
            server.serve_points_won += int(server_won)
        receiver_id = _receiver(snapshot, receiving, team_members)
        receiver = players.get(receiver_id) if receiver_id is not None else None
        if receiver is not None:
            receiver.receive_points_total += 1
            receiver.receive_points_won += int(not server_won)

    if excluded == len(points):
        return None
    return ServeStatsResult(teams=teams, players=players, excluded_points=excluded)


def momentum_stats(points: list[EffectivePoint]) -> MomentumResult:
    """research.md Decision 6."""
    best_run: dict[Team, ScoringRunResult] = {
        "A": ScoringRunResult("A", 0),
        "B": ScoringRunResult("B", 0),
    }
    best_lead: dict[Team, MaxLeadResult] = {"A": MaxLeadResult("A", 0), "B": MaxLeadResult("B", 0)}
    lead_changes: list[LeadChangeResult] = []

    run_start = 0
    last_leader: Team | None = None
    for index, point in enumerate(points):
        if index > 0 and points[index - 1].side != point.side:
            run_start = index
        length = index - run_start + 1
        # Strictly greater: of equally long runs, the earliest one stays.
        if length > best_run[point.side].length:
            before = points[run_start - 1] if run_start > 0 else None
            best_run[point.side] = ScoringRunResult(
                team=point.side,
                length=length,
                start_score_a=before.score_a if before else 0,
                start_score_b=before.score_b if before else 0,
                end_score_a=point.score_a,
                end_score_b=point.score_b,
            )

        if point.score_a == point.score_b:
            continue  # a tie neither leads nor resets who led last
        leader: Team = "A" if point.score_a > point.score_b else "B"
        margin = abs(point.score_a - point.score_b)
        if margin > best_lead[leader].margin:
            best_lead[leader] = MaxLeadResult(leader, margin, point.score_a, point.score_b)
        if last_leader is not None and leader != last_leader:
            lead_changes.append(LeadChangeResult(leader, point.score_a, point.score_b))
        last_leader = leader

    return MomentumResult(
        longest_runs=[best_run["A"], best_run["B"]],
        max_leads=[best_lead["A"], best_lead["B"]],
        lead_changes=lead_changes,
    )


def tempo_stats(points: list[EffectivePoint]) -> TempoResult | None:
    """research.md Decision 5. Only a rough pace estimate: each duration
    runs from the previous effective point (match start for the first) to
    the scorer's tap, breaks between rallies included. A gap that isn't
    clean also contains a correction being keyed in, so it is left out of
    both the average and the longest-point pick."""
    durations: list[tuple[float, EffectivePoint]] = []
    for index, point in enumerate(points):
        if not point.gap_is_clean:
            continue
        previous_at = points[index - 1].at_seconds if index > 0 else 0.0
        durations.append((point.at_seconds - previous_at, point))
    if not durations:
        return None

    # max() keeps the first of equal maxima — the earliest point.
    longest_seconds, longest_point = max(durations, key=lambda pair: pair[0])
    return TempoResult(
        average_seconds=round(sum(seconds for seconds, _ in durations) / len(durations), 1),
        counted_points=len(durations),
        longest_seconds=round(longest_seconds, 1),
        longest_score_a=longest_point.score_a,
        longest_score_b=longest_point.score_b,
    )


def landing_distribution(
    points: list[EffectivePoint],
    placements: dict[uuid.UUID, Placement],
    participants: list[Participant],
) -> list[PlayerLandingResult]:
    """research.md Decision 7. `*_total` counts every effective point the
    player was credited/charged with, plotted or not — the denominator that
    tells a viewer how much of the picture the plotted points cover. Empty
    when nobody ends up with a single plotted point, so the caller shows one
    "no landing data" notice rather than a court per player with nothing on
    it."""
    results = {
        p.roster_entry_id: PlayerLandingResult(p.roster_entry_id, p.team) for p in participants
    }
    for point in points:
        placement = placements.get(point.event_id)
        if placement is None:
            continue
        scorer = results.get(placement.scorer_id) if placement.scorer_id else None
        loser = results.get(placement.loser_id) if placement.loser_id else None
        if scorer is not None:
            scorer.scored_total += 1
            if placement.landing is not None:
                scorer.scored.append(placement.landing)
        if loser is not None:
            loser.lost_total += 1
            if placement.landing is not None:
                loser.lost.append(placement.landing)

    if not any(result.scored or result.lost for result in results.values()):
        return []
    return list(results.values())
