"""Net rally match detail and stat inputs (016/032/033/034/035), moved here
from group/service.py by spec 043 (research Decisions 9/12): everything that
reads this plugin's own tables — serve snapshots and shot placements — or
builds the net-rally-only blocks of MatchRecordDetailResponse. The pure rules
stay in `app.domains.group.match_stats`.
"""

import dataclasses
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group import match_stats
from app.domains.group.schemas import (
    ClutchComeback,
    ClutchMatchPoints,
    ClutchPhaseCounts,
    ClutchStateCounts,
    ClutchStats,
    EndingStats,
    ErrorsByType,
    LandingPoint,
    LeadChange,
    LongestPoint,
    MatchRecordSummary,
    MaxLead,
    MomentumStats,
    PlayerEndingStat,
    PlayerLandingDistribution,
    PlayerScoringStat,
    PlayerServeStat,
    ScoringRun,
    ServeStats,
    ShotPlacementSummary,
    TeamEndingStat,
    TeamServeStat,
    TempoStats,
)
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, ScoreServeRecord, ShotPlacementRecord
from app.sports.plugin import MatchDetailContext, MatchDetailParts, StatExtras
from app.sports.presentation import Section

_STAT_INPUT_BATCH = 500


def _to_serve_snapshots(
    records: Iterable[ScoreServeRecord],
) -> dict[uuid.UUID, match_stats.ServeSnapshot]:
    return {
        record.score_event_id: match_stats.ServeSnapshot(
            server_team=record.server_team,  # type: ignore[arg-type]
            server_id=record.server_roster_entry_id,
            team_a_right=record.team_a_right_roster_entry_id,
            team_a_left=record.team_a_left_roster_entry_id,
            team_b_right=record.team_b_right_roster_entry_id,
            team_b_left=record.team_b_left_roster_entry_id,
        )
        for record in records
    }


def _to_placements(
    placements: Iterable[ShotPlacementRecord],
) -> dict[uuid.UUID, match_stats.Placement]:
    return {
        placement.score_event_id: match_stats.Placement(
            scorer_id=placement.roster_entry_id,
            loser_id=placement.losing_roster_entry_id,
            landing=(
                (placement.landing_x, placement.landing_y)
                if placement.landing_x is not None and placement.landing_y is not None
                else None
            ),
            ending=placement.ending_type,  # type: ignore[arg-type]
        )
        for placement in placements
    }


async def load_stat_extras(
    session: AsyncSession, matches: Sequence[Match]
) -> dict[uuid.UUID, StatExtras]:
    """034 research.md Decision 7: two queries per batch of 500 matches
    however many there are (the spine's third query is core's). Every
    requested match gets an entry."""
    serve_by_match: dict[uuid.UUID, list[ScoreServeRecord]] = defaultdict(list)
    placements_by_match: dict[uuid.UUID, list[ShotPlacementRecord]] = defaultdict(list)
    match_ids = [match.id for match in matches]
    for offset in range(0, len(match_ids), _STAT_INPUT_BATCH):
        batch = match_ids[offset : offset + _STAT_INPUT_BATCH]
        serve_result = await session.execute(
            select(ScoreServeRecord).where(ScoreServeRecord.match_id.in_(batch))
        )
        for record in serve_result.scalars():
            serve_by_match[record.match_id].append(record)
        placements_result = await session.execute(
            select(ShotPlacementRecord).where(ShotPlacementRecord.match_id.in_(batch))
        )
        for placement in placements_result.scalars():
            placements_by_match[placement.match_id].append(placement)
    return {
        match_id: StatExtras(
            snapshots=_to_serve_snapshots(serve_by_match[match_id]),
            placements=_to_placements(placements_by_match[match_id]),
        )
        for match_id in match_ids
    }


def _clutch_stats_schema(
    clutch: match_stats.ClutchResult,
    momentum: match_stats.MomentumResult,
    winner: Literal["A", "B"],
) -> ClutchStats:
    """`comeback` is read off 033's `max_leads` rather than recomputed: the
    winner's deepest deficit IS the loser's biggest lead, so the two blocks
    cannot disagree (034 research.md Decision 4)."""
    teams: tuple[match_stats.Team, match_stats.Team] = ("A", "B")

    def _phase(
        counts: dict[match_stats.Team, match_stats.PhaseCounts] | None,
    ) -> list[ClutchPhaseCounts] | None:
        if counts is None:
            return None
        return [
            ClutchPhaseCounts(team=team, **dataclasses.asdict(counts[team])) for team in teams
        ]

    loser_lead = next(lead for lead in momentum.max_leads if lead.team != winner)
    comeback = (
        ClutchComeback(
            winner=winner,
            max_deficit=loser_lead.margin,
            score_a=loser_lead.score_a,
            score_b=loser_lead.score_b,
        )
        if loser_lead.margin > 0
        and loser_lead.score_a is not None
        and loser_lead.score_b is not None
        else None
    )
    return ClutchStats(
        endgame_from=clutch.endgame_from,
        endgame=_phase(clutch.endgame),
        deuce=_phase(clutch.deuce),
        match_points=[
            ClutchMatchPoints(team=team, **dataclasses.asdict(clutch.match_points[team]))
            for team in teams
        ],
        by_state=[
            ClutchStateCounts(team=team, **dataclasses.asdict(clutch.by_state[team]))
            for team in teams
        ],
        comeback=comeback,
    )


