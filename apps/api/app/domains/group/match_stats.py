"""033-match-record-derived-stats: pure derivations over one completed
match's existing score/serve/placement history — serve & receive win rates,
momentum, per-point tempo, and per-player landing distribution.
034-clutch-points-player-dashboard adds clutch-point performance
(`clutch_stats()`), which also needs the match's own rule snapshot.

Deliberately free of any ORM model or `AsyncSession` (research.md Decision
1): `build_match_record_detail()` does the querying and converts rows into
the plain inputs below, so every rule here is unit-testable without a
database."""

import uuid
from dataclasses import dataclass, field
from typing import Literal

Team = Literal["A", "B"]
# 035-point-ending-type: how a rally ended. A deliberate copy of
# `schedule.schemas.EndingType` — this module imports nothing from the ORM
# side — pinned to the original by test_match_stats.py.
EndingType = Literal["winner", "out", "net", "serve_fault", "other_error"]
# Everything but a winner is the LOSER's doing.
ERROR_TYPES: tuple[EndingType, ...] = ("out", "net", "serve_fault", "other_error")


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
    # 035: None = not recorded (every point scored before 035 included).
    ending: EndingType | None = None


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


@dataclass(frozen=True)
class PhaseCounts:
    """One team's points won out of the points played in some phase or
    score state."""

    won: int
    total: int


@dataclass(frozen=True)
class MatchPointResult:
    """`converted_on`: which of this team's match points (1-based) ended the
    match — None for the loser. `saved`: opponent match points this team
    survived."""

    held: int
    converted_on: int | None
    saved: int


@dataclass(frozen=True)
class StateCounts:
    """Grouped by the score BEFORE each point was played."""

    leading: PhaseCounts
    tied: PhaseCounts
    trailing: PhaseCounts


@dataclass(frozen=True)
class ClutchResult:
    """`endgame_from`/`endgame` are None when the target is too low for an
    "endgame" to mean anything; `deuce` is None when the match never got
    there."""

    endgame_from: int | None
    endgame: dict[Team, PhaseCounts] | None
    deuce: dict[Team, PhaseCounts] | None
    match_points: dict[Team, MatchPointResult]
    by_state: dict[Team, StateCounts]


@dataclass
class PlayerLandingResult:
    roster_entry_id: uuid.UUID
    team: Team
    scored: list[tuple[float, float]] = field(default_factory=list)
    scored_total: int = 0
    lost: list[tuple[float, float]] = field(default_factory=list)
    lost_total: int = 0


@dataclass(frozen=True)
class TeamEndingResult:
    """035. `errors` are the ones THIS team committed — i.e. points the
    other team was credited with by an error — so a team's own line reads
    "we hit N winners and gave away M"."""

    team: Team
    winners: int
    errors: int
    errors_by_type: dict[EndingType, int]


@dataclass(frozen=True)
class PlayerEndingResult:
    """035. Points scored split three ways (winners / opponent errors /
    ending not recorded) and points lost likewise (beaten by a winner / own
    errors / not recorded), so each triple adds up to the player's
    `PlayerLandingResult.*_total` (FR-015)."""

    roster_entry_id: uuid.UUID
    team: Team
    winners: int
    opponent_errors: int
    scored_unrecorded: int
    beaten_by_winners: int
    own_errors: int
    lost_unrecorded: int
    own_errors_by_type: dict[EndingType, int]


@dataclass(frozen=True)
class EndingStatsResult:
    """`recorded_points`: effective points whose ending was recorded;
    `total_points`: every effective point, so a viewer can see how much of
    the match the numbers cover. `players` is insertion-ordered by
    `participants` and includes every one of them, all-zero rows too."""

    recorded_points: int
    total_points: int
    teams: dict[Team, TeamEndingResult]
    players: dict[uuid.UUID, PlayerEndingResult]


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


