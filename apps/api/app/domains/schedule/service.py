"""Schedule domain service layer: round generation, manual assignment, member
changes, and the abandon-matches hooks consumed by 001/002. Per
specs/003-schedule-rotation/plan.md and research.md."""

import random
import secrets
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast, get_args

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.errors import ApiError
from app.core.realtime import court_channel, group_notifications_channel, publish
from app.domains.court.models import Court
from app.domains.group.models import Group, RoundHistory
from app.domains.roster.models import RosterEntry
from app.domains.schedule.algorithms import (
    random_pair_units,
    round_robin_pairs,
    stage1_select_players,
    stage2_pair_players,
    team_matchup_stage2,
)
from app.domains.schedule.models import (
    Match,
    MatchParticipant,
    PairHistory,
    Partnership,
    ScoreEvent,
    ScoreServeRecord,
    ShotPlacementRecord,
)
from app.domains.schedule.schemas import (
    CourtLiveState,
    CourtScheduleStatus,
    EndingType,
    MatchDetailResponse,
    MatchLiveDetail,
    MatchSummary,
    NextUpPreview,
    ParticipantSummary,
    PartnershipsResponse,
    PartnershipSummary,
    RosterScheduleStatus,
    RosterSummary,
    RoundMatchesResponse,
    RoundMatchSummary,
    RoundPhase,
    ScheduleResponse,
    ScoreMutationResult,
    ServeStationInfo,
    Team,
    TemporaryPairing,
    TemporaryPairingsResponse,
    WaitingReason,
)

_ACTIVE_MATCH_STATUSES = ("queued", "in_progress")


async def abandon_group_matches(session: AsyncSession, group_id: uuid.UUID) -> None:
    """Implements 001's `AbandonMatchesHook` — called from `disband_group()`.
    Abandons every not-yet-terminal match for the whole group. PairHistory is
    untouched: pair counts are recorded at match creation, not completion
    (research.md #5), so nothing to undo here."""
    await session.execute(
        update(Match)
        .where(Match.group_id == group_id, Match.status.in_(_ACTIVE_MATCH_STATUSES))
        .values(status="abandoned", ended_at=datetime.now(UTC))
    )


async def abandon_court_matches(session: AsyncSession, court_id: uuid.UUID) -> bool:
    """Implements 002's `AbandonCourtMatchesHook` — called from
    `delete_court()`. Returns whether any match was actually abandoned, so
    the caller can report `had_active_match` in its response."""
    result = await session.execute(
        select(Match.id).where(
            Match.court_id == court_id, Match.status.in_(_ACTIVE_MATCH_STATUSES)
        )
    )
    match_ids = list(result.scalars().all())
    if not match_ids:
        return False

    await session.execute(
        update(Match)
        .where(Match.id.in_(match_ids))
        .values(status="abandoned", ended_at=datetime.now(UTC))
    )
    return True


async def apply_wait_count_updates(
    session: AsyncSession, group_id: uuid.UUID, selected_ids: Sequence[uuid.UUID]
) -> None:
    """FR-007 / research.md #9: selected participants' `wait_count` -> 0;
    every other active roster entry's `wait_count` += 1 (NULL treated as 0
    first, i.e. a never-played member who missed this round has now waited
    one round). Two bulk UPDATEs, not a per-row Python loop."""
    selected = list(selected_ids)
    if selected:
        await session.execute(
            update(RosterEntry).where(RosterEntry.id.in_(selected)).values(wait_count=0)
        )
    await session.execute(
        update(RosterEntry)
        .where(
            RosterEntry.group_id == group_id,
            RosterEntry.status == "active",
            RosterEntry.id.notin_(selected),
        )
        .values(wait_count=func.coalesce(RosterEntry.wait_count, 0) + 1)
    )


async def _increment_pair_history(
    session: AsyncSession, group_id: uuid.UUID, player_ids: Sequence[uuid.UUID]
) -> None:
    """research.md #5: every unordered pair among `player_ids` gets +1,
    regardless of team role, at match-creation time (never reversed later
    regardless of how the match ends — see FR-009)."""
    ids = list(player_ids)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            lo, hi = sorted((ids[i], ids[j]))
            stmt = pg_insert(PairHistory).values(
                group_id=group_id, player_lo_id=lo, player_hi_id=hi, pair_count=1
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["group_id", "player_lo_id", "player_hi_id"],
                set_={"pair_count": PairHistory.pair_count + 1},
            )
            await session.execute(stmt)


async def get_pair_count(
    session: AsyncSession, group_id: uuid.UUID, player_a: uuid.UUID, player_b: uuid.UUID
) -> int:
    lo, hi = sorted((player_a, player_b))
    result = await session.execute(
        select(PairHistory.pair_count).where(
            PairHistory.group_id == group_id,
            PairHistory.player_lo_id == lo,
            PairHistory.player_hi_id == hi,
        )
    )
    return result.scalar_one_or_none() or 0


@dataclass(frozen=True)
class StationResult:
    """Output of `_compute_station()` — one snapshot of "who's serving and
    where everyone stands", per specs/030-score-serve-record/data-model.md
    站位計算公式. Field names mirror `ScoreServeRecord`'s columns 1:1."""

    server_roster_entry_id: uuid.UUID
    server_team: Team
    team_a_right_roster_entry_id: uuid.UUID | None
    team_a_left_roster_entry_id: uuid.UUID | None
    team_b_right_roster_entry_id: uuid.UUID | None
    team_b_left_roster_entry_id: uuid.UUID | None