async def _build_derived_stats(
    session: AsyncSession,
    ctx: MatchDetailContext,
    placements: list[ShotPlacementRecord],
    parts: dict[str, object],
) -> None:
    """033-match-record-derived-stats: the querying/conversion half of the
    derived blocks — every actual rule lives in `match_stats` (pure, no
    session). Only called for a `"complete"` record: a partial history has
    no trustworthy starting score to re-accumulate from. Reads
    `ScoreServeRecord` (written since 030); `placements` is 032's existing
    query result, reused rather than re-queried. Fills `parts`."""
    match = ctx.match
    summary: MatchRecordSummary = ctx.summary
    points = match_stats.effective_points(list(ctx.raw_events), match.score_a, match.score_b)
    if points is None:
        return

    participants = summary.team_a + summary.team_b
    nickname_by_id = {uuid.UUID(p.roster_entry_id): p.nickname for p in participants}
    stat_participants = [
        match_stats.Participant(uuid.UUID(p.roster_entry_id), p.team) for p in participants
    ]

    serve_result = await session.execute(
        select(ScoreServeRecord).where(ScoreServeRecord.match_id == match.id)
    )
    serve = match_stats.serve_stats(
        points, _to_serve_snapshots(serve_result.scalars()), stat_participants
    )
    parts["serve_stats"] = (
        ServeStats(
            teams=[
                TeamServeStat(team=team, **dataclasses.asdict(counts))
                for team, counts in serve.teams.items()  # built in A, B order
            ],
            players=[
                PlayerServeStat(
                    roster_entry_id=p.roster_entry_id,
                    nickname=p.nickname,
                    team=p.team,
                    **dataclasses.asdict(serve.players[uuid.UUID(p.roster_entry_id)]),
                )
                for p in participants
                if uuid.UUID(p.roster_entry_id) in serve.players
            ],
            excluded_points=serve.excluded_points,
        )
        if serve is not None
        else None
    )

    momentum = match_stats.momentum_stats(points)
    parts["momentum_stats"] = MomentumStats(
        longest_runs=[ScoringRun(**dataclasses.asdict(run)) for run in momentum.longest_runs],
        max_leads=[MaxLead(**dataclasses.asdict(lead)) for lead in momentum.max_leads],
        lead_changes=[
            LeadChange(**dataclasses.asdict(change)) for change in momentum.lead_changes
        ],
    )

    tempo = match_stats.tempo_stats(points)
    parts["tempo_stats"] = (
        TempoStats(
            average_seconds=tempo.average_seconds,
            counted_points=tempo.counted_points,
            longest=LongestPoint(
                seconds=tempo.longest_seconds,
                score_a=tempo.longest_score_a,
                score_b=tempo.longest_score_b,
            ),
        )
        if tempo is not None
        else None
    )

    stat_placements = _to_placements(placements)
    parts["landing_distribution"] = [
        PlayerLandingDistribution(
            roster_entry_id=str(player.roster_entry_id),
            nickname=nickname_by_id[player.roster_entry_id],
            team=player.team,
            scored=[LandingPoint(x=x, y=y) for x, y in player.scored],
            scored_total=player.scored_total,
            lost=[LandingPoint(x=x, y=y) for x, y in player.lost],
            lost_total=player.lost_total,
        )
        for player in match_stats.landing_distribution(
            points, stat_placements, stat_participants
        )
    ]

    assert match.winner_team is not None  # always set for completed matches
    parts["clutch_stats"] = _clutch_stats_schema(
        match_stats.clutch_stats(points, match.target_score, match.cap_score, match.win_by),
        momentum,
        match.winner_team,  # type: ignore[arg-type]
    )

    # 035-point-ending-type: None when not one point recorded an ending
    # (the pure function's own rule), so a pre-035 match shows the single
    # "no data" notice rather than a table of zeros.
    ending = match_stats.ending_stats(points, stat_placements, stat_participants)
    parts["ending_stats"] = (
        EndingStats(
            recorded_points=ending.recorded_points,
            total_points=ending.total_points,
            teams=[
                TeamEndingStat(
                    team=team.team,
                    winners=team.winners,
                    errors=team.errors,
                    errors_by_type=ErrorsByType(
                        out=team.errors_by_type["out"],
                        net=team.errors_by_type["net"],
                        serve_fault=team.errors_by_type["serve_fault"],
                        other_error=team.errors_by_type["other_error"],
                    ),
                )
                for team in ending.teams.values()  # built in A, B order
            ],
            players=[
                PlayerEndingStat(
                    roster_entry_id=p.roster_entry_id,
                    nickname=p.nickname,
                    team=p.team,
                    winners=split.winners,
                    opponent_errors=split.opponent_errors,
                    scored_unrecorded=split.scored_unrecorded,
                    beaten_by_winners=split.beaten_by_winners,
                    own_errors=split.own_errors,
                    lost_unrecorded=split.lost_unrecorded,
                )
                for p in participants
                for split in (ending.players[uuid.UUID(p.roster_entry_id)],)
            ],
        )
        if ending is not None
        else None
    )