def _wins(score_x: int, score_y: int, target_score: int, cap_score: int) -> bool:
    """034 research.md Decision 2: the write path's win rule
    (`schedule.service.match_wins()`), restated because that module drags in
    the ORM and realtime publishing. test_match_stats.py pins the two
    together over a grid so they cannot drift apart."""
    return score_x >= cap_score or (score_x >= target_score and score_x - score_y >= 2)


# Below this target an "endgame" of the last three points would swallow half
# the match or more, so the phase is reported as not applicable (FR-010).
_ENDGAME_MIN_TARGET = 11
_ENDGAME_WINDOW = 3


def clutch_stats(
    points: list[EffectivePoint], target_score: int, cap_score: int
) -> ClutchResult:
    """034 research.md Decision 1-3. Every phase is judged by the score a
    point STARTS from — the previous effective point's re-accumulated score,
    0:0 for the first. `target_score`/`cap_score` are the match's own rule
    snapshot, so matches under different rules can be aggregated later
    without any of them borrowing another's thresholds. A completed match
    can only end on a converted match point (anything cut short is
    `abandoned` and never gets here), so the winner always has
    `converted_on == held`."""
    endgame_from = (
        target_score - _ENDGAME_WINDOW if target_score >= _ENDGAME_MIN_TARGET else None
    )
    teams: tuple[Team, Team] = ("A", "B")
    # [won, total] per team
    endgame: dict[Team, list[int]] = {team: [0, 0] for team in teams}
    deuce: dict[Team, list[int]] = {team: [0, 0] for team in teams}
    state: dict[Team, dict[str, list[int]]] = {
        team: {"leading": [0, 0], "tied": [0, 0], "trailing": [0, 0]} for team in teams
    }
    held: dict[Team, int] = {"A": 0, "B": 0}
    converted_on: dict[Team, int | None] = {"A": None, "B": None}

    before: dict[Team, int] = {"A": 0, "B": 0}
    for point in points:
        in_endgame = endgame_from is not None and max(before.values()) >= endgame_from
        in_deuce = min(before.values()) >= target_score - 1
        for team in teams:
            mine, theirs = before[team], before[_other(team)]
            won = int(point.side == team)
            key = "leading" if mine > theirs else "trailing" if mine < theirs else "tied"
            for applies, tally in (
                (True, state[team][key]),
                (in_endgame, endgame[team]),
                (in_deuce, deuce[team]),
            ):
                if applies:
                    tally[0] += won
                    tally[1] += 1
            if _wins(mine + 1, theirs, target_score, cap_score):
                held[team] += 1
                if won:
                    converted_on[team] = held[team]
        before = {"A": point.score_a, "B": point.score_b}

    def _phase(tallies: dict[Team, list[int]]) -> dict[Team, PhaseCounts] | None:
        if tallies["A"][1] == 0:
            return None
        return {team: PhaseCounts(*tallies[team]) for team in teams}

    return ClutchResult(
        endgame_from=endgame_from,
        endgame=_phase(endgame) if endgame_from is not None else None,
        deuce=_phase(deuce),
        match_points={
            team: MatchPointResult(
                held=held[team],
                converted_on=converted_on[team],
                saved=held[_other(team)] - int(converted_on[_other(team)] is not None),
            )
            for team in teams
        },
        by_state={
            team: StateCounts(
                leading=PhaseCounts(*state[team]["leading"]),
                tied=PhaseCounts(*state[team]["tied"]),
                trailing=PhaseCounts(*state[team]["trailing"]),
            )
            for team in teams
        },
    )


def player_landings(
    points: list[EffectivePoint],
    placements: dict[uuid.UUID, Placement],
    participants: list[Participant],
) -> dict[uuid.UUID, PlayerLandingResult]:
    """Every participant's full result, insertion-ordered by `participants`.
    `*_total` counts every effective point the player was credited/charged
    with, plotted or not. 034's cross-match dashboard reads the totals even
    from a match where nobody plotted a single landing, which is why this
    has no "empty" rule of its own — see `landing_distribution()`."""
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
    return results