def _team_station(
    reference_server_id: uuid.UUID, participants: Sequence[uuid.UUID], score: int
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """One team's (right, left) station occupants — research.md Decision 3:
    the reference server stands right when their team's score is even, left
    when odd; the other participant (doubles only — `None` for singles)
    always takes the opposite box. For singles (`other` is `None`), this
    correctly leaves the box the reference server isn't in as `None` in
    either parity, rather than swapping which box is empty."""
    other = next((p for p in participants if p != reference_server_id), None)
    if score % 2 == 0:
        return reference_server_id, other
    return other, reference_server_id


def _compute_station(
    serving_team: Team,
    team_a_participants: Sequence[uuid.UUID],
    team_b_participants: Sequence[uuid.UUID],
    team_a_reference_server_id: uuid.UUID,
    team_b_reference_server_id: uuid.UUID,
    score_a: int,
    score_b: int,
) -> StationResult:
    """Pure function — 030-score-serve-record research.md Decision 3. Given
    which team currently serves, each team's reference server, and the
    current score, derives all four station slots (singles: one slot per
    team stays `None`) and who's currently serving."""
    team_a_right, team_a_left = _team_station(
        team_a_reference_server_id, team_a_participants, score_a
    )
    team_b_right, team_b_left = _team_station(
        team_b_reference_server_id, team_b_participants, score_b
    )
    server_roster_entry_id = (
        team_a_reference_server_id if serving_team == "A" else team_b_reference_server_id
    )
    return StationResult(
        server_roster_entry_id=server_roster_entry_id,
        server_team=serving_team,
        team_a_right_roster_entry_id=team_a_right,
        team_a_left_roster_entry_id=team_a_left,
        team_b_right_roster_entry_id=team_b_right,
        team_b_left_roster_entry_id=team_b_left,
    )


async def _match_participants_by_team(
    session: AsyncSession, match_id: uuid.UUID
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Returns (team_a_roster_entry_ids, team_b_roster_entry_ids) for a
    match — shared by `_initialize_serve_state()`,
    `_advance_serve_state_and_snapshot()`, and `_build_serve_station()`."""
    result = await session.execute(
        select(MatchParticipant.roster_entry_id, MatchParticipant.team).where(
            MatchParticipant.match_id == match_id
        )
    )
    team_a: list[uuid.UUID] = []
    team_b: list[uuid.UUID] = []
    for roster_entry_id, team in result.all():
        (team_a if team == "A" else team_b).append(roster_entry_id)
    return team_a, team_b


async def _build_serve_station(session: AsyncSession, match: Match) -> ServeStationInfo | None:
    """029-serve-rotation-display: the *live* equivalent of a
    `ScoreServeRecord` snapshot — computed fresh from `match`'s currently
    persisted serve state + score, not stored anywhere itself. `None` when
    the match has no serve state yet (research.md Decision 4 — a match
    created before 030-score-serve-record's migration).

    Shared by `court_live_state()` (every read) and `apply_score_delta()`'s
    `delta < 0` branch (`-1` doesn't advance the serve state, so there's no
    fresh `ScoreServeRecord` to reuse there like the `delta > 0` branch
    does — this recomputes from the unchanged serve state + corrected
    score instead, per FR-010)."""
    if match.serving_team is None:
        return None
    team_a, team_b = await _match_participants_by_team(session, match.id)
    station = _compute_station(
        cast(Team, match.serving_team),
        team_a,
        team_b,
        cast(uuid.UUID, match.team_a_reference_server_id),
        cast(uuid.UUID, match.team_b_reference_server_id),
        match.score_a,
        match.score_b,
    )
    return ServeStationInfo(
        server_roster_entry_id=str(station.server_roster_entry_id),
        server_team=station.server_team,
        team_a_right_roster_entry_id=_opt_str(station.team_a_right_roster_entry_id),
        team_a_left_roster_entry_id=_opt_str(station.team_a_left_roster_entry_id),
        team_b_right_roster_entry_id=_opt_str(station.team_b_right_roster_entry_id),
        team_b_left_roster_entry_id=_opt_str(station.team_b_left_roster_entry_id),
    )


def _opt_str(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None


async def _initialize_serve_state(session: AsyncSession, match: Match) -> None:
    """030-score-serve-record FR-001/FR-002 (research.md Decision 4/5):
    called once, exactly when a match becomes `in_progress` (the only two
    call sites are `create_match_with_participants()` and
    `pull_queued_match_for_court()`) — randomly assigns the serving team
    and, for doubles, each team's own reference server (both the serving
    and the receiving side, so `_compute_station()` has a starting point
    for all four slots). Mutates `match` in place; caller flushes/commits."""
    team_a, team_b = await _match_participants_by_team(session, match.id)
    match.serving_team = random.choice(("A", "B"))
    match.team_a_reference_server_id = random.choice(team_a)
    match.team_b_reference_server_id = random.choice(team_b)


async def create_match_with_participants(
    session: AsyncSession,
    group: Group,
    *,
    court_id: uuid.UUID | None,
    round_number: int,
    status: str,
    team_a: Sequence[uuid.UUID],
    team_b: Sequence[uuid.UUID],
) -> Match:
    """Writes `matches` + `match_participants` + `pair_history`, applying the
    group's current Match Scoring Settings as an immutable snapshot (spec
    FR-012, 001's data-model.md §2). Flushes but does NOT commit — this is a
    building block called in a loop by `generate_next_round()`, which commits
    once for the whole round (atomicity); callers using it standalone (e.g.
    `manual_assign()`) are responsible for their own commit."""
    match = Match(
        group_id=group.id,
        court_id=court_id,
        round_number=round_number,
        status=status,
        target_score=group.target_score,
        deuce_threshold=group.deuce_threshold,
        cap_score=group.cap_score,
        # 031-shot-placement-scoring research.md Decision 6: snapshotted here
        # only — pull_queued_match_for_court() merely transitions an
        # already-created row to in_progress, this value is already fixed.
        detailed_scoring_enabled=group.detailed_scoring_enabled,
        started_at=datetime.now(UTC) if status == "in_progress" else None,
    )
    session.add(match)
    await session.flush()

    participants = [
        MatchParticipant(match_id=match.id, roster_entry_id=pid, team="A") for pid in team_a
    ] + [MatchParticipant(match_id=match.id, roster_entry_id=pid, team="B") for pid in team_b]
    session.add_all(participants)

    await _increment_pair_history(session, group.id, list(team_a) + list(team_b))
    await session.flush()
    if status == "in_progress":
        await _initialize_serve_state(session, match)
        await session.flush()
    return match


async def _get_active_courts_ordered(session: AsyncSession, group_id: uuid.UUID) -> list[Court]:
    result = await session.execute(
        select(Court)
        .where(Court.group_id == group_id, Court.deleted_at.is_(None))
        .order_by(Court.created_at)
    )
    return list(result.scalars().all())


async def _get_active_roster_for_selection(
    session: AsyncSession, group_id: uuid.UUID
) -> list[tuple[uuid.UUID, int | None, datetime]]:
    result = await session.execute(
        select(RosterEntry.id, RosterEntry.wait_count, RosterEntry.joined_at).where(
            RosterEntry.group_id == group_id, RosterEntry.status == "active"
        )
    )
    return [(row.id, row.wait_count, row.joined_at) for row in result.all()]


async def _get_active_roster_ids(session: AsyncSession, group_id: uuid.UUID) -> list[uuid.UUID]:
    """011-round-robin-scheduling: the algorithmic modes' full round-robin
    generation includes every active member — no wait_count-based subset
    selection (research.md #5), unlike `_get_active_roster_for_selection`
    above, which `stage1_select_players` still needs for fair_rotation
    doubles (untouched by this feature)."""
    result = await session.execute(
        select(RosterEntry.id).where(
            RosterEntry.group_id == group_id, RosterEntry.status == "active"
        )
    )
    return list(result.scalars())


async def _build_pair_count_lookup(
    session: AsyncSession, group_id: uuid.UUID
) -> Callable[[uuid.UUID, uuid.UUID], int]:
    result = await session.execute(select(PairHistory).where(PairHistory.group_id == group_id))
    cache = {
        frozenset((row.player_lo_id, row.player_hi_id)): row.pair_count
        for row in result.scalars()
    }

    def lookup(a: uuid.UUID, b: uuid.UUID) -> int:
        return cache.get(frozenset((a, b)), 0)

    return lookup


async def pull_queued_match_for_court(
    session: AsyncSession, group_id: uuid.UUID, round_number: int, court_id: uuid.UUID
) -> Match | None:
    """FR-027: binds the next `queued`, court-unassigned match in this round
    to `court_id` and starts it. Shared by round generation's initial
    distribution (research.md #7) and `advance_court_after_match_ends`
    (US3) — same "pull from the queue" mechanism either way.

    011-round-robin-scheduling research.md #4: a full round-robin schedule
    puts the same player in several queued matches at once, so this MUST
    skip any candidate whose participants are already in an `in_progress`
    match elsewhere in the group — otherwise the same person could end up
    "playing" on two courts simultaneously. Picks the earliest-created
    eligible match; if none is eligible yet, returns None (court waits)."""
    busy_participants = (
        select(MatchParticipant.roster_entry_id)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(Match.group_id == group_id, Match.status == "in_progress")
    ).scalar_subquery()

    result = await session.execute(
        select(Match)
        .where(
            Match.group_id == group_id,
            Match.round_number == round_number,
            Match.status == "queued",
            Match.court_id.is_(None),
            ~exists(
                select(MatchParticipant.id).where(
                    MatchParticipant.match_id == Match.id,
                    MatchParticipant.roster_entry_id.in_(busy_participants),
                )
            ),
        )
        .order_by(Match.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    match = result.scalar_one_or_none()
    if match is None:
        return None
    match.court_id = court_id
    match.status = "in_progress"
    match.started_at = datetime.now(UTC)
    await _initialize_serve_state(session, match)
    await session.flush()
    return match


async def _match_participants_payload(
    session: AsyncSession, match_id: uuid.UUID
) -> list[dict[str, str]]:
    result = await session.execute(
        select(MatchParticipant, RosterEntry.nickname)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(MatchParticipant.match_id == match_id)
    )
    return [
        {
            "roster_entry_id": str(participant.roster_entry_id),
            "nickname": nickname,
            "team": participant.team,
        }
        for participant, nickname in result.all()
    ]


async def _publish_rotation_updated(
    session: AsyncSession, group_id: uuid.UUID, court_id: uuid.UUID, match: Match
) -> None:
    """contracts/ably-events.md `rotation.updated` — a court just bound a new
    match (round generation's initial pull, `advance_court_after_match_ends`,
    or manual assignment). Callers MUST have already committed."""
    participants = await _match_participants_payload(session, match.id)
    await publish(
        court_channel(str(group_id), str(court_id)),
        "rotation.updated",
        {
            "match_id": str(match.id),
            "round_number": match.round_number,
            "participants": participants,
        },
    )


async def _publish_lineup_changed(
    session: AsyncSession, group: Group, touched_matches: Sequence[Match]
) -> None:
    """018-plan-then-start follow-up: after `swap_planned_match_players()`/
    `change_match_player()` mutates who's playing in a match, any open
    scoreboard/control-panel for it needs to refresh — otherwise a
    substitution only shows up in the admin's own view, never on the court
    itself, until some unrelated event happens to trigger a refetch.
    Callers MUST have already committed. A touched match already bound to a
    court (`in_progress`) reuses `rotation.updated` (contracts/ably-
    events.md: "a court's current match changed" — the same participants
    payload a live scoreboard/control panel already re-renders from); a
    still-`queued` touched match has no court of its own yet, so this falls
    back to broadcasting `match.nextRound` to every court — the same
    reuse-as-refetch-trigger convention `end_current_round()`/
    `plan_next_round()` lean on — since only whichever court is currently
    peeking it as `next_up` cares."""
    any_still_queued = False
    for match in touched_matches:
        if match.court_id is not None:
            await _publish_rotation_updated(session, group.id, match.court_id, match)
        else:
            any_still_queued = True

    if any_still_queued:
        for court in await _get_active_courts_ordered(session, group.id):
            await publish(
                court_channel(str(group.id), str(court.id)),
                "match.nextRound",
                {"round_number": group.current_round_number},
            )


async def _generate_fair_rotation_matches(
    session: AsyncSession, group: Group, courts: list[Court], round_number: int
) -> None:
    """011-round-robin-scheduling FR-002: the singles case is redefined as a
    full round-robin covering every active member (research.md #1) — courts
    no longer bound how many matches get generated. Doubles is explicitly
    out of scope for this feature (spec.md User Story 1) and keeps its
    original "fill exactly `len(courts)` matches by wait_count priority"
    behavior unchanged below."""
    if group.match_mode == "singles":
        await _generate_singles_round_robin_matches(session, group, round_number)
        return

    per_match = 4
    n = len(courts) * per_match

    roster = await _get_active_roster_for_selection(session, group.id)
    selected_ids = stage1_select_players(roster, n)
    await apply_wait_count_updates(session, group.id, selected_ids)

    if not selected_ids:
        return

    pair_count_lookup = await _build_pair_count_lookup(session, group.id)
    teammate_pairs = stage2_pair_players(selected_ids, pair_count_lookup)
    team_matchups = team_matchup_stage2(teammate_pairs, pair_count_lookup)
    for team_a, team_b in team_matchups:
        await create_match_with_participants(
            session,
            group,
            court_id=None,
            round_number=round_number,
            status="queued",
            team_a=list(team_a),
            team_b=list(team_b),
        )


async def _generate_singles_round_robin_matches(
    session: AsyncSession, group: Group, round_number: int
) -> None:
    """011-round-robin-scheduling FR-002/research.md #1: every active
    roster member plays every other active member exactly once this round.
    No wait_count-based subset selection — the full round-robin already
    guarantees equal participation (research.md #5), so `stage1_select_players`/
    `apply_wait_count_updates` are intentionally not called here."""
    roster_ids = await _get_active_roster_ids(session, group.id)
    # research.md #1 follow-up (fix for "球員固定同一側"): alternate which
    # side the circle-method anchor starts on from one Round to the next,
    # so the same perennial pool[0] roster entry doesn't land on Team A in
    # batch 0 of every Round's full round-robin.
    for batch in round_robin_pairs(roster_ids, start_swapped=round_number % 2 == 1):
        for player_a, player_b in batch:
            await create_match_with_participants(
                session,
                group,
                court_id=None,
                round_number=round_number,
                status="queued",
                team_a=[player_a],
                team_b=[player_b],
            )


async def _generate_individual_mixed_matches(
    session: AsyncSession, group: Group, round_number: int
) -> None:
    """011-round-robin-scheduling FR-004/research.md #2,#3: every active
    member partners with every other active member at least once this
    round — a combinatorial design problem with no general closed-form
    solution (unlike singles/fixed_partner's circle method), so this uses a
    multi-wave greedy loop instead: each wave reuses the exact same
    two-stage pipeline fair_rotation doubles already runs
    (`stage2_pair_players` -> `team_matchup_stage2`), re-reading
    `PairHistory` (which reflects every match `flush()`-ed by earlier waves
    in this same call, per `create_match_with_participants`) so each wave
    tends to surface pairs not yet seen. A wave that adds no new teammate
    pair just means this rotation (see below) is stuck given the current
    `PairHistory` — not that every rotation is; only once a full cycle of
    rotations in a row adds nothing does the loop give up, since the
    pipeline is otherwise deterministic given unchanged inputs.

    `PairHistory` counts teammates and opponents alike (003 research.md
    #5), so every pair in a single match gets incremented equally — on its
    own, that degenerates into the SAME tie-break every wave (a fresh
    group's first individual_mixed round would stall after just one wave,
    even when perfect coverage is achievable). The teammate-forming stage
    therefore adds a large penalty for any pair already seen as teammates
    THIS generation (`seen_teammate_pairs`, precise — unlike `PairHistory`,
    it doesn't conflate teammates with opponents), pushing the greedy
    search toward genuinely new pairings each wave; the matchup stage still
    uses the unpenalized `pair_count_lookup`, since minimizing repeat
    opponents is exactly what it's already meant to do.

    `greedy_pair_by_cost`'s anchor (`remaining.pop(0)`, i.e. the list's
    first element) always ends up paired, never the odd one left sitting
    out — so with an unrotated roster order the same player would be the
    anchor (and, transitively, the anchor team going into
    `team_matchup_stage2`) every single wave, guaranteeing them a match
    every wave while the other players merely take turns sitting out.
    `roster_ids` isn't priority-ordered here (unlike fair_rotation's
    stage-1 selection), so rotating it each wave is safe and spreads the
    anchor role round-robin across the whole roster instead of pinning it
    to whoever the roster query happens to return first.

    Rotating the anchor alone only rules out the single-player-always-plays
    extreme — it doesn't bound how unevenly the OTHER players' per-round
    appearance counts can land (confirmed by simulation: 6 players still
    landed on a 4-vs-6 split some rounds), because a doubles wave can only
    ever seat a multiple of 4, so whenever `len(roster_ids)` isn't one,
    `sit_out_count` players must sit out every wave regardless of anchor —
    and nothing about `stage2_pair_players`/`team_matchup_stage2` (which
    only optimize for pair-coverage/repeat-opponent cost) has any notion of
    "who's already played more this round." So sit-out selection is done
    explicitly, upfront, per wave: rank this wave's roster order by
    `play_count_this_round` (most-played first, ties broken by the
    rotation's order since `sorted` is stable) and drop the top
    `sit_out_count` from this wave's candidate pool entirely — they never
    reach `stage2_pair_players`, so they can't be dealt back in by the
    pairing cost. The remaining count is always a multiple of 4, so
    `stage2_pair_players`/`team_matchup_stage2` never need to drop anyone
    further this wave; every remaining player gets seated. This still
    doesn't guarantee a perfectly even round (pair-coverage sometimes needs
    a few extra waves to make room for it — confirmed by simulation, e.g. 6
    players needing 9 matches this way instead of 7), but it does bound the
    worst-case spread within a round to 1 match, versus the 2+ spread
    rotation alone left possible."""
    roster_ids = await _get_active_roster_ids(session, group.id)
    if len(roster_ids) < 4:
        return

    total_possible_pairs = len(roster_ids) * (len(roster_ids) - 1) // 2
    seen_teammate_pairs: set[frozenset[uuid.UUID]] = set()
    NOT_YET_TEAMMATES_PENALTY = 1_000_000
    play_count_this_round: dict[uuid.UUID, int] = dict.fromkeys(roster_ids, 0)
    sit_out_count = len(roster_ids) % 4

    wave = 0
    stale_rotations = 0
    while len(seen_teammate_pairs) < total_possible_pairs and stale_rotations < len(roster_ids):
        pair_count_lookup = await _build_pair_count_lookup(session, group.id)

        def cost_favoring_unseen_teammates(
            a: uuid.UUID,
            b: uuid.UUID,
            _pair_count_lookup: Callable[[uuid.UUID, uuid.UUID], int] = pair_count_lookup,
        ) -> int:
            penalty = NOT_YET_TEAMMATES_PENALTY if frozenset((a, b)) in seen_teammate_pairs else 0
            return _pair_count_lookup(a, b) + penalty

        rotation = wave % len(roster_ids)
        wave_order = roster_ids[rotation:] + roster_ids[:rotation]
        wave += 1

        if sit_out_count:
            ranked_by_play_count = sorted(
                wave_order, key=lambda player_id: -play_count_this_round[player_id]
            )
            sitting_out = set(ranked_by_play_count[:sit_out_count])
            active_order = [player_id for player_id in wave_order if player_id not in sitting_out]
        else:
            active_order = wave_order

        teammate_pairs = stage2_pair_players(active_order, cost_favoring_unseen_teammates)
        new_pairs = [
            frozenset(pair) for pair in teammate_pairs if frozenset(pair) not in seen_teammate_pairs
        ]
        if not new_pairs:
            stale_rotations += 1
            continue
        stale_rotations = 0

        team_matchups = team_matchup_stage2(teammate_pairs, pair_count_lookup)
        for team_a, team_b in team_matchups:
            for player_id in (*team_a, *team_b):
                play_count_this_round[player_id] += 1
            await create_match_with_participants(
                session,
                group,
                court_id=None,
                round_number=round_number,
                status="queued",
                team_a=list(team_a),
                team_b=list(team_b),
            )
        seen_teammate_pairs.update(frozenset(pair) for pair in teammate_pairs)


async def _get_active_partnership_teams(
    session: AsyncSession, group_id: uuid.UUID
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Partnerships whose both members are still active — a member leaving
    already dissolves their Partnership (FR-023), so this is mostly a
    defensive filter against any inconsistency. Used when
    `partner_source == "manual"` (research.md #6)."""
    result = await session.execute(select(Partnership).where(Partnership.group_id == group_id))
    partnerships = result.scalars().all()
    if not partnerships:
        return []

    all_ids = {p.player_a_id for p in partnerships} | {p.player_b_id for p in partnerships}
    active_result = await session.execute(
        select(RosterEntry.id).where(RosterEntry.id.in_(all_ids), RosterEntry.status == "active")
    )
    active_ids = set(active_result.scalars())
    return [
        (p.player_a_id, p.player_b_id)
        for p in partnerships
        if p.player_a_id in active_ids and p.player_b_id in active_ids
    ]


async def compute_auto_partner_teams_for_round(
    session: AsyncSession, group_id: uuid.UUID
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """011-round-robin-scheduling FR-009: computed fresh for every Round
    when `partner_source == "auto"` — deliberately a different function
    from `auto_pair_on_enter_fixed_partner()` (research.md #6 naming
    clarification), which is a one-time join-order fallback that writes to
    `partnerships`. This pairs the whole active roster by minimizing
    `PairHistory` pair_count (reusing `stage2_pair_players`) and never
    touches `partnerships`."""
    active_ids = await _get_active_roster_ordered(session, group_id)
    pair_count_lookup = await _build_pair_count_lookup(session, group_id)
    return stage2_pair_players(active_ids, pair_count_lookup)


async def _resolve_manual_fixed_partner_teams(
    session: AsyncSession,
    group: Group,
    temporary_pairings: list[tuple[uuid.UUID, uuid.UUID]] | None,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """017-fixed-partner-autofill data-model.md 三段聯集，`partner_source ==
    "manual"` 專用：(1) 既有正式搭檔（不變）；(2) 驗證通過的
    `temporary_pairings`——任一方已有正式搭檔/非現役、或同一位成員在提交的
    清單中出現超過一次（FR-003：該重複成員涉及的組合一律視為無效、一律
    捨棄，MUST NOT 只丟棄後面出現的那一組）的組合皆被捨棄；(3) 對步驟 1+2
    後仍未涵蓋到的現役成員，呼叫 `random_pair_units()` 當場隨機配對補齊
    （FR-002）。"""
    formal_teams = await _get_active_partnership_teams(session, group.id)
    covered = {pid for pair in formal_teams for pid in pair}

    active_ids = await _get_active_roster_ordered(session, group.id)
    active_set = set(active_ids)

    temp_list = temporary_pairings or []
    member_counts: dict[uuid.UUID, int] = {}
    for player_a, player_b in temp_list:
        member_counts[player_a] = member_counts.get(player_a, 0) + 1
        member_counts[player_b] = member_counts.get(player_b, 0) + 1

    validated_temp_teams: list[tuple[uuid.UUID, uuid.UUID]] = []
    for player_a, player_b in temp_list:
        if member_counts[player_a] > 1 or member_counts[player_b] > 1:
            continue
        if player_a in covered or player_b in covered:
            continue
        if player_a not in active_set or player_b not in active_set:
            continue
        validated_temp_teams.append((player_a, player_b))
        covered.add(player_a)
        covered.add(player_b)

    remaining = [pid for pid in active_ids if pid not in covered]
    autofill_teams = random_pair_units(remaining)

    return [*formal_teams, *validated_temp_teams, *autofill_teams]


async def _generate_fixed_partner_matches(
    session: AsyncSession,
    group: Group,
    courts: list[Court],
    round_number: int,
    temporary_pairings: list[tuple[uuid.UUID, uuid.UUID]] | None = None,
) -> None:
    """011-round-robin-scheduling FR-003/FR-008: every team plays every
    other team exactly once this round (research.md #1's circle method,
    applied to teams) — courts no longer bound how many matches get
    generated, and there's no wait_count-based team subset selection
    (research.md #5); ALL teams participate. `group.partner_source`
    decides where the teams come from (research.md #6). 017-fixed-partner-
    autofill: in "manual" mode, `temporary_pairings` (validated) plus an
    auto-fill pass over anyone still uncovered ensure the round always
    covers every active member (FR-002/FR-003/FR-007) — see
    `_resolve_manual_fixed_partner_teams()`."""
    del courts

    if group.partner_source == "auto":
        teams = await compute_auto_partner_teams_for_round(session, group.id)
    else:
        teams = await _resolve_manual_fixed_partner_teams(session, group, temporary_pairings)

    # research.md #1 follow-up (fix for "球員固定同一側"): same anchor-side
    # alternation as singles round-robin above, applied at the team level.
    for batch in round_robin_pairs(teams, start_swapped=round_number % 2 == 1):
        for team_a, team_b in batch:
            await create_match_with_participants(
                session,
                group,
                court_id=None,
                round_number=round_number,
                status="queued",
                team_a=list(team_a),
                team_b=list(team_b),
            )


async def _lock_group_for_round_generation(session: AsyncSession, group_id: uuid.UUID) -> None:
    """research.md #8: pessimistic lock (not the optimistic version-column
    pattern used elsewhere in this project) — a round's write set is too
    broad (many matches + wait_count rows) to describe with a single version
    number. A concurrent request that can't acquire the lock immediately is
    rejected outright rather than queued or retried."""
    try:
        await session.execute(
            select(Group.id).where(Group.id == group_id).with_for_update(nowait=True)
        )
    except DBAPIError as exc:
        await session.rollback()
        # 55P03 = lock_not_available (Postgres' response to FOR UPDATE
        # NOWAIT hitting an already-locked row) — the only case this
        # function means to translate. Anything else is a real DB error and
        # MUST propagate rather than be misreported as a round-generation
        # conflict.
        if getattr(exc.orig, "sqlstate", None) != "55P03":
            raise
        raise ApiError("ROUND_GENERATION_IN_PROGRESS", status_code=409) from exc


async def _last_match_lineup_for_round(
    session: AsyncSession, group_id: uuid.UUID, round_number: int
) -> frozenset[uuid.UUID] | None:
    """The full participant set (both teams) of the last-called match in the
    given round, keyed off the same `created_at` ordering
    `_shuffle_round_match_order` controls — or None if that round has no
    matches (e.g. round_number < 1, or nothing generated yet). Lets a new
    round's shuffle avoid reseating the previous round's closing lineup into
    its own first slot."""
    if round_number < 1:
        return None

    last_match_result = await session.execute(
        select(Match.id)
        .where(Match.group_id == group_id, Match.round_number == round_number)
        .order_by(Match.created_at.desc())
        .limit(1)
    )
    last_match_id = last_match_result.scalar_one_or_none()
    if last_match_id is None:
        return None

    participants_result = await session.execute(
        select(MatchParticipant.roster_entry_id).where(
            MatchParticipant.match_id == last_match_id
        )
    )
    return frozenset(participants_result.scalars())


async def _fetch_match_lineups(
    session: AsyncSession, match_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
    """match_id -> its full participant set (both teams combined) — only
    used for whole-lineup repeat comparisons, not team-side-aware logic."""
    result = await session.execute(
        select(MatchParticipant.match_id, MatchParticipant.roster_entry_id).where(
            MatchParticipant.match_id.in_(match_ids)
        )
    )
    lineups: dict[uuid.UUID, set[uuid.UUID]] = {match_id: set() for match_id in match_ids}
    for match_id, roster_entry_id in result.all():
        lineups[match_id].add(roster_entry_id)
    return {match_id: frozenset(ids) for match_id, ids in lineups.items()}


async def _shuffle_round_match_order(
    session: AsyncSession, group_id: uuid.UUID, round_number: int
) -> None:
    """Randomizes the call-up/display order of this round's just-generated
    matches — purely cosmetic, deliberately separate from who's paired with
    whom (that's decided by the mechanism-specific generators above; this
    runs after all of them). `pull_queued_match_for_court` and
    `build_round_matches_list` both `order_by(Match.created_at)` (this
    file), and `created_at` is otherwise unused — never serialized to any
    schema — so overwriting it with a freshly shuffled sequence is the
    cheapest way to randomize both without a dedicated ordering column.

    Also avoids landing the exact same 2/4-player lineup that closed out the
    previous round into this round's opening slot: if the shuffle happens to
    put it there and another match with a different lineup exists, the two
    are swapped. Only the first slot is guarded — back-to-back repeats later
    in the round are accepted as ordinary shuffle noise."""
    result = await session.execute(
        select(Match.id).where(Match.group_id == group_id, Match.round_number == round_number)
    )
    match_ids = list(result.scalars())
    if len(match_ids) < 2:
        return

    random.shuffle(match_ids)

    prev_lineup = await _last_match_lineup_for_round(session, group_id, round_number - 1)
    if prev_lineup is not None:
        lineups = await _fetch_match_lineups(session, match_ids)
        if lineups[match_ids[0]] == prev_lineup:
            for i in range(1, len(match_ids)):
                if lineups[match_ids[i]] != prev_lineup:
                    match_ids[0], match_ids[i] = match_ids[i], match_ids[0]
                    break

    base = datetime.now(UTC)
    for index, match_id in enumerate(match_ids):
        await session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(created_at=base + timedelta(microseconds=index))
        )


async def _begin_new_round(session: AsyncSession, group: Group) -> None:
    """Shared prefix of both the fused `generate_next_round()` and the
    two-step `plan_next_round()`: force-abandons whatever is still queued/
    in_progress (a no-op if the round already finished naturally, but also
    how an admin force-skips an unfinished round), then bumps
    `current_round_number` and writes the round's `RoundHistory` row. Caller
    is responsible for the zero-courts/odd-headcount guards and the
    generation lock beforehand."""
    await abandon_group_matches(session, group.id)

    history_count_result = await session.execute(
        select(func.count())
        .select_from(RoundHistory)
        .where(RoundHistory.group_id == group.id)
    )
    has_generated_round_before = (history_count_result.scalar_one() or 0) > 0
    if has_generated_round_before:
        group.current_round_number += 1
    # The very first call for a group leaves current_round_number at its
    # column default (1) so it generates round 1 itself, instead of
    # pre-incrementing to 2 and skipping round 1 entirely. Every call still
    # writes a round_history row in the same transaction, one per round
    # generated (including round 1 now).
    session.add(
        RoundHistory(
            group_id=group.id,
            round_number=group.current_round_number,
            started_at=datetime.now(UTC),
        )
    )


async def _generate_round_matches_for_mechanism(
    session: AsyncSession,
    group: Group,
    courts: list[Court],
    temporary_pairings: list[tuple[uuid.UUID, uuid.UUID]] | None,
) -> None:
    """Dispatches per `scheduling_mechanism` to create the round's matches as
    `queued` (manual mode generates nothing, FR-033), then randomizes call-up
    order — everything `generate_next_round()` used to do between the round-
    number bump and pulling matches onto courts. 017-fixed-partner-autofill:
    `temporary_pairings` is only meaningful for `scheduling_mechanism ==
    "fixed_partner"` + `partner_source == "manual"`; ignored otherwise."""
    if group.scheduling_mechanism == "manual":
        pass
    elif group.scheduling_mechanism == "fair_rotation":
        await _generate_fair_rotation_matches(session, group, courts, group.current_round_number)
    elif group.scheduling_mechanism == "individual_mixed":
        # 011-round-robin-scheduling FR-004/research.md #2,#3: this now
        # diverges from fair_rotation doubles — a full round is "everyone
        # partners with everyone else at least once" (multi-wave), not a
        # single court-count-sized batch, so it gets its own generator.
        await _generate_individual_mixed_matches(session, group, group.current_round_number)
    elif group.scheduling_mechanism == "fixed_partner":
        await _generate_fixed_partner_matches(
            session, group, courts, group.current_round_number, temporary_pairings
        )
    else:
        raise ApiError("VALIDATION_ERROR", status_code=400)

    if group.scheduling_mechanism != "manual":
        await _shuffle_round_match_order(session, group.id, group.current_round_number)


async def _pull_matches_onto_courts(
    session: AsyncSession, group: Group, courts: list[Court]
) -> list[tuple[uuid.UUID, Match]]:
    """Pulls one queued match per available court onto that court — the
    "start the round" step shared by `generate_next_round()`'s fused flow
    and `start_planned_round()`."""
    pulled: list[tuple[uuid.UUID, Match]] = []
    for court in courts:
        match = await pull_queued_match_for_court(
            session, group.id, group.current_round_number, court.id
        )
        if match is not None:
            pulled.append((court.id, match))
    return pulled


async def generate_next_round(
    session: AsyncSession,
    group: Group,
    temporary_pairings: list[tuple[uuid.UUID, uuid.UUID]] | None = None,
) -> Group:
    """Round generation entry point for manual mode's "Next Round" button
    (FR-031~033) and Auto Next Round (018-plan-then-start moved the
    algorithmic mechanisms' admin-initiated path to the two-step
    `plan_next_round()` / `start_planned_round()` below, since neither of
    those callers has a human in the loop to review a plan before it
    starts). Force-abandons whatever is still queued/in_progress, then
    dispatches per `scheduling_mechanism`: for algorithmic modes, creates the
    round's matches as `queued` and immediately pulls one per available
    court (research.md #7); manual mode generates nothing (FR-033) — courts
    simply show "waiting for admin"."""
    courts = await _get_active_courts_ordered(session, group.id)
    if not courts:
        raise ApiError("NO_COURTS_AVAILABLE", status_code=400)

    # 011-round-robin-scheduling FR-003: fixed_partner's team round-robin
    # requires an even headcount to pair everyone up — checked before any
    # side effect (lock/abandon/round-number bump), same style as the
    # zero-courts guard above.
    if group.scheduling_mechanism == "fixed_partner":
        active_count = len(await _get_active_roster_ordered(session, group.id))
        if active_count % 2 != 0:
            raise ApiError("FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT", status_code=400)

    await _lock_group_for_round_generation(session, group.id)
    await _begin_new_round(session, group)
    await _generate_round_matches_for_mechanism(session, group, courts, temporary_pairings)
    pulled = await _pull_matches_onto_courts(session, group, courts)

    # Starting a round is real usage, not idleness — resets the auto-disband
    # clock (apps/api/app/scheduler/auto_disband.py) same as join/edit/reauth.
    group.last_activity_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(group)

    # contracts/ably-events.md: match.nextRound goes to every active court
    # regardless of mechanism (even manual, where nothing was generated);
    # rotation.updated only to courts that actually picked up a new match.
    for court in courts:
        await publish(
            court_channel(str(group.id), str(court.id)),
            "match.nextRound",
            {"round_number": group.current_round_number},
        )
    for court_id, match in pulled:
        await _publish_rotation_updated(session, group.id, court_id, match)

    return group


async def get_round_phase(session: AsyncSession, group: Group) -> RoundPhase:
    """018-plan-then-start: derives the current round's admin-facing
    "plan → start" state from `Match` rows alone (no new column) — there is
    deliberately no "manual" case here; that mechanism has no plan/start
    split (its admin-facing "Next Round" always fully advances via
    `generate_next_round()`), so callers must gate on
    `scheduling_mechanism` before consulting this.

    - `awaiting_plan`: no round generated yet, or the current round is
      finished (every match completed/abandoned) — the admin should plan
      the next one.
    - `awaiting_start`: `plan_next_round()` has queued this round's matches
      but none have been pulled onto a court yet — the admin can still
      `swap_planned_match_players()` before confirming.
    - `in_progress`: at least one match has been pulled onto a court.
    """
    result = await session.execute(
        select(Match.status, Match.court_id).where(
            Match.group_id == group.id, Match.round_number == group.current_round_number
        )
    )
    rows = result.all()
    if not rows:
        return "awaiting_plan"
    if all(status in ("completed", "abandoned") for status, _ in rows):
        return "awaiting_plan"
    if all(court_id is None for _, court_id in rows):
        return "awaiting_start"
    return "in_progress"


async def end_current_round(session: AsyncSession, group: Group) -> Group:
    """018-plan-then-start: the admin-facing "結束這一輪" step — force-
    abandons whatever is still queued/in_progress in the current round
    WITHOUT bumping `current_round_number` or generating anything, so
    `get_round_phase()` reads the round as `awaiting_plan` afterwards (every
    match is now terminal) and the admin proceeds to `plan_next_round()`
    separately. Split out from `plan_next_round()` so the "this discards
    unfinished matches" confirmation is its own explicit step, distinct from
    the (now non-destructive, dialog-free) planning step that follows it.
    Only meaningful while a round is actually still going — rejects
    otherwise. Manual mode keeps its old single-button `generate_next_round()`
    instead, which still does both in one step."""
    if group.scheduling_mechanism == "manual":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)

    await _lock_group_for_round_generation(session, group.id)
    if await get_round_phase(session, group) != "in_progress":
        raise ApiError("ROUND_NOT_IN_PROGRESS", status_code=409)

    await abandon_group_matches(session, group.id)
    group.last_activity_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(group)

    # Same reuse-as-refetch-trigger convention as generate_next_round()/
    # plan_next_round(): round_number is unchanged here, but every live
    # court/member/scoreboard view listening for match.nextRound just
    # refetches on it regardless of payload, which is exactly what a court
    # whose match just got abandoned needs to do (show "waiting" instead of
    # a stale in-progress match).
    for court in await _get_active_courts_ordered(session, group.id):
        await publish(
            court_channel(str(group.id), str(court.id)),
            "match.nextRound",
            {"round_number": group.current_round_number},
        )

    return group


async def plan_next_round(
    session: AsyncSession,
    group: Group,
    temporary_pairings: list[tuple[uuid.UUID, uuid.UUID]] | None = None,
) -> Group:
    """018-plan-then-start: the admin-facing "規劃賽程安排" step for
    algorithmic mechanisms — everything `generate_next_round()` does except
    pulling matches onto courts, so the admin can review the planned
    matchups (via `build_round_matches_list()`) and adjust them
    (`swap_planned_match_players()`, `reorder_planned_matches()`) before
    `start_planned_round()` actually puts anyone on a court. The admin-page
    UI only ever calls this once the round is already `awaiting_plan` (via
    `end_current_round()` or the round finishing naturally), so in practice
    this never has anything left to force-abandon — the `_begin_new_round()`
    call below still does it defensively for any other caller. Manual mode
    has no "plan" concept (the admin's per-court manual-assign already IS
    the plan) and keeps using `generate_next_round()` directly instead."""
    if group.scheduling_mechanism == "manual":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)

    courts = await _get_active_courts_ordered(session, group.id)
    if not courts:
        raise ApiError("NO_COURTS_AVAILABLE", status_code=400)

    if group.scheduling_mechanism == "fixed_partner":
        active_count = len(await _get_active_roster_ordered(session, group.id))
        if active_count % 2 != 0:
            raise ApiError("FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT", status_code=400)

    await _lock_group_for_round_generation(session, group.id)
    await _begin_new_round(session, group)
    await _generate_round_matches_for_mechanism(session, group, courts, temporary_pairings)

    group.last_activity_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(group)

    # Every court re-fetches on this, same as the fused flow — nothing is on
    # a court yet, so there's no rotation.updated to pair it with.
    for court in courts:
        await publish(
            court_channel(str(group.id), str(court.id)),
            "match.nextRound",
            {"round_number": group.current_round_number},
        )

    return group


async def start_planned_round(session: AsyncSession, group: Group) -> Group:
    """018-plan-then-start: the "Next Round" confirm step that follows
    `plan_next_round()` — pulls the current round's already-planned `queued`
    matches onto available courts. Rejects if the round isn't in
    `awaiting_start` (nothing planned yet, or it was already started) —
    same generation lock as planning, since this also mutates round state."""
    if group.scheduling_mechanism == "manual":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)

    courts = await _get_active_courts_ordered(session, group.id)
    if not courts:
        raise ApiError("NO_COURTS_AVAILABLE", status_code=400)

    await _lock_group_for_round_generation(session, group.id)
    if await get_round_phase(session, group) != "awaiting_start":
        raise ApiError("ROUND_NOT_PLANNED", status_code=409)

    pulled = await _pull_matches_onto_courts(session, group, courts)

    group.last_activity_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(group)

    for court_id, match in pulled:
        await _publish_rotation_updated(session, group.id, court_id, match)

    return group


async def swap_planned_match_players(
    session: AsyncSession,
    group: Group,
    match_id_1: uuid.UUID,
    roster_entry_id_1: uuid.UUID,
    match_id_2: uuid.UUID,
    roster_entry_id_2: uuid.UUID,
) -> None:
    """018-plan-then-start: swaps two players' match assignments for any two
    not-yet-terminal matches (`queued` or `in_progress`) — not just a
    planned-but-unstarted round (research.md follow-up: the admin also
    needs this once a round is already underway, e.g. an injury mid-round,
    for any of its matches that haven't finished yet). Gated per-match
    rather than per-round-phase for exactly that reason. Each participant
    row keeps its match and team-letter slot, only the `roster_entry_id`
    values trade places, so a swap never changes a match's A/B side balance
    or its court/order. Known limitation: `PairHistory` was already
    incremented for the pre-swap pairing at plan time
    (`_increment_pair_history`) and is deliberately NOT corrected here —
    recomputing it correctly for doubles' partner+opponent structure is its
    own scoped problem, and the fairness drift from an occasional manual
    swap is minor compared to that complexity. Publishes via
    `_publish_lineup_changed()` so any open scoreboard/control panel for
    either match refreshes in real time."""
    if match_id_1 == match_id_2:
        raise ApiError("VALIDATION_ERROR", status_code=400)

    if group.scheduling_mechanism == "manual":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)

    await _lock_group_for_round_generation(session, group.id)

    matches_result = await session.execute(
        select(Match).where(Match.id.in_((match_id_1, match_id_2)))
    )
    matches_by_id = {m.id: m for m in matches_result.scalars()}
    if len(matches_by_id) != 2 or any(m.group_id != group.id for m in matches_by_id.values()):
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    if any(m.status not in ("queued", "in_progress") for m in matches_by_id.values()):
        raise ApiError("MATCH_ALREADY_ENDED", status_code=409)

    result = await session.execute(
        select(MatchParticipant).where(MatchParticipant.match_id.in_((match_id_1, match_id_2)))
    )
    by_match: dict[uuid.UUID, list[MatchParticipant]] = {}
    for participant in result.scalars():
        by_match.setdefault(participant.match_id, []).append(participant)

    participant_1 = next(
        (p for p in by_match.get(match_id_1, []) if p.roster_entry_id == roster_entry_id_1), None
    )
    participant_2 = next(
        (p for p in by_match.get(match_id_2, []) if p.roster_entry_id == roster_entry_id_2), None
    )
    if participant_1 is None or participant_2 is None:
        raise ApiError("VALIDATION_ERROR", status_code=400)

    match_1_ids = {p.roster_entry_id for p in by_match.get(match_id_1, [])}
    match_2_ids = {p.roster_entry_id for p in by_match.get(match_id_2, [])}
    if roster_entry_id_1 in match_2_ids or roster_entry_id_2 in match_1_ids:
        raise ApiError("DUPLICATE_PARTICIPANT", status_code=400)

    participant_1.roster_entry_id, participant_2.roster_entry_id = (
        roster_entry_id_2,
        roster_entry_id_1,
    )
    await session.commit()
    await _publish_lineup_changed(session, group, list(matches_by_id.values()))


async def change_match_player(
    session: AsyncSession,
    group: Group,
    match_id: uuid.UUID,
    old_roster_entry_id: uuid.UUID,
    new_roster_entry_id: uuid.UUID,
) -> None:
    """018-plan-then-start: replaces one match participant with a specific,
    directly-chosen roster member — a substitute who wasn't necessarily
    playing anywhere else this round, as opposed to
    `swap_planned_match_players()`'s "trade with someone else's match".
    Allowed for any not-yet-terminal match (`queued`/`in_progress`), same
    scope as swap. If the match is currently `in_progress` (live on a
    court), the new player MUST NOT already be `in_progress` elsewhere —
    they can't physically be on two courts at once; no such restriction for
    a still-`queued` match, since a round-robin schedule already routinely
    lists the same person in several queued matches at once (only one gets
    pulled onto a court at a time). Same PairHistory caveat as
    `swap_planned_match_players()`. Publishes via `_publish_lineup_changed()`
    so any open scoreboard/control panel for the match refreshes in real
    time."""
    if group.scheduling_mechanism == "manual":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)

    await _lock_group_for_round_generation(session, group.id)

    match_result = await session.execute(select(Match).where(Match.id == match_id))
    match = match_result.scalar_one_or_none()
    if match is None or match.group_id != group.id:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    if match.status not in ("queued", "in_progress"):
        raise ApiError("MATCH_ALREADY_ENDED", status_code=409)

    participants_result = await session.execute(
        select(MatchParticipant).where(MatchParticipant.match_id == match_id)
    )
    participants = list(participants_result.scalars())
    target = next((p for p in participants if p.roster_entry_id == old_roster_entry_id), None)
    if target is None:
        raise ApiError("VALIDATION_ERROR", status_code=400)
    if any(p.roster_entry_id == new_roster_entry_id for p in participants):
        raise ApiError("DUPLICATE_PARTICIPANT", status_code=400)

    new_entry_result = await session.execute(
        select(RosterEntry.id).where(
            RosterEntry.id == new_roster_entry_id,
            RosterEntry.group_id == group.id,
            RosterEntry.status == "active",
        )
    )
    if new_entry_result.scalar_one_or_none() is None:
        raise ApiError("PARTICIPANT_NOT_ACTIVE", status_code=400)

    if match.status == "in_progress":
        busy_result = await session.execute(
            select(MatchParticipant.id)
            .join(Match, Match.id == MatchParticipant.match_id)
            .where(
                Match.group_id == group.id,
                Match.status == "in_progress",
                Match.id != match_id,
                MatchParticipant.roster_entry_id == new_roster_entry_id,
            )
        )
        if busy_result.scalar_one_or_none() is not None:
            raise ApiError("PARTICIPANT_ALREADY_PLAYING", status_code=400)

    target.roster_entry_id = new_roster_entry_id
    await session.commit()
    await _publish_lineup_changed(session, group, [match])


async def reorder_planned_matches(
    session: AsyncSession, group: Group, match_ids: Sequence[uuid.UUID]
) -> None:
    """018-plan-then-start: lets the admin drag-reorder the round's still-
    `queued` call-up order — same `created_at`-rewrite mechanism as
    `_shuffle_round_match_order` (random.shuffle), just admin-driven instead
    of random. Follow-up requirement: this now works whether the round is
    still fully `awaiting_start` or already `in_progress` (some matches
    already on courts, the rest still queued) — only a match that hasn't
    been pulled onto a court yet has a "call-up order" left to adjust, so
    the eligible set is exactly `status == "queued"`, not the whole round.
    `match_ids` MUST be a permutation of exactly that queued set — the
    whole point is reordering, not adding/removing matches, so anything
    else is rejected outright rather than guessed at. Broadcasts
    `match.nextRound` to every court afterward so a court currently peeking
    one of these matches as `next_up` refreshes to the new order — same
    reuse-as-refetch-trigger convention as `_publish_lineup_changed()`."""
    if group.scheduling_mechanism == "manual":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)

    await _lock_group_for_round_generation(session, group.id)

    result = await session.execute(
        select(Match.id).where(
            Match.group_id == group.id,
            Match.round_number == group.current_round_number,
            Match.status == "queued",
        )
    )
    queued_ids = set(result.scalars())
    if not queued_ids:
        raise ApiError("ROUND_NOT_PLANNED", status_code=409)
    if set(match_ids) != queued_ids or len(match_ids) != len(queued_ids):
        raise ApiError("VALIDATION_ERROR", status_code=400)

    base = datetime.now(UTC)
    for index, match_id in enumerate(match_ids):
        await session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(created_at=base + timedelta(microseconds=index))
        )
    await session.commit()

    for court in await _get_active_courts_ordered(session, group.id):
        await publish(
            court_channel(str(group.id), str(court.id)),
            "match.nextRound",
            {"round_number": group.current_round_number},
        )


async def round_is_complete(
    session: AsyncSession, group_id: uuid.UUID, round_number: int
) -> bool:
    """FR-028: a round is complete when every one of its matches has reached
    a terminal state (`completed` or `abandoned`) — vacuously true if the
    round has no matches at all (e.g. manual mode, or not yet generated)."""
    result = await session.execute(
        select(func.count())
        .select_from(Match)
        .where(
            Match.group_id == group_id,
            Match.round_number == round_number,
            Match.status.notin_(("completed", "abandoned")),
        )
    )
    return (result.scalar_one() or 0) == 0


async def advance_court_after_match_ends(session: AsyncSession, match: Match) -> Match | None:
    """FR-027: called once a match has reached a terminal state (by 007's
    scoring endpoints, once they exist) — pulls the next queued match for
    the same court, or leaves it idle ("等待下一輪") if none remain. Manual
    mode never queues anything, so this is a no-op there (research.md #10)."""
    if match.court_id is None:
        return None
    group_result = await session.execute(select(Group).where(Group.id == match.group_id))
    group = group_result.scalar_one()
    if group.scheduling_mechanism == "manual":
        return None
    return await pull_queued_match_for_court(
        session, match.group_id, match.round_number, match.court_id
    )


async def check_round_complete_and_maybe_auto_advance(session: AsyncSession, group: Group) -> bool:
    """FR-034/035: if Auto Next Round is on, the round has actually finished,
    and there's at least one court to generate for (FR-030 — zero courts
    MUST NOT even attempt generation), advance to the next round."""
    if group.scheduling_mechanism == "manual" or not group.auto_next_round:
        return False
    if not await round_is_complete(session, group.id, group.current_round_number):
        return False
    courts = await _get_active_courts_ordered(session, group.id)
    if not courts:
        return False
    await generate_next_round(session, group)
    return True


async def set_auto_next_round(session: AsyncSession, group: Group, enabled: bool) -> Group:
    """FR-016 (reverse direction): manual mode MUST NOT allow enabling Auto
    Next Round at all — the forward direction (switching INTO manual auto-
    disables it) is handled where `scheduling_mechanism` itself changes,
    per research.md #4."""
    if enabled and group.scheduling_mechanism == "manual":
        raise ApiError("AUTO_NEXT_ROUND_NOT_SUPPORTED_IN_MANUAL_MODE", status_code=400)
    group.auto_next_round = enabled
    await session.commit()
    await session.refresh(group)
    return group


async def build_schedule_snapshot(session: AsyncSession, group: Group) -> ScheduleResponse:
    """Assembles the admin-facing `GET /groups/{group_id}/schedule` read
    model per contracts/schedule-api.md — courts with their current match
    (or a `waiting_reason`), and the active roster with per-member schedule
    status for the manual-assign picker."""
    courts = await _get_active_courts_ordered(session, group.id)

    result = await session.execute(
        select(Match, MatchParticipant, RosterEntry.nickname)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(Match.group_id == group.id, Match.status == "in_progress")
    )
    matches_by_court: dict[uuid.UUID, tuple[Match, list[ParticipantSummary]]] = {}
    playing_roster_ids: set[uuid.UUID] = set()
    for match, participant, nickname in result.all():
        playing_roster_ids.add(participant.roster_entry_id)
        if match.court_id is None:
            continue
        court_entry = matches_by_court.setdefault(match.court_id, (match, []))
        court_entry[1].append(
            ParticipantSummary(
                roster_entry_id=str(participant.roster_entry_id),
                nickname=nickname,
                team=cast("Team", participant.team),
            )
        )

    court_statuses = []
    for court in courts:
        entry = matches_by_court.get(court.id)
        next_up: NextUpPreview | None = None
        if entry is not None:
            current_match = MatchSummary(
                match_id=str(entry[0].id),
                status=entry[0].status,
                participants=entry[1],
                score_a=entry[0].score_a,
                score_b=entry[0].score_b,
                serve=await _build_serve_station(session, entry[0]),
            )
            waiting_reason = None
        else:
            current_match = None
            waiting_reason = (
                "manual_assignment" if group.scheduling_mechanism == "manual" else "no_queued_match"
            )
            if group.scheduling_mechanism != "manual":
                queued = await peek_next_queued_match(
                    session, group.id, group.current_round_number, court.id
                )
                if queued is not None:
                    participants = await _match_participants_payload(session, queued.id)
                    next_up = NextUpPreview(
                        match_id=str(queued.id),
                        participants=[ParticipantSummary(**p) for p in participants],
                    )
        court_statuses.append(
            CourtScheduleStatus(
                court_id=str(court.id),
                name=court.name,
                current_match=current_match,
                waiting_reason=waiting_reason,
                next_up=next_up,
            )
        )

    roster_result = await session.execute(
        select(RosterEntry)
        .where(RosterEntry.group_id == group.id, RosterEntry.status == "active")
        .order_by(RosterEntry.joined_at)
    )
    roster_statuses = [
        RosterScheduleStatus(
            roster_entry_id=str(entry.id),
            nickname=entry.nickname,
            status=entry.status,
            wait_count=entry.wait_count,
            currently_playing=entry.id in playing_roster_ids,
            is_creator=entry.is_creator,
            is_guest=entry.member_id is None,
            # 026-match-record-friend-invite research.md #1 (redesign): the
            # "加好友" entry point now lives on the roster list (both the
            # member-schedule page and the admin schedule/roster tab, same
            # function/response) instead of next to live-match participants
            # — this is the one place it's populated within this function.
            member_id=str(entry.member_id) if entry.member_id else None,
        )
        for entry in roster_result.scalars()
    ]

    round_phase = (
        None if group.scheduling_mechanism == "manual" else await get_round_phase(session, group)
    )

    return ScheduleResponse(
        current_round_number=group.current_round_number,
        scheduling_mechanism=group.scheduling_mechanism,
        auto_next_round=group.auto_next_round,
        round_phase=round_phase,
        courts=court_statuses,
        roster=roster_statuses,
    )


async def build_round_matches_list(session: AsyncSession, group: Group) -> RoundMatchesResponse:
    """011-round-robin-scheduling: the admin-facing "本輪賽程清單" — unlike
    `build_schedule_snapshot()` above (which only shows each court's
    *current* match), this returns every match in the current round
    regardless of status (queued/in_progress/completed/abandoned), in
    generation order, so the admin can see the whole pre-generated
    round-robin schedule rather than just what's on court right now."""
    result = await session.execute(
        select(Match)
        .where(Match.group_id == group.id, Match.round_number == group.current_round_number)
        .order_by(Match.created_at)
    )
    matches = result.scalars().all()
    if not matches:
        return RoundMatchesResponse(round_number=group.current_round_number, matches=[])

    match_ids = [match.id for match in matches]
    participants_result = await session.execute(
        select(MatchParticipant, RosterEntry.nickname)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(MatchParticipant.match_id.in_(match_ids))
    )
    participants_by_match: dict[uuid.UUID, list[ParticipantSummary]] = {}
    for participant, nickname in participants_result.all():
        participants_by_match.setdefault(participant.match_id, []).append(
            ParticipantSummary(
                roster_entry_id=str(participant.roster_entry_id),
                nickname=nickname,
                team=cast("Team", participant.team),
            )
        )

    court_ids = {match.court_id for match in matches if match.court_id is not None}
    court_names: dict[uuid.UUID, str] = {}
    if court_ids:
        courts_result = await session.execute(
            select(Court.id, Court.name).where(Court.id.in_(court_ids))
        )
        court_names = {row.id: row.name for row in courts_result.all()}

    return RoundMatchesResponse(
        round_number=group.current_round_number,
        matches=[
            RoundMatchSummary(
                match_id=str(match.id),
                status=match.status,
                court_name=court_names.get(match.court_id) if match.court_id else None,
                participants=participants_by_match.get(match.id, []),
                score_a=match.score_a,
                score_b=match.score_b,
                winner_team=cast("Team | None", match.winner_team),
            )
            for match in matches
        ],
    )


async def manual_assign(
    session: AsyncSession,
    group: Group,
    court: Court,
    *,
    team_a: Sequence[uuid.UUID],
    team_b: Sequence[uuid.UUID],
) -> Match:
    """FR-011~015: manual scheduling's court-by-court assignment. Creates the
    match directly as `in_progress` (never `queued`) and zeroes the
    participants' `wait_count` immediately."""
    if group.scheduling_mechanism != "manual":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)

    all_ids = list(team_a) + list(team_b)
    if len(all_ids) != len(set(all_ids)):
        raise ApiError("DUPLICATE_PARTICIPANT", status_code=400)

    existing = await session.execute(
        select(Match.id).where(Match.court_id == court.id, Match.status == "in_progress")
    )
    if existing.scalar_one_or_none() is not None:
        raise ApiError("COURT_NOT_WAITING", status_code=409)

    roster_result = await session.execute(
        select(RosterEntry).where(
            RosterEntry.id.in_(all_ids), RosterEntry.group_id == group.id
        )
    )
    entries = {entry.id: entry for entry in roster_result.scalars()}
    for participant_id in all_ids:
        entry = entries.get(participant_id)
        if entry is None or entry.status != "active":
            raise ApiError("PARTICIPANT_NOT_ACTIVE", status_code=400)

    playing_result = await session.execute(
        select(MatchParticipant.roster_entry_id)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(Match.status == "in_progress", MatchParticipant.roster_entry_id.in_(all_ids))
    )
    if playing_result.scalars().first() is not None:
        raise ApiError("PARTICIPANT_ALREADY_PLAYING", status_code=400)

    match = await create_match_with_participants(
        session,
        group,
        court_id=court.id,
        round_number=group.current_round_number,
        status="in_progress",
        team_a=team_a,
        team_b=team_b,
    )
    await apply_wait_count_updates(session, group.id, all_ids)
    await session.commit()
    await session.refresh(match)
    await _publish_rotation_updated(session, group.id, court.id, match)
    return match


async def build_match_detail(
    session: AsyncSession, match: Match, team_a: Sequence[uuid.UUID], team_b: Sequence[uuid.UUID]
) -> MatchDetailResponse:
    all_ids = list(team_a) + list(team_b)
    result = await session.execute(select(RosterEntry).where(RosterEntry.id.in_(all_ids)))
    nicknames = {entry.id: entry.nickname for entry in result.scalars()}

    participants = [
        ParticipantSummary(roster_entry_id=str(pid), nickname=nicknames.get(pid, ""), team="A")
        for pid in team_a
    ] + [
        ParticipantSummary(roster_entry_id=str(pid), nickname=nicknames.get(pid, ""), team="B")
        for pid in team_b
    ]
    return MatchDetailResponse(
        match_id=str(match.id),
        status=match.status,
        participants=participants,
        target_score=match.target_score,
        deuce_threshold=match.deuce_threshold,
        cap_score=match.cap_score,
    )


async def _get_active_roster_ordered(session: AsyncSession, group_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(
        select(RosterEntry.id)
        .where(RosterEntry.group_id == group_id, RosterEntry.status == "active")
        .order_by(RosterEntry.joined_at)
    )
    return [row[0] for row in result.all()]


async def _get_paired_ids(session: AsyncSession, group_id: uuid.UUID) -> set[uuid.UUID]:
    result = await session.execute(
        select(Partnership.player_a_id, Partnership.player_b_id).where(
            Partnership.group_id == group_id
        )
    )
    paired: set[uuid.UUID] = set()
    for player_a_id, player_b_id in result.all():
        paired.add(player_a_id)
        paired.add(player_b_id)
    return paired


async def auto_pair_on_enter_fixed_partner(session: AsyncSession, group: Group) -> None:
    """FR-020: pair up every currently-unpaired active member by join order;
    an odd member out (the latest joiner among the unpaired) stays single."""
    active_ids = await _get_active_roster_ordered(session, group.id)
    paired = await _get_paired_ids(session, group.id)
    unpaired = [pid for pid in active_ids if pid not in paired]

    for i in range(0, len(unpaired) - 1, 2):
        session.add(
            Partnership(group_id=group.id, player_a_id=unpaired[i], player_b_id=unpaired[i + 1])
        )
    await session.flush()


async def clear_partnerships_on_exit(session: AsyncSession, group: Group) -> None:
    """FR-024: switching away from fixed_partner clears all Partnership rows
    (PairHistory is untouched — it lives independently of this table)."""
    await session.execute(delete(Partnership).where(Partnership.group_id == group.id))


async def manual_partnership_reassign(
    session: AsyncSession, group: Group, player_a_id: uuid.UUID, player_b_id: uuid.UUID
) -> None:
    """FR-021: any existing Partnership involving either player is dropped
    first (their old partners become unpaired), then the new pair is
    created."""
    if group.scheduling_mechanism != "fixed_partner":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)
    if player_a_id == player_b_id:
        raise ApiError("VALIDATION_ERROR", status_code=422)
    result = await session.execute(
        select(RosterEntry.status).where(
            RosterEntry.id.in_([player_a_id, player_b_id]), RosterEntry.group_id == group.id
        )
    )
    statuses = result.scalars().all()
    if len(statuses) != 2 or any(status != "active" for status in statuses):
        raise ApiError("VALIDATION_ERROR", status_code=422)

    await session.execute(
        delete(Partnership).where(
            Partnership.group_id == group.id,
            or_(
                Partnership.player_a_id.in_([player_a_id, player_b_id]),
                Partnership.player_b_id.in_([player_a_id, player_b_id]),
            ),
        )
    )
    session.add(Partnership(group_id=group.id, player_a_id=player_a_id, player_b_id=player_b_id))
    await session.flush()


async def dissolve_partnership(
    session: AsyncSession, group: Group, roster_entry_id: uuid.UUID
) -> None:
    """管理員手動拆散一組正式搭檔，讓雙方都變成落單。既有「點兩人互換」
    (`manual_partnership_reassign`) 只能透過「把其中一人配給第三人，原本的
    搭檔就自然落單」來間接拆散一組搭檔——現役成員只剩下這唯一一組搭檔、
    沒有第三人可以拿來觸發這個技巧時，管理員完全無法讓他們落單，這是本
    函式要補上的缺口。"""
    if group.scheduling_mechanism != "fixed_partner":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)
    result = await session.execute(
        select(Partnership).where(
            Partnership.group_id == group.id,
            or_(
                Partnership.player_a_id == roster_entry_id,
                Partnership.player_b_id == roster_entry_id,
            ),
        )
    )
    partnership = result.scalar_one_or_none()
    if partnership is None:
        raise ApiError("PARTNERSHIP_NOT_FOUND", status_code=404)
    await session.delete(partnership)
    await session.flush()


