"""Schedule domain service layer: round generation, manual assignment, member
changes, and the abandon-matches hooks consumed by 001/002. Per
specs/003-schedule-rotation/plan.md and research.md."""

import random
import secrets
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

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
)
from app.domains.schedule.schemas import (
    CourtLiveState,
    CourtScheduleStatus,
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
    ScheduleResponse,
    ScoreMutationResult,
    Team,
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
    for batch in round_robin_pairs(roster_ids):
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


async def _generate_fixed_partner_matches(
    session: AsyncSession, group: Group, courts: list[Court], round_number: int
) -> None:
    """011-round-robin-scheduling FR-003/FR-008: every team plays every
    other team exactly once this round (research.md #1's circle method,
    applied to teams) — courts no longer bound how many matches get
    generated, and there's no wait_count-based team subset selection
    (research.md #5); ALL teams participate. `group.partner_source`
    decides where the teams come from (research.md #6)."""
    del courts

    if group.partner_source == "auto":
        teams = await compute_auto_partner_teams_for_round(session, group.id)
    else:
        teams = await _get_active_partnership_teams(session, group.id)

    for batch in round_robin_pairs(teams):
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
    cheapest way to randomize both without a dedicated ordering column."""
    result = await session.execute(
        select(Match.id).where(Match.group_id == group_id, Match.round_number == round_number)
    )
    match_ids = list(result.scalars())
    if len(match_ids) < 2:
        return

    random.shuffle(match_ids)
    base = datetime.now(UTC)
    for index, match_id in enumerate(match_ids):
        await session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(created_at=base + timedelta(microseconds=index))
        )


async def generate_next_round(session: AsyncSession, group: Group) -> Group:
    """Round generation entry point — both the manual "Next Round" button
    (FR-031~033) and Auto Next Round funnel through here. Force-abandons
    whatever is still queued/in_progress (a no-op if the round already
    finished naturally), then dispatches per `scheduling_mechanism`: for
    algorithmic modes, creates the round's matches as `queued` and
    immediately pulls one per available court (research.md #7); manual mode
    generates nothing (FR-033) — courts simply show "waiting for admin"."""
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
        await _generate_fixed_partner_matches(session, group, courts, group.current_round_number)
    else:
        raise ApiError("VALIDATION_ERROR", status_code=400)

    if group.scheduling_mechanism != "manual":
        await _shuffle_round_match_order(session, group.id, group.current_round_number)

    pulled: list[tuple[uuid.UUID, Match]] = []
    if group.scheduling_mechanism != "manual":
        for court in courts:
            match = await pull_queued_match_for_court(
                session, group.id, group.current_round_number, court.id
            )
            if match is not None:
                pulled.append((court.id, match))

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
        )
        for entry in roster_result.scalars()
    ]

    return ScheduleResponse(
        current_round_number=group.current_round_number,
        scheduling_mechanism=group.scheduling_mechanism,
        auto_next_round=group.auto_next_round,
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


def _score_mutation_result(applied: bool, match: Match) -> ScoreMutationResult:
    return ScoreMutationResult(
        applied=applied,
        match_id=str(match.id),
        status=match.status,
        score_a=match.score_a,
        score_b=match.score_b,
        winner_team=cast("Team | None", match.winner_team),
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
    轉為 `completed` 並依序呼叫 003 既有 hook。"""
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
    session.add(
        ScoreEvent(
            match_id=match_id,
            group_id=match.group_id,
            side=side,
            delta=delta,
            score_a=row.score_a,
            score_b=row.score_b,
            source=source,
        )
    )

    await session.commit()
    await session.refresh(match)

    my_score, opp_score = (
        (match.score_a, match.score_b) if side == "A" else (match.score_b, match.score_a)
    )
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
        await publish(
            court_channel(str(match.group_id), str(court.id)),
            "match.scoreUpdated",
            {"match_id": str(match.id), "score_a": match.score_a, "score_b": match.score_b},
        )

    return _score_mutation_result(applied=True, match=match)


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