def landing_distribution(
    points: list[EffectivePoint],
    placements: dict[uuid.UUID, Placement],
    participants: list[Participant],
) -> list[PlayerLandingResult]:
    """research.md Decision 7. `*_total` is the denominator that tells a
    viewer how much of the picture the plotted points cover. Empty when
    nobody ends up with a single plotted point, so the caller shows one
    "no landing data" notice rather than a court per player with nothing on
    it."""
    results = player_landings(points, placements, participants)
    if not any(result.scored or result.lost for result in results.values()):
        return []
    return list(results.values())


def ending_stats(
    points: list[EffectivePoint],
    placements: dict[uuid.UUID, Placement],
    participants: list[Participant],
) -> EndingStatsResult | None:
    """035 research.md Decision 5. Who a point is attributed to follows the
    row's own players (FR-003): a winner is the scorer's, an error is the
    loser's — and where that player wasn't recorded, the point still counts
    for its TEAM (the effective point's side, which is fixed) but for no
    individual. A row whose ending is None, or no row at all, is "not
    recorded" and lands in the `*_unrecorded` buckets so each player's
    triple keeps adding up to their `player_landings()` totals (FR-015).
    None when not a single point recorded an ending — the caller shows one
    "no data" notice instead of a table of zeros (FR-017)."""
    team_winners: dict[Team, int] = {"A": 0, "B": 0}
    team_errors: dict[Team, dict[EndingType, int]] = {
        "A": dict.fromkeys(ERROR_TYPES, 0),
        "B": dict.fromkeys(ERROR_TYPES, 0),
    }
    # Per player: [winners, opponent_errors, scored_unrecorded,
    #              beaten_by_winners, own_errors, lost_unrecorded]
    tallies: dict[uuid.UUID, list[int]] = {p.roster_entry_id: [0] * 6 for p in participants}
    own_errors_by_type: dict[uuid.UUID, dict[EndingType, int]] = {
        p.roster_entry_id: dict.fromkeys(ERROR_TYPES, 0) for p in participants
    }
    recorded = 0

    for point in points:
        placement = placements.get(point.event_id)
        ending = placement.ending if placement is not None else None
        scorer = tallies.get(placement.scorer_id) if placement and placement.scorer_id else None
        loser = tallies.get(placement.loser_id) if placement and placement.loser_id else None
        if ending is None:
            if scorer is not None:
                scorer[2] += 1
            if loser is not None:
                loser[5] += 1
            continue

        recorded += 1
        if ending == "winner":
            team_winners[point.side] += 1
            if scorer is not None:
                scorer[0] += 1
            if loser is not None:
                loser[3] += 1
        else:
            team_errors[_other(point.side)][ending] += 1
            if scorer is not None:
                scorer[1] += 1
            if loser is not None and placement is not None and placement.loser_id is not None:
                loser[4] += 1
                own_errors_by_type[placement.loser_id][ending] += 1

    if recorded == 0:
        return None
    teams: tuple[Team, Team] = ("A", "B")
    return EndingStatsResult(
        recorded_points=recorded,
        total_points=len(points),
        teams={
            team: TeamEndingResult(
                team=team,
                winners=team_winners[team],
                errors=sum(team_errors[team].values()),
                errors_by_type=team_errors[team],
            )
            for team in teams
        },
        players={
            p.roster_entry_id: PlayerEndingResult(
                roster_entry_id=p.roster_entry_id,
                team=p.team,
                winners=tallies[p.roster_entry_id][0],
                opponent_errors=tallies[p.roster_entry_id][1],
                scored_unrecorded=tallies[p.roster_entry_id][2],
                beaten_by_winners=tallies[p.roster_entry_id][3],
                own_errors=tallies[p.roster_entry_id][4],
                lost_unrecorded=tallies[p.roster_entry_id][5],
                own_errors_by_type=own_errors_by_type[p.roster_entry_id],
            )
            for p in participants
        },
    )