async def handle_member_joined(
    session: AsyncSession, group: Group, new_member: RosterEntry
) -> None:
    """FR-038 (adding to the roster doesn't touch the current round's already
    -generated matches — nothing to do here for that part, it's inherent in
    never having been selected) + FR-022 (fixed_partner auto-pairing, when
    applicable)."""
    if group.scheduling_mechanism != "fixed_partner":
        return
    active_ids = await _get_active_roster_ordered(session, group.id)
    paired = await _get_paired_ids(session, group.id)
    unpaired_existing = [
        pid for pid in active_ids if pid not in paired and pid != new_member.id
    ]
    if unpaired_existing:
        session.add(
            Partnership(
                group_id=group.id, player_a_id=unpaired_existing[0], player_b_id=new_member.id
            )
        )
        await session.flush()


async def remove_roster_entry_from_schedule(
    session: AsyncSession, group: Group, roster_entry_id: uuid.UUID
) -> None:
    """FR-039/040/041, shared by a member leaving and being kicked. Queued
    matches are always created with an exact participant count for the
    group's match_mode (no substitutes) — removing any one participant
    always breaks that count, so the whole match is abandoned rather than
    partially edited. In-progress matches are left completely untouched
    (FR-040); this never regenerates a round (FR-041), it only mutates the
    already-generated schedule for the current round."""
    result = await session.execute(
        select(Match.id)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(
            Match.group_id == group.id,
            Match.round_number == group.current_round_number,
            Match.status == "queued",
            MatchParticipant.roster_entry_id == roster_entry_id,
        )
    )
    match_ids = list(result.scalars().all())
    if not match_ids:
        return
    await session.execute(
        update(Match)
        .where(Match.id.in_(match_ids))
        .values(status="abandoned", ended_at=datetime.now(UTC))
    )
    await session.flush()