async def match_detail(session: AsyncSession, ctx: MatchDetailContext) -> MatchDetailParts:
    """016/032/033/034/035's net-rally blocks of the match detail page."""
    match = ctx.match
    summary: MatchRecordSummary = ctx.summary

    # 032-match-record-scoring-stats: one query for every ShotPlacementRecord
    # this match ever wrote (031/032-shot-placement-scoring), reused below
    # both to attach each event's own `detail` and to aggregate `player_stats`.
    placements_result = await session.execute(
        select(ShotPlacementRecord).where(ShotPlacementRecord.match_id == match.id)
    )
    placements = list(placements_result.scalars())
    placement_by_event_id = {placement.score_event_id: placement for placement in placements}

    nickname_ids = {
        entry_id
        for placement in placements
        for entry_id in (placement.roster_entry_id, placement.losing_roster_entry_id)
        if entry_id is not None
    }
    nickname_by_id: dict[uuid.UUID, str] = {}
    if nickname_ids:
        nickname_result = await session.execute(
            select(RosterEntry.id, RosterEntry.nickname).where(RosterEntry.id.in_(nickname_ids))
        )
        nickname_by_id = {row.id: row.nickname for row in nickname_result.all()}

    def _detail_for(event_id: uuid.UUID) -> ShotPlacementSummary | None:
        placement = placement_by_event_id.get(event_id)
        if placement is None:
            return None
        # research.md Decision 2: a row with all its fields NULL (confirmed
        # with nothing picked) renders identically to no row at all. 035
        # made that five fields: a row carrying only an ending type IS a
        # recorded detail (research.md Decision 4).
        if (
            placement.roster_entry_id is None
            and placement.losing_roster_entry_id is None
            and placement.landing_x is None
            and placement.landing_y is None
            and placement.ending_type is None
        ):
            return None
        return ShotPlacementSummary(
            scoring_roster_entry_id=(
                str(placement.roster_entry_id) if placement.roster_entry_id else None
            ),
            scoring_nickname=(
                nickname_by_id.get(placement.roster_entry_id)
                if placement.roster_entry_id
                else None
            ),
            losing_roster_entry_id=(
                str(placement.losing_roster_entry_id)
                if placement.losing_roster_entry_id
                else None
            ),
            losing_nickname=(
                nickname_by_id.get(placement.losing_roster_entry_id)
                if placement.losing_roster_entry_id
                else None
            ),
            landing_x=placement.landing_x,
            landing_y=placement.landing_y,
            ending_type=placement.ending_type,
        )

    event_details = {event.id: _detail_for(event.id) for event in ctx.point_events}

    # research.md Decision 3/4: two independent per-field aggregations —
    # scored_count from roster_entry_id, fault_count from
    # losing_roster_entry_id — over the SAME placements queried above; an
    # empty combined result means "no data at all" (player_stats stays []),
    # otherwise every one of this match's actual participants is listed,
    # zero counts included (FR-009).
    scored_counts: dict[uuid.UUID, int] = defaultdict(int)
    fault_counts: dict[uuid.UUID, int] = defaultdict(int)
    for placement in placements:
        if placement.roster_entry_id is not None:
            scored_counts[placement.roster_entry_id] += 1
        if placement.losing_roster_entry_id is not None:
            fault_counts[placement.losing_roster_entry_id] += 1

    player_stats: list[PlayerScoringStat] = []
    if scored_counts or fault_counts:
        for participant in summary.team_a + summary.team_b:
            entry_id = uuid.UUID(participant.roster_entry_id)
            player_stats.append(
                PlayerScoringStat(
                    roster_entry_id=participant.roster_entry_id,
                    nickname=participant.nickname,
                    team=participant.team,
                    scored_count=scored_counts.get(entry_id, 0),
                    fault_count=fault_counts.get(entry_id, 0),
                )
            )

    # 033-match-record-derived-stats FR-004: a partial/absent history gets
    # the "no data" defaults for every derived block, never numbers
    # computed from an incomplete record.
    parts: dict[str, object] = {}
    if ctx.completeness == "complete":
        await _build_derived_stats(session, ctx, placements, parts)

    return MatchDetailParts(
        event_details=event_details,
        player_stats=player_stats,
        serve_stats=parts.get("serve_stats"),
        momentum_stats=parts.get("momentum_stats"),
        tempo_stats=parts.get("tempo_stats"),
        landing_distribution=parts.get("landing_distribution", []),  # type: ignore[arg-type]
        clutch_stats=parts.get("clutch_stats"),
        ending_stats=parts.get("ending_stats"),
        sections=[Section(kind="net_rally.match_detail")],
    )