async def handle_member_left(
    session: AsyncSession, group: Group, entry: RosterEntry, *, new_status: str
) -> None:
    """FR-023: dissolving a fixed_partner Partnership when one side leaves
    (the other side simply becomes unpaired — no forced re-pairing). FR-039
    /040/041: convergence of the current round's schedule.

    Also decrements `current_member_count` — its only increment is
    `join_group`'s atomic `+1` (group/service.py), and until this fix
    nothing ever brought it back down on a leave/kick, so it only ever grew
    (a group whose members kept turning over would eventually hit
    max_members and start rejecting new joins with GROUP_FULL, even with
    barely anyone actually active). Atomic `UPDATE ... - 1` for the same
    reason `join_group`'s increment is atomic rather than a Python
    read-modify-write — this can run concurrently with a leave/kick/join
    elsewhere in the same group. `entry.status` was already confirmed
    "active" by both callers before this runs, so exactly one is
    guaranteed here per call — never over-decrements."""
    entry.status = new_status
    entry.left_at = datetime.now(UTC)
    if group.scheduling_mechanism == "fixed_partner":
        await session.execute(
            delete(Partnership).where(
                Partnership.group_id == group.id,
                or_(Partnership.player_a_id == entry.id, Partnership.player_b_id == entry.id),
            )
        )
    await remove_roster_entry_from_schedule(session, group, entry.id)
    await session.execute(
        update(Group)
        .where(Group.id == group.id)
        .values(current_member_count=Group.current_member_count - 1)
    )
    await session.flush()


async def kick_member(session: AsyncSession, group: Group, entry: RosterEntry) -> RosterEntry:
    """FR-037: admin-triggered removal — identical convergence rules to a
    member leaving on their own (FR-039/040/041), only the trigger differs.
    The creator's own roster entry MUST NOT be kickable — the admin page
    hides the button for that row, but that's UI-only, so the invariant is
    enforced here too rather than relying on the frontend never sending
    the request."""
    if entry.group_id != group.id:
        raise ApiError("ROSTER_ENTRY_NOT_FOUND", status_code=404)
    if entry.is_creator:
        raise ApiError("CANNOT_KICK_CREATOR", status_code=403)
    if entry.status != "active":
        raise ApiError("ROSTER_ENTRY_ALREADY_LEFT", status_code=409)

    await handle_member_left(session, group, entry, new_status="kicked")
    await session.commit()
    await session.refresh(entry)
    await session.refresh(group)

    await publish(
        group_notifications_channel(str(group.id)),
        "member.left",
        {"roster_entry_id": str(entry.id), "nickname": entry.nickname},
    )
    return entry


async def regenerate_guest_session_token(
    session: AsyncSession, group: Group, entry: RosterEntry
) -> RosterEntry:
    """Constitution IV: every link-type token (scoreboard, court control
    panels, join link) MUST be independently regenerable by the admin to
    invalidate a leaked copy — `guest_session_token` was the one exception
    (015-manual-add-guest's shareable `/guest-access/:token` link reuses
    this same field, so the gap became reachable, not just theoretical).
    Same token-generation call as `join_group()`'s guest branch, so a
    regenerated token is indistinguishable in shape/entropy from one
    issued at join time."""
    if entry.group_id != group.id:
        raise ApiError("ROSTER_ENTRY_NOT_FOUND", status_code=404)
    if entry.member_id is not None:
        raise ApiError("NOT_A_GUEST_ENTRY", status_code=400)
    if entry.status != "active":
        raise ApiError("ROSTER_ENTRY_ALREADY_LEFT", status_code=409)

    entry.guest_session_token = secrets.token_urlsafe(32)
    await session.commit()
    await session.refresh(entry)

    await publish(
        group_notifications_channel(str(group.id)),
        "link.regenerated",
        {
            "event": "link.regenerated",
            "group_id": str(group.id),
            "link_type": "guest_session",
            "roster_entry_id": str(entry.id),
        },
    )
    return entry


async def build_partnerships_snapshot(
    session: AsyncSession, group: Group
) -> PartnershipsResponse:
    if group.scheduling_mechanism != "fixed_partner":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)

    partnership_result = await session.execute(
        select(Partnership).where(Partnership.group_id == group.id)
    )
    partnerships = partnership_result.scalars().all()
    paired_ids = {p.player_a_id for p in partnerships} | {p.player_b_id for p in partnerships}

    roster_result = await session.execute(
        select(RosterEntry)
        .where(RosterEntry.group_id == group.id, RosterEntry.status == "active")
        .order_by(RosterEntry.joined_at)
    )
    roster_by_id = {entry.id: entry for entry in roster_result.scalars()}

    partnership_summaries = [
        PartnershipSummary(
            partnership_id=str(p.id),
            player_a=RosterSummary(
                roster_entry_id=str(p.player_a_id),
                nickname=roster_by_id[p.player_a_id].nickname
                if p.player_a_id in roster_by_id
                else "",
            ),
            player_b=RosterSummary(
                roster_entry_id=str(p.player_b_id),
                nickname=roster_by_id[p.player_b_id].nickname
                if p.player_b_id in roster_by_id
                else "",
            ),
        )
        for p in partnerships
    ]
    unpaired = [
        RosterSummary(roster_entry_id=str(entry_id), nickname=entry.nickname)
        for entry_id, entry in roster_by_id.items()
        if entry_id not in paired_ids
    ]
    return PartnershipsResponse(partnerships=partnership_summaries, unpaired=unpaired)


async def preview_random_partner_pairing(
    session: AsyncSession, group: Group
) -> TemporaryPairingsResponse:
    """017-fixed-partner-autofill FR-001: pure, side-effect-free preview of
    how the currently-unpaired active members would be randomly paired —
    never writes to `partnerships` (research.md #1). `PARTNER_SOURCE_MISMATCH`
    is deliberately a distinct error code from `SCHEDULING_MECHANISM_MISMATCH`
    (research.md #4): the latter means "this group isn't fixed_partner at
    all", the former means "it is, but partner_source isn't manual"."""
    if group.scheduling_mechanism != "fixed_partner":
        raise ApiError("SCHEDULING_MECHANISM_MISMATCH", status_code=409)
    if group.partner_source != "manual":
        raise ApiError("PARTNER_SOURCE_MISMATCH", status_code=409)

    active_ids = await _get_active_roster_ordered(session, group.id)
    paired = await _get_paired_ids(session, group.id)
    unpaired_ids = [pid for pid in active_ids if pid not in paired]
    pairs = random_pair_units(unpaired_ids)

    roster_result = await session.execute(
        select(RosterEntry).where(RosterEntry.id.in_(unpaired_ids))
    )
    roster_by_id = {entry.id: entry for entry in roster_result.scalars()}

    return TemporaryPairingsResponse(
        pairings=[
            TemporaryPairing(
                player_a=RosterSummary(
                    roster_entry_id=str(player_a), nickname=roster_by_id[player_a].nickname
                ),
                player_b=RosterSummary(
                    roster_entry_id=str(player_b), nickname=roster_by_id[player_b].nickname
                ),
            )
            for player_a, player_b in pairs
        ]
    )


# --- 007-live-scoreboard: 即時計分板與控制板 ---


def match_wins(score_x: int, score_y: int, target_score: int, cap_score: int) -> bool:
    """達標判定公式（research.md #2）——`deuce_threshold` 不參與運算：
    001 之兩組固定預設值（21/20/30、15/14/21）已交叉驗證此公式與其定義
    完全一致，無需額外讀取 deuce 門檻欄位。"""
    return score_x >= cap_score or (score_x >= target_score and score_x - score_y >= 2)


async def _fetch_match_for_court(
    session: AsyncSession, court: Court, match_id: uuid.UUID
) -> Match:
    result = await session.execute(select(Match).where(Match.id == match_id))
    match = result.scalar_one_or_none()
    if match is None or match.court_id != court.id:
        raise ApiError("MATCH_NOT_FOUND", status_code=404)
    return match


def _score_mutation_result(
    applied: bool,
    match: Match,
    score_event_id: uuid.UUID | None = None,
    serve: ServeStationInfo | None = None,
) -> ScoreMutationResult:
    return ScoreMutationResult(
        applied=applied,
        match_id=str(match.id),
        status=match.status,
        score_a=match.score_a,
        score_b=match.score_b,
        winner_team=cast("Team | None", match.winner_team),
        score_event_id=str(score_event_id) if score_event_id is not None else None,
        serve=serve,
    )


async def _publish_match_ended(
    session: AsyncSession, match: Match, court: Court, pulled: Match | None
) -> None:
    """contracts/ably-events.md `match.ended` — `waiting_reason` is `null`
    when `pulled` is not None (a `rotation.updated` is published right after,
    research.md #7), otherwise reports why the court is idle."""
    waiting_reason = None
    if pulled is None:
        group_result = await session.execute(
            select(Group.scheduling_mechanism).where(Group.id == match.group_id)
        )
        mechanism = group_result.scalar_one()
        waiting_reason = "manual_assignment" if mechanism == "manual" else "no_queued_match"
    await publish(
        court_channel(str(match.group_id), str(court.id)),
        "match.ended",
        {
            "match_id": str(match.id),
            "status": match.status,
            "winner_team": match.winner_team,
            "score_a": match.score_a,
            "score_b": match.score_b,
            "waiting_reason": waiting_reason,
        },
    )
    if pulled is not None:
        await _publish_rotation_updated(session, match.group_id, court.id, pulled)

    if match.status == "completed":
        # 018-group-leaderboard FR-003/contracts/ably-events.md: only an
        # actual win (never `abandoned`, which `_publish_match_ended` is
        # also called for from `end_match_early`) changes anyone's
        # standings, so only that case is worth telling open 戰績頁 to
        # re-fetch.
        await publish(
            group_notifications_channel(str(match.group_id)),
            "standings.updated",
            {"group_id": str(match.group_id)},
        )


async def _advance_other_idle_courts(
    session: AsyncSession, group: Group, round_number: int, *, exclude_court_id: uuid.UUID | None
) -> None:
    """011-round-robin-scheduling: a full round-robin schedule can leave a
    court idle only because every remaining candidate's players were busy
    elsewhere (FR-005's conflict guard, research.md #4) — that's a
    *temporary* block, not "nothing left this round" like the old
    court-count-sized schedule. Once any match ends, previously-blocked
    matches may become eligible, so every OTHER idle court in the group
    (not just the one whose match just ended) MUST be re-checked here;
    otherwise it would sit idle forever waiting for an event that only
    fires for the court whose match actually ended."""
    if group.scheduling_mechanism == "manual":
        return
    courts = await _get_active_courts_ordered(session, group.id)
    for court in courts:
        if court.id == exclude_court_id:
            continue
        current = await session.execute(
            select(Match.id).where(Match.court_id == court.id, Match.status == "in_progress")
        )
        if current.scalar_one_or_none() is not None:
            continue
        pulled = await pull_queued_match_for_court(session, group.id, round_number, court.id)
        if pulled is not None:
            await session.commit()
            await _publish_rotation_updated(session, group.id, court.id, pulled)


async def _advance_after_terminal(session: AsyncSession, match: Match) -> Match | None:
    """research.md #6: the two hooks 003 explicitly reserved for 007, called
    in order once a match has just reached a terminal state. Each hook
    manages its own commit boundary (003's existing convention, see
    `tests/integration/test_round_lifecycle_flow.py`)."""
    pulled = await advance_court_after_match_ends(session, match)
    await session.commit()
    group_result = await session.execute(select(Group).where(Group.id == match.group_id))
    group = group_result.scalar_one()
    await _advance_other_idle_courts(
        session, group, match.round_number, exclude_court_id=match.court_id
    )
    await check_round_complete_and_maybe_auto_advance(session, group)
    await session.refresh(match)
    return pulled


async def _advance_serve_state_and_snapshot(
    session: AsyncSession, match: Match, side: Team, score_a: int, score_b: int
) -> ScoreServeRecord:
    """030-score-serve-record FR-001~003 (research.md Decision 2). Called
    ONLY from `apply_score_delta()`'s `delta > 0` branch — `-1` MUST NOT
    call this (Decision 5). `score_a`/`score_b` are the POST-increment
    totals from that branch's `UPDATE ... RETURNING` — NOT `match.score_a`/
    `score_b`, which the ORM instance doesn't reflect until refreshed.

    Advances `match.serving_team`/`team_a_reference_server_id`/
    `team_b_reference_server_id` in place (side-out swap when `side` isn't
    the team that was already serving) and returns the immutable
    `ScoreServeRecord` snapshot to insert — caller still needs to set
    `score_event_id` and add it to the session."""
    team_a, team_b = await _match_participants_by_team(session, match.id)

    if side != match.serving_team:
        # Side-out: serve passes to `side`. That team's reference server
        # alternates to whichever of its (up to 2) participants doesn't
        # currently hold it (singles: the same lone participant, a no-op).
        participants = team_a if side == "A" else team_b
        current = (
            match.team_a_reference_server_id if side == "A" else match.team_b_reference_server_id
        )
        new_server = next((p for p in participants if p != current), current)
        match.serving_team = side
        if side == "A":
            match.team_a_reference_server_id = new_server
        else:
            match.team_b_reference_server_id = new_server

    station = _compute_station(
        cast(Team, match.serving_team),
        team_a,
        team_b,
        cast(uuid.UUID, match.team_a_reference_server_id),
        cast(uuid.UUID, match.team_b_reference_server_id),
        score_a,
        score_b,
    )
    return ScoreServeRecord(
        match_id=match.id,
        group_id=match.group_id,
        server_roster_entry_id=station.server_roster_entry_id,
        server_team=station.server_team,
        team_a_right_roster_entry_id=station.team_a_right_roster_entry_id,
        team_a_left_roster_entry_id=station.team_a_left_roster_entry_id,
        team_b_right_roster_entry_id=station.team_b_right_roster_entry_id,
        team_b_left_roster_entry_id=station.team_b_left_roster_entry_id,
    )


async def _remove_last_shot_placement_record(
    session: AsyncSession, match_id: uuid.UUID, side: Team
) -> None:
    """031-shot-placement-scoring FR-007: deletes the newest ShotPlacementRecord
    for this match+team, if any — a plain no-op when none exists (every
    simple-mode match, and a detailed-mode match with no prior point for
    this side). data-model.md: "刪除（單筆）"."""
    subquery = (
        select(ShotPlacementRecord.id)
        .where(ShotPlacementRecord.match_id == match_id, ShotPlacementRecord.team == side)
        .order_by(ShotPlacementRecord.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    await session.execute(delete(ShotPlacementRecord).where(ShotPlacementRecord.id == subquery))


async def apply_score_delta(
    session: AsyncSession,
    court: Court,
    match_id: uuid.UUID,
    side: Team,
    delta: int,
    source: str = "control_panel",
) -> ScoreMutationResult:
    """+1/-1（FR-003~007）。原子防呆（research.md #5）: 一句 `UPDATE ...
    WHERE status='in_progress' [AND score>0]` 同時達成 FR-005/006/006a；
    命中後才在同一函式內套用達標判定（FR-003），達標則另一句 `UPDATE`
    轉為 `completed` 並依序呼叫 003 既有 hook。

    032-score-then-record: a `+1` in detailed-scoring mode is applied here
    exactly like a plain one — score-then-record (see attach_shot_placement()
    below) never blocks the score itself on the scorer filling in landing
    detail. The returned ScoreMutationResult.score_event_id is what a caller
    then hands to attach_shot_placement()."""
    match = await _fetch_match_for_court(session, court, match_id)

    column = Match.score_a if side == "A" else Match.score_b
    conditions = [Match.id == match_id, Match.status == "in_progress"]
    if delta < 0:
        conditions.append(column > 0)

    stmt = (
        update(Match)
        .where(*conditions)
        .values(**{column.key: column + delta})
        .returning(Match.score_a, Match.score_b)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        await session.rollback()
        await session.refresh(match)
        return _score_mutation_result(applied=False, match=match)

    # Scoring is real usage, not idleness — resets the auto-disband clock
    # (apps/api/app/scheduler/auto_disband.py) same as join/edit/reauth.
    await session.execute(
        update(Group).where(Group.id == match.group_id).values(last_activity_at=datetime.now(UTC))
    )
    score_event_id = uuid.uuid4()
    session.add(
        ScoreEvent(
            id=score_event_id,
            match_id=match_id,
            group_id=match.group_id,
            side=side,
            delta=delta,
            score_a=row.score_a,
            score_b=row.score_b,
            source=source,
        )
    )

    if delta > 0:
        # 030-score-serve-record FR-001/FR-004: only a genuine point (+1)
        # advances the serve state and leaves a snapshot — `-1` MUST NOT.
        serve_record = await _advance_serve_state_and_snapshot(
            session, match, side, row.score_a, row.score_b
        )
        serve_record.score_event_id = score_event_id
        session.add(serve_record)
    else:
        # 031-shot-placement-scoring FR-007/research.md Decision 3: a
        # correction (-1) collapses the last point for this side — unconditional
        # (no `match.detailed_scoring_enabled` check needed): a simple-mode
        # match never has any ShotPlacementRecord to begin with, so this is a
        # harmless no-op there.
        await _remove_last_shot_placement_record(session, match_id, side)

        # feature/control-panel-scoreboard-style: a `-1` correcting the
        # point that just advanced the serve state (a side-out rotation
        # swap — see _advance_serve_state_and_snapshot()) previously left
        # match.serving_team/team_{a,b}_reference_server_id at their
        # POST-point values while only the score itself rolled back — a
        # stale, inconsistent combination that showed the wrong server
        # whenever the undone point was a side-out. 030-score-serve-record's
        # ScoreServeRecord rows are read-only history per its Clarifications
        # (never written or deleted by `-1`) — this only reads them to
        # restore match's own LIVE columns. `row.score_a`/`row.score_b` are
        # this correction's resulting totals; the historical point that
        # originally produced that exact score is exactly the state to
        # restore back to (robust to undoing several points in a row, not
        # just the single most recent one, since it matches by score
        # rather than by position in the history).
        prior = (
            await session.execute(
                select(ScoreServeRecord)
                .join(ScoreEvent, ScoreServeRecord.score_event_id == ScoreEvent.id)
                .where(
                    ScoreServeRecord.match_id == match_id,
                    ScoreEvent.score_a == row.score_a,
                    ScoreEvent.score_b == row.score_b,
                )
                .order_by(ScoreServeRecord.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if prior is not None:
            match.serving_team = prior.server_team
            match.team_a_reference_server_id = (
                prior.team_a_right_roster_entry_id
                if row.score_a % 2 == 0
                else prior.team_a_left_roster_entry_id
            )
            match.team_b_reference_server_id = (
                prior.team_b_right_roster_entry_id
                if row.score_b % 2 == 0
                else prior.team_b_left_roster_entry_id
            )
        # else: undoing all the way back past this match's first recorded
        # point — no earlier snapshot exists to restore from. If that
        # first point wasn't itself a side-out, match's serve columns were
        # never mutated for it and are already correct as-is; if it WAS, the
        # true pre-match-start random assignment (_initialize_serve_state())
        # was never persisted anywhere and can't be recovered here — a
        # narrow, accepted gap rather than something this correction can fix.

    await session.commit()
    await session.refresh(match)

    my_score, opp_score = (
        (match.score_a, match.score_b) if side == "A" else (match.score_b, match.score_a)
    )
    # feature/control-panel-scoreboard-style: also handed back on this same
    # response below (not just published) — None when the match ends this
    # point (no more serve state to show).
    serve_payload: dict[str, str | None] | None = None
    if match_wins(my_score, opp_score, match.target_score, match.cap_score):
        await session.execute(
            update(Match)
            .where(Match.id == match_id, Match.status == "in_progress")
            .values(status="completed", winner_team=side, ended_at=datetime.now(UTC))
        )
        await session.commit()
        await session.refresh(match)
        pulled = await _advance_after_terminal(session, match)
        await _publish_match_ended(session, match, court, pulled)
    else:
        # 029-serve-rotation-display FR-009/FR-010: `serve` rides the same
        # event as the score itself. `delta > 0` already has a freshly
        # computed station from `serve_record` above — reuse its fields
        # rather than calling `_compute_station()` a second time. `delta <
        # 0` never advances the serve state (research.md Decision 5), so
        # there's no `serve_record` in scope here; recompute fresh from the
        # unchanged serve state + corrected score instead (same helper
        # `court_live_state()` uses).
        if delta > 0:
            serve_payload = {
                "server_roster_entry_id": str(serve_record.server_roster_entry_id),
                "server_team": serve_record.server_team,
                "team_a_right_roster_entry_id": _opt_str(serve_record.team_a_right_roster_entry_id),
                "team_a_left_roster_entry_id": _opt_str(serve_record.team_a_left_roster_entry_id),
                "team_b_right_roster_entry_id": _opt_str(serve_record.team_b_right_roster_entry_id),
                "team_b_left_roster_entry_id": _opt_str(serve_record.team_b_left_roster_entry_id),
            }
        else:
            station = await _build_serve_station(session, match)
            serve_payload = (
                {
                    "server_roster_entry_id": station.server_roster_entry_id,
                    "server_team": station.server_team,
                    "team_a_right_roster_entry_id": station.team_a_right_roster_entry_id,
                    "team_a_left_roster_entry_id": station.team_a_left_roster_entry_id,
                    "team_b_right_roster_entry_id": station.team_b_right_roster_entry_id,
                    "team_b_left_roster_entry_id": station.team_b_left_roster_entry_id,
                }
                if station is not None
                else None
            )

        await publish(
            court_channel(str(match.group_id), str(court.id)),
            "match.scoreUpdated",
            {
                "match_id": str(match.id),
                "score_a": match.score_a,
                "score_b": match.score_b,
                "serve": serve_payload,
            },
        )

    return _score_mutation_result(
        applied=True,
        match=match,
        score_event_id=score_event_id,
        serve=ServeStationInfo(**serve_payload) if serve_payload is not None else None,
    )


async def undo_match_completion(
    session: AsyncSession, court: Court, match_id: uuid.UUID, side: Team
) -> ScoreMutationResult:
    """032-cancel-score: reverts a match that this exact winning point just
    completed, back to in_progress with that point removed — the "Cancel
    Score" action's counterpart to apply_score_delta(-1) specifically for
    the match-DECIDING point. A plain -1 can't do this: its UPDATE requires
    status='in_progress' (research.md #5), which this match no longer is
    the instant it wins — that's exactly the gap this closes.

    Completing a match can cascade well beyond this one row (pulling a new
    match onto this same court, other idle courts, even a whole new round
    auto-generating — see service.py's `_advance_after_terminal`), and most
    of that cascade is NOT safely reversible in general: round generation's
    PairHistory/wait_count bulk writes and its randomized pairing/serve
    state have no stored inverse, and another court's newly-pulled match
    may already have real gameplay on it by the time anyone tries to undo.
    So this only proceeds while the cascade "stayed local":
      - the group's round hasn't already advanced past this match's own
        round (ROUND_ALREADY_ADVANCED otherwise — reversing round
        generation isn't attempted at all), and
      - if a replacement match was pulled onto THIS SAME court afterward,
        it hasn't been touched yet (no points, no ShotPlacementRecord) —
        untouched, it's put back to queued so this match can retake the
        court; already started, this refuses too
        (NEXT_MATCH_ALREADY_STARTED), rather than risk discarding real
        data on that other match.
    Once safely back to in_progress, delegates the actual point removal to
    apply_score_delta(-1) unchanged — same floor guard, ScoreEvent,
    ShotPlacementRecord cleanup, and serve/score realtime publish as any
    other correction."""
    match = await _fetch_match_for_court(session, court, match_id)

    if match.status != "completed":
        raise ApiError("MATCH_NOT_COMPLETED", status_code=422)
    if match.winner_team != side:
        raise ApiError("SIDE_DID_NOT_WIN_THIS_MATCH", status_code=422)

    group_result = await session.execute(select(Group).where(Group.id == match.group_id))
    group = group_result.scalar_one()
    if group.current_round_number != match.round_number:
        raise ApiError("ROUND_ALREADY_ADVANCED", status_code=422)

    replacement_result = await session.execute(
        select(Match).where(
            Match.court_id == court.id,
            Match.status == "in_progress",
            Match.id != match.id,
        )
    )
    replacement = replacement_result.scalar_one_or_none()
    if replacement is not None:
        touched = replacement.score_a > 0 or replacement.score_b > 0
        if not touched:
            existing_event = await session.execute(
                select(ScoreEvent.id).where(ScoreEvent.match_id == replacement.id).limit(1)
            )
            touched = existing_event.scalar_one_or_none() is not None
        if touched:
            raise ApiError("NEXT_MATCH_ALREADY_STARTED", status_code=422)

        # Reverses pull_queued_match_for_court()'s own writes exactly —
        # nothing else (PairHistory, wait_count) is touched by a plain
        # pull, so there's nothing else to unwind here.
        await session.execute(
            update(Match)
            .where(Match.id == replacement.id)
            .values(
                court_id=None,
                status="queued",
                started_at=None,
                serving_team=None,
                team_a_reference_server_id=None,
                team_b_reference_server_id=None,
            )
        )

    await session.execute(
        update(Match)
        .where(Match.id == match_id)
        .values(status="in_progress", winner_team=None, ended_at=None)
    )
    await session.commit()
    await session.refresh(match)

    if replacement is not None:
        # Tells any other viewer of this court "the match here changed
        # back" — the same event a fresh pull onto this court always fires.
        await _publish_rotation_updated(session, match.group_id, court.id, match)

    return await apply_score_delta(session, court, match_id, side, -1, source="cancel_score")


# 032-out-of-bounds-by-match-mode: a singles rally is only "in" within the
# narrower singles sidelines, not the full doubles width — inset 0.46m from
# each doubles sideline (the court's own drawn border, data-model.md
# Decision 1's y=0/1) out of the 6.1m doubles width, same proportion as the
# singles sideline drawn on the court diagram itself.
_SINGLES_SIDELINE_INSET = 0.46 / 6.1

# 032-serve-fault-landing: a serve that lands on the CREDITED side's own
# half isn't necessarily a contradiction — it's exactly what a service
# fault looks like (the serve never legally reached the receiver's box), and
# the receiver (the credited side) wins the point immediately regardless of
# where the shuttle actually came down. These two bands, measured from each
# baseline, mark landings that could be such a fault rather than a genuine
# rally return-failure:
#   - short (never crossed the short service line): 1.98m from the net ->
#     4.72/13.4 from each baseline.
#   - long, DOUBLES ONLY (past the doubles long service line): 0.76/13.4
#     from each baseline. Singles serves are legal all the way to the
#     baseline, so there is no long-fault band for singles.
#   - the wrong service court: a serve goes diagonally, and each side's
#     right court is diagonal to the other side's right court, so the target
#     is the receiver's right court when the server's score is even and its
#     left court when odd. Only checked when the server's score is known.
_SHORT_SERVICE_LINE_INSET = 4.72 / 13.4
_LONG_SERVICE_LINE_INSET = 0.76 / 13.4


def _is_serve_fault_zone(
    landing_x: float,
    landing_y: float,
    side: str,
    is_doubles: bool,
    server_score: int | None,
) -> bool:
    """Whether an in-bounds landing on `side`'s (the receiver's) half is
    outside the serve's legal target. Teams face each other, so A's right
    court is the bottom half of the diagram (y > 0.5) and B's the top half
    (y < 0.5) — the station convention the scoreboard draws. The center
    line itself counts as in, for both courts. Mirrors the picker's
    isServeFaultZone()."""
    if side == "A":
        if _SHORT_SERVICE_LINE_INSET < landing_x < 0.5:
            return True
        if is_doubles and landing_x < _LONG_SERVICE_LINE_INSET:
            return True
    else:
        if 0.5 < landing_x < 1 - _SHORT_SERVICE_LINE_INSET:
            return True
        if is_doubles and landing_x > 1 - _LONG_SERVICE_LINE_INSET:
            return True
    if server_score is None:
        return False
    target_is_right_court = server_score % 2 == 0
    target_is_bottom = target_is_right_court == (side == "A")
    return landing_y < 0.5 if target_is_bottom else landing_y > 0.5


async def _serve_before_point(
    session: AsyncSession, score_event: ScoreEvent
) -> tuple[str, int] | None:
    """(serving team, that team's own score) going into the rally that
    `score_event` (a +1) credited — the score's parity says which service
    court the serve came from. Its own ScoreServeRecord can't tell — that
    snapshot is taken AFTER the point, and the winner always serves next, so
    its server_team is always the scorer. The team that served this rally
    is the one serving at the PRE-point
    score, i.e. the server_team of the latest earlier +1 that produced that
    exact score — the same match-by-score lookup apply_score_delta()'s -1
    uses to restore the serve state, so undone points in between don't
    confuse it. None for a match's first point (the pre-match serve
    assignment isn't persisted) — callers then skip any serve-based check,
    the same fallback the picker uses when it has no `servingTeam`."""
    before_a = score_event.score_a - (1 if score_event.side == "A" else 0)
    before_b = score_event.score_b - (1 if score_event.side == "B" else 0)
    server_team = (
        await session.execute(
            select(ScoreServeRecord.server_team)
            .join(ScoreEvent, ScoreServeRecord.score_event_id == ScoreEvent.id)
            .where(
                ScoreServeRecord.match_id == score_event.match_id,
                ScoreEvent.score_a == before_a,
                ScoreEvent.score_b == before_b,
                ScoreEvent.created_at <= score_event.created_at,
                ScoreEvent.id != score_event.id,
            )
            .order_by(ScoreEvent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if server_team is None:
        return None
    return server_team, before_a if server_team == "A" else before_b


async def attach_shot_placement(
    session: AsyncSession,
    court: Court,
    match_id: uuid.UUID,
    score_event_id: uuid.UUID,
    roster_entry_id: uuid.UUID | None,
    losing_roster_entry_id: uuid.UUID | None,
    landing_x: float | None,
    landing_y: float | None,
    *,
    ending_type: str | None = None,
) -> None:
    """032-score-then-record: records landing/player detail for a `+1`
    that's already been applied via a plain apply_score_delta() call —
    pressing "+" in detailed mode bumps the score immediately (same as
    simple mode) so match pace is never held up on this dialog; this
    function is what the picker's confirm() then calls, pinned to the exact
    ScoreEvent that "+" created (`score_event_id`) rather than "the most
    recent point", so a rapid string of points can never mismatch which
    point a given picker's answer lands on.

    032-optional-shot-placement-detail: every one of `roster_entry_id`,
    `losing_roster_entry_id`, and the `landing_x`/`landing_y` pair is
    independently optional — the scorer can confirm with only whatever they
    actually picked, rather than being forced to fill in all three before
    submitting anything at all. Whichever ARE supplied are still validated
    the same as before.

    Which side scored is no longer inferred from `roster_entry_id` (031's
    approach) — it's already fixed by the ScoreEvent itself (`.side`), so a
    supplied `roster_entry_id` is validated AGAINST that side rather than
    used to derive it, and the record's own `team` always comes from the
    ScoreEvent regardless of whether a player was specified.
    `losing_roster_entry_id`, if supplied, still must be on the other team —
    and, per official badminton rules, a supplied in-bounds landing must be
    on the side that actually failed to return the shuttle (i.e. NOT the
    credited side's own half), UNLESS that landing falls in a serve-fault
    band (_is_serve_fault_zone()) where the credited side could have won
    the point on a service fault instead, without ever having to return
    anything. Landing out of bounds leaves the return-failure question
    ambiguous too, so only the opposing-team constraint applies there. This
    landing-vs-credited-side check runs whenever a landing IS supplied,
    independent of whether a specific player was too.

    032-out-of-bounds-by-match-mode: "in bounds" itself depends on whether
    this match is singles or doubles (official rules use a narrower court
    width for singles) — derived from how many roster entries are actually
    on this match (2 -> singles, 4 -> doubles) rather than trusting the
    group's current match_mode, since that could have changed since this
    specific match was created.

    035-point-ending-type: `ending_type` is a fourth independently optional
    detail — how the rally ended. The picker pre-selects it from the landing
    where the landing leaves no doubt, but nothing is inferred HERE: what the
    request says is what gets stored, so a scorer who deliberately cleared
    the selection really does store "not recorded". Only two combinations
    are refused, the same spirit as the landing-vs-credited-side check —
    data that contradicts itself, never the scorer's judgement: a winner
    lands IN the court, a shot hit out lands OUT of it. 'net',
    'serve_fault' and 'other_error' say nothing about where the shuttle came
    down, and without a landing there is nothing to contradict. The check
    runs after the older landing check so that one keeps answering first.
    Being refused is costlier than it looks — the callers drop a failed
    request silently, losing the whole row — which is why the picker's own
    in/out judgement is pinned to this one by a shared vector table
    (035 data-model.md).

    Both serve-fault readings need the credited side to have been
    RECEIVING (_serve_before_point()): a fault always hands the point to
    the receiver, so when the credited side itself served, 'serve_fault' is
    refused (ENDING_TYPE_CONTRADICTS_SERVE) and a landing in its own
    serve-fault band is the plain landing contradiction again — the same
    gate as the picker's `isServeFault`. When the server is unknown (a
    match's first point) neither applies, as before."""
    match = await _fetch_match_for_court(session, court, match_id)

    if not match.detailed_scoring_enabled:
        raise ApiError("DETAILED_SCORING_NOT_ENABLED", status_code=422)

    if ending_type is not None and ending_type not in get_args(EndingType):
        raise ApiError("INVALID_ENDING_TYPE", status_code=422)

    if (landing_x is None) != (landing_y is None):
        raise ApiError("INVALID_LANDING_COORDINATES", status_code=422)
    if landing_x is not None and landing_y is not None:
        if not (-0.3 <= landing_x <= 1.3) or not (-0.3 <= landing_y <= 1.3):
            raise ApiError("INVALID_LANDING_COORDINATES", status_code=422)

    score_event_result = await session.execute(
        select(ScoreEvent).where(ScoreEvent.id == score_event_id, ScoreEvent.match_id == match_id)
    )
    score_event = score_event_result.scalar_one_or_none()
    if score_event is None:
        raise ApiError("SCORE_EVENT_NOT_FOUND", status_code=404)
    if score_event.delta <= 0:
        raise ApiError("SCORE_EVENT_NOT_A_POINT", status_code=422)

    existing_result = await session.execute(
        select(ShotPlacementRecord.id).where(ShotPlacementRecord.score_event_id == score_event_id)
    )
    if existing_result.scalar_one_or_none() is not None:
        raise ApiError("SHOT_PLACEMENT_ALREADY_RECORDED", status_code=422)

    participants_result = await session.execute(
        select(MatchParticipant.roster_entry_id, MatchParticipant.team).where(
            MatchParticipant.match_id == match_id,
        )
    )
    participant_rows = participants_result.all()
    team_by_entry: dict[uuid.UUID, str] = {entry_id: team for entry_id, team in participant_rows}
    is_singles = len(participant_rows) <= 2

    team: str | None = None
    if roster_entry_id is not None:
        team = team_by_entry.get(roster_entry_id)
        if team is None:
            raise ApiError("PARTICIPANT_NOT_IN_MATCH", status_code=422)
        if team != score_event.side:
            raise ApiError("SCORING_PLAYER_NOT_ON_CREDITED_SIDE", status_code=422)

    losing_team: str | None = None
    if losing_roster_entry_id is not None:
        losing_team = team_by_entry.get(losing_roster_entry_id)
        if losing_team is None:
            raise ApiError("PARTICIPANT_NOT_IN_MATCH", status_code=422)

    if team is not None and losing_team is not None and team == losing_team:
        raise ApiError("SCORING_AND_LOSING_PLAYER_SAME_TEAM", status_code=422)

    serve = await _serve_before_point(session, score_event)
    credited_side_served = serve is not None and serve[0] == score_event.side
    server_score = serve[1] if serve is not None else None

    if landing_x is not None and landing_y is not None:
        y_min, y_max = (
            (_SINGLES_SIDELINE_INSET, 1 - _SINGLES_SIDELINE_INSET) if is_singles else (0.0, 1.0)
        )
        in_bounds = 0 <= landing_x <= 1 and y_min <= landing_y <= y_max
        if in_bounds:
            landing_side = "A" if landing_x < 0.5 else "B"
            if score_event.side == landing_side and (
                credited_side_served
                or not _is_serve_fault_zone(
                    landing_x, landing_y, landing_side, not is_singles, server_score
                )
            ):
                raise ApiError("SCORING_PLAYER_WRONG_TEAM_FOR_LANDING", status_code=422)
        if (ending_type == "winner" and not in_bounds) or (
            ending_type == "out" and in_bounds
        ):
            raise ApiError("ENDING_TYPE_CONTRADICTS_LANDING", status_code=422)

    if ending_type == "serve_fault" and credited_side_served:
        raise ApiError("ENDING_TYPE_CONTRADICTS_SERVE", status_code=422)

    session.add(
        ShotPlacementRecord(
            score_event_id=score_event_id,
            match_id=match_id,
            group_id=match.group_id,
            roster_entry_id=roster_entry_id,
            losing_roster_entry_id=losing_roster_entry_id,
            team=cast(Team, score_event.side),
            landing_x=landing_x,
            landing_y=landing_y,
            ending_type=ending_type,
        )
    )
    await session.commit()


async def end_match_early(
    session: AsyncSession, court: Court, match_id: uuid.UUID
) -> ScoreMutationResult:
    """提前結束（FR-008~010）。原子防呆（research.md #5）: `UPDATE ...
    WHERE status='in_progress'` 轉 `abandoned`，`winner_team` 保持 `NULL`
    （research.md #1，即「不產生 MatchResult」）。"""
    match = await _fetch_match_for_court(session, court, match_id)

    stmt = (
        update(Match)
        .where(Match.id == match_id, Match.status == "in_progress")
        .values(status="abandoned", ended_at=datetime.now(UTC))
        .returning(Match.id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        await session.rollback()
        await session.refresh(match)
        return _score_mutation_result(applied=False, match=match)

    await session.commit()
    await session.refresh(match)
    pulled = await _advance_after_terminal(session, match)
    await _publish_match_ended(session, match, court, pulled)
    return _score_mutation_result(applied=True, match=match)


async def peek_next_queued_match(
    session: AsyncSession, group_id: uuid.UUID, round_number: int, court_id: uuid.UUID
) -> Match | None:
    """唯讀版本的「即將登場」預告查詢（research.md #11）——`WHERE` 子句與
    `pull_queued_match_for_court` 相同，但不帶 `with_for_update`、不修改
    `court_id`/`status`，避免與真正的領取路徑爭搶列鎖。`court_id` 參數目前
    未用於篩選（同一輪的排隊比賽尚未綁定場地），保留供未來場地優先序
    邏輯使用，並使函式簽章與「這是哪個場地的預告」語意保持明確。"""
    del court_id  # 見上——目前排隊比賽皆未綁定場地，暫不需要以此篩選
    result = await session.execute(
        select(Match)
        .where(
            Match.group_id == group_id,
            Match.round_number == round_number,
            Match.status == "queued",
            Match.court_id.is_(None),
        )
        .order_by(Match.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def court_live_state(session: AsyncSession, court: Court) -> CourtLiveState:
    """組出 `CourtLiveState`（data-model.md）——供公開 `GET .../state` 端點
    與管理頁場地控制區塊共用。`next_up` 由 US3 補上（`peek_next_queued_match`
    尚未接入時恆為 `None`）。"""
    group_result = await session.execute(
        select(Group.current_round_number, Group.scheduling_mechanism).where(
            Group.id == court.group_id
        )
    )
    round_number, mechanism = group_result.one()

    match_result = await session.execute(
        select(Match).where(Match.court_id == court.id, Match.status == "in_progress")
    )
    match = match_result.scalar_one_or_none()

    current_match: MatchLiveDetail | None = None
    waiting_reason: str | None = None
    next_up: NextUpPreview | None = None
    if match is not None:
        participants = await _match_participants_payload(session, match.id)
        current_match = MatchLiveDetail(
            match_id=str(match.id),
            status="in_progress",
            score_a=match.score_a,
            score_b=match.score_b,
            participants=[ParticipantSummary(**p) for p in participants],
            serve=await _build_serve_station(session, match),
            detailed_scoring_enabled=match.detailed_scoring_enabled,
        )
    else:
        waiting_reason = "manual_assignment" if mechanism == "manual" else "no_queued_match"
        if mechanism != "manual":
            queued = await peek_next_queued_match(session, court.group_id, round_number, court.id)
            if queued is not None:
                participants = await _match_participants_payload(session, queued.id)
                next_up = NextUpPreview(
                    match_id=str(queued.id),
                    participants=[ParticipantSummary(**p) for p in participants],
                )

    return CourtLiveState(
        court_id=str(court.id),
        round_number=round_number,
        current_match=current_match,
        waiting_reason=cast("WaitingReason | None", waiting_reason),
        next_up=next_up,
    )
