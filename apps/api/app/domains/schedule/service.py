"""Schedule domain service layer: round generation, manual assignment, member
changes, and the abandon-matches hooks consumed by 001/002. Per
specs/003-schedule-rotation/plan.md and research.md."""

import math
import random
import secrets
import statistics
import uuid
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import ValidationError
from sqlalchemy import ColumnElement, Exists, Select, delete, exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.errors import ApiError
from app.core.realtime import court_channel, group_notifications_channel, publish
from app.domains.court.models import Court
from app.domains.group.models import Group, RoundHistory
from app.domains.roster.models import RosterEntry, RosterRestPeriod
from app.domains.schedule.algorithms import (
    PlayerHistory,
    RestPeriod,
    pair_doubles_matches,
    pick_next_match,
    player_histories,
    random_pair_units,
    round_robin_pairs,
    stage1_select_players,
    stage2_pair_players,
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
    RestEffect,
    RosterScheduleStatus,
    RosterSummary,
    RoundMatchesResponse,
    RoundMatchSummary,
    RoundPhase,
    ScheduleResponse,
    ScoreMutationResult,
    ServeStationInfo,
    SubstitutionPreview,
    Team,
    TemporaryPairing,
    TemporaryPairingsResponse,
    WaitingOnRest,
    WaitingReason,
)
from app.sports import catalog, registry, scoring
from app.sports.plugin import PluginEventContext, PointDetail, SpineEventContext
from app.sports.presentation import SportSummary

_ACTIVE_MATCH_STATUSES = ("queued", "in_progress")

# 037-rest-ready-toggle: a resting player is still in the group (status
# "active") but isn't picked to play. Every "who can play next" query adds
# this; queries about who is in the group, or who partners whom, don't
# (research.md Decision 2).
_IS_READY = RosterEntry.resting_since.is_(None)


async def abandon_group_matches(session: AsyncSession, group_id: uuid.UUID) -> None:
    """Implements 001's `AbandonMatchesHook` — called from `disband_group()`.
    Abandons every not-yet-terminal match for the whole group. PairHistory is
    untouched: a match is counted when it takes a court, so a queued match
    abandoned here was never counted, and one abandoned mid-play really was
    played."""
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
    one round). Two bulk UPDATEs, not a per-row Python loop. A resting
    player isn't waiting, so their count stays frozen (037 FR-024)."""
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
            _IS_READY,
            RosterEntry.id.notin_(selected),
        )
        .values(wait_count=func.coalesce(RosterEntry.wait_count, 0) + 1)
    )


async def _record_pair_history(
    session: AsyncSession,
    group_id: uuid.UUID,
    team_a: Sequence[uuid.UUID],
    team_b: Sequence[uuid.UUID],
    delta: int = 1,
) -> None:
    """research.md #5: every unordered pair among the match's players gets
    `delta` on pair_count, and same-side pairs also on teammate_count.
    Called when a match takes a court (`_start_match()`), not when it is
    planned, so a planned match that never gets played (round ended early,
    member left) leaves no trace. `delta=-1` undoes a start, for a match
    put back in the queue or a lineup changed mid-match."""
    teams = [(pid, "A") for pid in team_a] + [(pid, "B") for pid in team_b]
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            (id_i, team_i), (id_j, team_j) = teams[i], teams[j]
            lo, hi = sorted((id_i, id_j))
            teammate_delta = delta if team_i == team_j else 0
            if delta > 0:
                stmt = pg_insert(PairHistory).values(
                    group_id=group_id,
                    player_lo_id=lo,
                    player_hi_id=hi,
                    pair_count=delta,
                    teammate_count=teammate_delta,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["group_id", "player_lo_id", "player_hi_id"],
                    set_={
                        "pair_count": PairHistory.pair_count + delta,
                        "teammate_count": PairHistory.teammate_count + teammate_delta,
                    },
                )
                await session.execute(stmt)
            else:
                await session.execute(
                    update(PairHistory)
                    .where(
                        PairHistory.group_id == group_id,
                        PairHistory.player_lo_id == lo,
                        PairHistory.player_hi_id == hi,
                    )
                    .values(
                        pair_count=PairHistory.pair_count + delta,
                        teammate_count=PairHistory.teammate_count + teammate_delta,
                    )
                )


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


async def _match_participants_by_team(
    session: AsyncSession, match_id: uuid.UUID
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Returns (team_a_roster_entry_ids, team_b_roster_entry_ids) for a
    match."""
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


async def _start_match(session: AsyncSession, match: Match, court_id: uuid.UUID | None) -> None:
    """Puts a match on `court_id` as `in_progress`: the one place a match
    starts, whether it was queued (`pull_queued_match_for_court()`) or
    created straight onto a court (`create_match_with_participants()`).
    Also where the match enters PairHistory. Flushes, never commits.

    043: whatever the sport type sets up at the start (badminton: the serve
    state, 030) is the plugin's `on_match_start()`."""
    match.court_id = court_id
    match.status = "in_progress"
    match.started_at = datetime.now(UTC)
    await registry.get(match.type_key).on_match_start(session, match, ())
    team_a, team_b = await _match_participants_by_team(session, match.id)
    await _record_pair_history(session, match.group_id, team_a, team_b)
    await session.flush()


async def create_match_with_participants(
    session: AsyncSession,
    group: Group,
    *,
    court_id: uuid.UUID | None,
    round_number: int,
    status: str,
    team_a: Sequence[uuid.UUID],
    team_b: Sequence[uuid.UUID],
    queue_position: int | None = None,
) -> Match:
    """Writes `matches` + `match_participants`, applying the group's current
    Match Scoring Settings as an immutable snapshot (spec FR-012, 001's
    data-model.md §2); a match created `in_progress` is started on
    `court_id` right away, which also records its PairHistory. Flushes but
    does NOT commit — this is a building block called in a loop by
    `generate_next_round()`, which commits once for the whole round
    (atomicity); callers using it standalone (e.g. `manual_assign()`) are
    responsible for their own commit."""
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=round_number,
        status="queued",
        target_score=group.target_score,
        deuce_threshold=group.deuce_threshold,
        cap_score=group.cap_score,
        # 031-shot-placement-scoring research.md Decision 6: snapshotted here
        # only — pull_queued_match_for_court() merely transitions an
        # already-created row to in_progress, this value is already fixed.
        detailed_scoring_enabled=group.detailed_scoring_enabled,
        queue_position=queue_position,
        # 043 data-model §3: the sport and its common parameters, fixed for
        # the life of the match whatever the group changes later.
        sport_key=group.sport_key,
        type_key=group.type_key,
        sport_name=group.sport_name,
        team_size=group.team_size,
        end_mode=group.end_mode,
        win_by=group.win_by,
        allow_draw=group.allow_draw,
        score_steps=list(group.score_steps),
        type_params=dict(group.type_params),
    )
    session.add(match)
    await session.flush()

    participants = [
        MatchParticipant(match_id=match.id, roster_entry_id=pid, team="A") for pid in team_a
    ] + [MatchParticipant(match_id=match.id, roster_entry_id=pid, team="B") for pid in team_b]
    session.add_all(participants)
    await session.flush()

    if status == "in_progress":
        await _start_match(session, match, court_id)
    elif status != "queued":
        match.status = status
        match.court_id = court_id
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
    """Ready players only (037) — both callers pick who plays next."""
    result = await session.execute(
        select(RosterEntry.id, RosterEntry.wait_count, RosterEntry.joined_at).where(
            RosterEntry.group_id == group_id, RosterEntry.status == "active", _IS_READY
        )
    )
    return [(row.id, row.wait_count, row.joined_at) for row in result.all()]


async def _get_active_roster_ids(session: AsyncSession, group_id: uuid.UUID) -> list[uuid.UUID]:
    """011-round-robin-scheduling: the algorithmic modes' full round-robin
    generation includes every active member — no wait_count-based subset
    selection (research.md #5), unlike `_get_active_roster_for_selection`
    above, which `stage1_select_players` still needs for fair_rotation
    doubles (untouched by this feature). Ready players only (037)."""
    result = await session.execute(
        select(RosterEntry.id)
        .where(RosterEntry.group_id == group_id, RosterEntry.status == "active", _IS_READY)
        # Without an ORDER BY the order was whatever the heap returned, and
        # the round-robin generators' anchors and tie-breaks all depend on it.
        .order_by(RosterEntry.joined_at, RosterEntry.id)
    )
    return list(result.scalars())


# frozenset({player, player}) -> [teammate count, opponent count]
PairCounts = dict[frozenset[uuid.UUID], list[int]]


async def _load_pair_counts(session: AsyncSession, group_id: uuid.UUID) -> PairCounts:
    result = await session.execute(select(PairHistory).where(PairHistory.group_id == group_id))
    return {
        frozenset((row.player_lo_id, row.player_hi_id)): [
            row.teammate_count,
            row.pair_count - row.teammate_count,
        ]
        for row in result.scalars()
    }


def _teammate_cost(counts: PairCounts) -> Callable[[uuid.UUID, uuid.UUID], int]:
    def cost(a: uuid.UUID, b: uuid.UUID) -> int:
        return counts.get(frozenset((a, b)), [0, 0])[0]

    return cost


def _opponent_cost(counts: PairCounts) -> Callable[[uuid.UUID, uuid.UUID], int]:
    def cost(a: uuid.UUID, b: uuid.UUID) -> int:
        return counts.get(frozenset((a, b)), [0, 0])[1]

    return cost


def _count_planned_match(
    counts: PairCounts, team_a: Sequence[uuid.UUID], team_b: Sequence[uuid.UUID]
) -> None:
    """Adds a just-planned match to an in-memory `PairCounts`, so a
    generator building several matches in one go sees its own earlier
    matches (the table itself only changes once a match starts)."""
    for team in (team_a, team_b):
        for i in range(len(team)):
            for j in range(i + 1, len(team)):
                counts.setdefault(frozenset((team[i], team[j])), [0, 0])[0] += 1
    for a in team_a:
        for b in team_b:
            counts.setdefault(frozenset((a, b)), [0, 0])[1] += 1


async def _get_player_histories(
    session: AsyncSession, group_id: uuid.UUID
) -> dict[uuid.UUID, PlayerHistory]:
    """roster_entry_id -> `PlayerHistory` (matches played, matches sat out
    since their last one, current back-to-back run), from every match of
    the group that went on court — including those abandoned mid-play,
    since the players were on court. Rest is counted in matches, not
    minutes (`player_histories()`).

    037-rest-ready-toggle: matches that started while a player was resting
    aren't counted as rest, and `played` includes `played_credit`. This is
    the only place credit enters scheduling (research.md Decisions 3, 4).
    Someone who has never played stays absent — they are a newcomer."""
    result = await session.execute(
        select(Match.id, Match.started_at, Match.ended_at, MatchParticipant.roster_entry_id)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(Match.group_id == group_id, Match.started_at.is_not(None))
    )
    matches: dict[uuid.UUID, tuple[datetime, datetime | None, list[uuid.UUID]]] = {}
    for match_id, started_at, ended_at, roster_entry_id in result.all():
        matches.setdefault(match_id, (started_at, ended_at, []))[2].append(roster_entry_id)

    rest_periods: dict[uuid.UUID, list[RestPeriod]] = {}
    periods_result = await session.execute(
        select(
            RosterRestPeriod.roster_entry_id, RosterRestPeriod.started_at, RosterRestPeriod.ended_at
        ).where(RosterRestPeriod.group_id == group_id)
    )
    for roster_entry_id, started_at, ended_at in periods_result.all():
        rest_periods.setdefault(roster_entry_id, []).append((started_at, ended_at))
    entries_result = await session.execute(
        select(RosterEntry.id, RosterEntry.resting_since, RosterEntry.played_credit).where(
            RosterEntry.group_id == group_id,
            or_(RosterEntry.resting_since.is_not(None), RosterEntry.played_credit > 0),
        )
    )
    credits: dict[uuid.UUID, int] = {}
    for roster_entry_id, resting_since, played_credit in entries_result.all():
        if resting_since is not None:
            rest_periods.setdefault(roster_entry_id, []).append((resting_since, None))
        if played_credit:
            credits[roster_entry_id] = played_credit

    histories = player_histories(list(matches.values()), rest_periods)
    for roster_entry_id, credit in credits.items():
        history = histories.get(roster_entry_id)
        if history is not None:
            histories[roster_entry_id] = history._replace(played=history.played + credit)
    return histories


# Whether a match counts as part of someone's round: everything except a
# match abandoned before it ever took a court. A match ended early
# ("提前結束") is abandoned too, but its players did play — counting it as
# nothing listed them as "not scheduled this round", could hand them a
# rematch as late joiners, and made them look like idle substitutes.
_COUNTS_TOWARD_ROUND = or_(Match.status != "abandoned", Match.started_at.is_not(None))

# Call-up order of a round's queued matches. created_at only breaks ties
# between rows written before queue_position existed.
_QUEUE_ORDER = (Match.queue_position.asc().nulls_last(), Match.created_at, Match.id)


def _busy_participants_subquery(group_id: uuid.UUID):  # type: ignore[no-untyped-def]
    return (
        select(MatchParticipant.roster_entry_id)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(Match.group_id == group_id, Match.status == "in_progress")
    ).scalar_subquery()


@dataclass(frozen=True)
class NextMatchChoice:
    """The match a freed court takes next, and — 037-rest-ready-toggle —
    who substitutes for which resting player when it's called."""

    match: Match
    # (resting player, substitute) pairs, applied only by the real pull.
    substitutions: tuple[tuple[uuid.UUID, uuid.UUID], ...] = ()


def _has_resting_participant() -> Exists:
    """037: correlated EXISTS — the match has a resting player in it."""
    return exists(
        select(MatchParticipant.id)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(MatchParticipant.match_id == Match.id, RosterEntry.resting_since.is_not(None))
    )


def _substitutes_for_rest(mechanism: str, match_mode: str) -> bool:
    """037 FR-016／FR-018: fair-rotation doubles and individual-mixed call a
    substitute for a resting player; singles round-robin and fixed partners
    keep the match — it is that pairing, and a substitute would hand
    someone else a repeat."""
    return match_mode == "doubles" and mechanism in ("fair_rotation", "individual_mixed")


async def _choose_next_queued_match(
    session: AsyncSession, group_id: uuid.UUID, round_number: int, *, lock: bool
) -> NextMatchChoice | None:
    """The match a freed court should take next, shared by the real pull
    and the read-only "next up" preview so the preview never promises a
    different match than the one that actually gets called.

    011-round-robin-scheduling research.md #4: a full round-robin schedule
    puts the same player in several queued matches at once, so candidates
    with anyone already `in_progress` elsewhere in the group are skipped —
    otherwise the same person could end up "playing" on two courts at once.
    Among the rest, `pick_next_match()` prefers the match whose players
    have sat out the most matches since their last one, falling back to
    call-up order once everyone has sat out at least
    `RESTED_AFTER_MATCHES`.

    037-rest-ready-toggle (research.md Decision 5): matches with a resting
    player are skipped too, so everything else goes first. Only when they
    are all that's left does the mechanism matter: substitutes for a
    fair-rotation doubles / individual-mixed match, in call-up order, the
    first one every resting player of which can be replaced by someone free
    right now; otherwise nothing, and the match waits for them."""

    def queued_and_free(*conditions: ColumnElement[bool]) -> Select[tuple[Match]]:
        query = (
            select(Match)
            .where(
                Match.group_id == group_id,
                Match.round_number == round_number,
                Match.status == "queued",
                Match.court_id.is_(None),
                ~exists(
                    select(MatchParticipant.id).where(
                        MatchParticipant.match_id == Match.id,
                        MatchParticipant.roster_entry_id.in_(
                            _busy_participants_subquery(group_id)
                        ),
                    )
                ),
                *conditions,
            )
            .order_by(*_QUEUE_ORDER)
        )
        return query.with_for_update(skip_locked=True) if lock else query

    candidates = list(
        (await session.execute(queued_and_free(~_has_resting_participant()))).scalars()
    )
    if not candidates:
        held = list((await session.execute(queued_and_free(_has_resting_participant()))).scalars())
        return await _choose_substituted_match(session, group_id, held) if held else None
    if len(candidates) == 1:
        return NextMatchChoice(candidates[0])

    participants_result = await session.execute(
        select(MatchParticipant.match_id, MatchParticipant.roster_entry_id).where(
            MatchParticipant.match_id.in_([m.id for m in candidates])
        )
    )
    players_by_match: dict[uuid.UUID, list[uuid.UUID]] = {}
    for match_id, roster_entry_id in participants_result.all():
        players_by_match.setdefault(match_id, []).append(roster_entry_id)

    chosen = pick_next_match(
        [(m, players_by_match.get(m.id, [])) for m in candidates],
        await _get_player_histories(session, group_id),
    )
    return NextMatchChoice(chosen) if chosen is not None else None


async def _choose_substituted_match(
    session: AsyncSession, group_id: uuid.UUID, held: list[Match]
) -> NextMatchChoice | None:
    """037: the first of `held` (in call-up order) whose every resting player
    gets a different substitute free to play now — or None if the mechanism
    keeps such matches, or none can be filled. Never half-substitutes."""
    group = (await session.execute(select(Group).where(Group.id == group_id))).scalar_one()
    if not _substitutes_for_rest(group.scheduling_mechanism, group.match_mode):
        return None
    resting_result = await session.execute(
        select(MatchParticipant.match_id, MatchParticipant.roster_entry_id)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(
            MatchParticipant.match_id.in_([m.id for m in held]),
            RosterEntry.resting_since.is_not(None),
        )
        .order_by(RosterEntry.joined_at, RosterEntry.id)
    )
    resting_by_match: dict[uuid.UUID, list[uuid.UUID]] = {}
    for match_id, roster_entry_id in resting_result.all():
        resting_by_match.setdefault(match_id, []).append(roster_entry_id)
    appearances = await _round_appearances(session, group)
    for match in held:
        chosen: list[tuple[uuid.UUID, uuid.UUID]] = []
        for resting_id in resting_by_match[match.id]:
            substitute = await _pick_substitute(
                session,
                group,
                match.id,
                resting_id,
                appearances,
                must_be_free=True,
                exclude=[sub for _resting, sub in chosen],
            )
            if substitute is None:
                break
            chosen.append((resting_id, substitute))
        else:
            return NextMatchChoice(match, tuple(chosen))
    return None


async def pull_queued_match_for_court(
    session: AsyncSession, group_id: uuid.UUID, round_number: int, court_id: uuid.UUID
) -> Match | None:
    """FR-027: binds the next queued, court-unassigned match in this round
    to `court_id` and starts it. Shared by round generation's initial
    distribution (research.md #7) and `advance_court_after_match_ends`
    (US3) — same "pull from the queue" mechanism either way. Which match is
    "next" is `_choose_next_queued_match()`'s call; if none is eligible
    yet, returns None (court waits).

    037: a call-up with substitutes takes the group lock and chooses again
    under it, so two courts freeing at once can't seat the same substitute
    twice (continuous rotation seats players under the same lock). The
    ordinary path takes no extra lock."""
    choice = await _choose_next_queued_match(session, group_id, round_number, lock=True)
    if choice is not None and choice.substitutions:
        await session.execute(select(Group.id).where(Group.id == group_id).with_for_update())
        choice = await _choose_next_queued_match(session, group_id, round_number, lock=True)
    if choice is None:
        return None
    if choice.substitutions:
        await _apply_substitutions(session, group_id, choice)
    await _start_match(session, choice.match, court_id)
    return choice.match


async def _apply_substitutions(
    session: AsyncSession, group_id: uuid.UUID, choice: NextMatchChoice
) -> None:
    """037: puts each substitute in the resting player's seat (same team).
    In fair rotation the substitute counts as picked, as when substituting
    for a leaver (FR-027); the resting player's wait count stays frozen."""
    mechanism = (
        await session.execute(select(Group.scheduling_mechanism).where(Group.id == group_id))
    ).scalar_one()
    for resting_id, substitute_id in choice.substitutions:
        await session.execute(
            update(MatchParticipant)
            .where(
                MatchParticipant.match_id == choice.match.id,
                MatchParticipant.roster_entry_id == resting_id,
            )
            .values(roster_entry_id=substitute_id)
        )
        if mechanism == "fair_rotation":
            await session.execute(
                update(RosterEntry).where(RosterEntry.id == substitute_id).values(wait_count=0)
            )
    await session.flush()


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
    if group.team_size == 1:
        await _generate_singles_round_robin_matches(session, group, round_number)
        return

    roster = await _get_active_roster_for_selection(session, group.id)
    histories = await _get_player_histories(session, group.id)
    counts = await _load_pair_counts(session, group.id)
    capacity = len(courts) * _DOUBLES_PER_MATCH
    # Only whole matches are seated, so select that many up front: the
    # ones trimmed afterwards would otherwise have influenced (via
    # _met_count) who else got picked.
    seats = min(capacity, len(roster) // _DOUBLES_PER_MATCH * _DOUBLES_PER_MATCH)
    selected_ids = _whole_doubles_matches(
        stage1_select_players(roster, seats, histories, _met_count(counts))
    )
    await apply_wait_count_updates(session, group.id, selected_ids)

    if not selected_ids:
        return

    for team_a, team_b in _pair_doubles(selected_ids, counts):
        await create_match_with_participants(
            session,
            group,
            court_id=None,
            round_number=round_number,
            status="queued",
            team_a=list(team_a),
            team_b=list(team_b),
        )


_DOUBLES_PER_MATCH = 4


def _whole_doubles_matches(selected_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Trims a stage-1 selection down to whole doubles matches. With fewer
    active players than the courts hold (say 7 players, 2 courts), stage 1
    returns all 7 but only 4 can be seated; the other 3 used to have their
    wait_count reset as if they had played, so the same 3 kept missing out
    round after round. The lowest-priority players are the ones trimmed."""
    return selected_ids[: len(selected_ids) // _DOUBLES_PER_MATCH * _DOUBLES_PER_MATCH]


def _pair_doubles(
    selected_ids: Sequence[uuid.UUID], counts: PairCounts
) -> list[tuple[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, uuid.UUID]]]:
    """fair_rotation doubles' pairing: fewest repeat teammates, then fewest
    repeat opponents (`pair_doubles_matches()`)."""
    return pair_doubles_matches(selected_ids, _teammate_cost(counts), _opponent_cost(counts))


def _met_count(counts: PairCounts) -> Callable[[uuid.UUID, uuid.UUID], int]:
    """How many matches two players have shared, on either side."""

    def cost(a: uuid.UUID, b: uuid.UUID) -> int:
        return sum(counts.get(frozenset((a, b)), [0, 0]))

    return cost


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
    multi-wave loop instead: each wave reuses the exact same two-stage
    pipeline fair_rotation doubles already runs (`stage2_pair_players` ->
    `team_matchup_stage2`) against an in-memory copy of the group's
    teammate/opponent counts that also includes every match planned by
    earlier waves in this same call (`_count_planned_match()` — the table
    itself only changes once a match starts), so each wave tends to surface
    pairs not yet seen. A wave that adds no new teammate pair just means
    this rotation (see below) is stuck given the current counts — not that
    every rotation is; only once a full cycle of rotations in a row adds
    nothing does the loop give up, since the pipeline is otherwise
    deterministic given unchanged inputs.

    The teammate-forming stage also adds a large penalty for any pair
    already teamed up THIS generation (`seen_teammate_pairs`), so the goal
    "everyone partners everyone once per round" outweighs history from
    earlier rounds; the matchup stage uses the opponent counts alone, since
    minimizing repeat opponents is exactly what it's meant to do.

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
    counts = await _load_pair_counts(session, group.id)
    teammate_count = _teammate_cost(counts)

    def cost_favoring_unseen_teammates(a: uuid.UUID, b: uuid.UUID) -> int:
        penalty = NOT_YET_TEAMMATES_PENALTY if frozenset((a, b)) in seen_teammate_pairs else 0
        return teammate_count(a, b) + penalty

    wave = 0
    stale_rotations = 0
    while len(seen_teammate_pairs) < total_possible_pairs and stale_rotations < len(roster_ids):
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

        # Teammates and opponents decided together (pair_doubles_matches):
        # with 4 active players there is only one way to match two teams,
        # so choosing teammates alone left the opponents to chance — 2 to 8
        # meetings per pair over two simulated 6-player rounds.
        team_matchups = pair_doubles_matches(
            active_order, cost_favoring_unseen_teammates, _opponent_cost(counts)
        )
        teammate_pairs = [team for matchup in team_matchups for team in matchup]
        new_pairs = [
            frozenset(pair) for pair in teammate_pairs if frozenset(pair) not in seen_teammate_pairs
        ]
        if not new_pairs:
            stale_rotations += 1
            continue
        stale_rotations = 0

        for team_a, team_b in team_matchups:
            for player_id in (*team_a, *team_b):
                play_count_this_round[player_id] += 1
            _count_planned_match(counts, team_a, team_b)
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
    `partnerships`. This pairs the whole active roster by minimizing how
    often each pair has already been teammates (reusing
    `stage2_pair_players`) and never touches `partnerships`. With an odd
    headcount one member sits the round out (`_choose_bye()`)."""
    active_ids = await _get_ready_roster_ordered(session, group_id)
    if len(active_ids) % 2 == 1:
        bye = await _choose_bye(session, group_id, active_ids)
        active_ids = [pid for pid in active_ids if pid != bye]
    counts = await _load_pair_counts(session, group_id)
    return stage2_pair_players(active_ids, _teammate_cost(counts))


async def _choose_bye(
    session: AsyncSession, group_id: uuid.UUID, candidates: Sequence[uuid.UUID]
) -> uuid.UUID:
    """fixed_partner with an odd headcount: which of `candidates` sits this
    round out. Whoever has played the most matches in the group, so the bye
    rotates instead of always landing on the same person; among equals, the
    latest joiner (`candidates` is in join order). This used to be a hard
    error (FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT) that blocked the whole
    round until the admin found one more player or sent one home."""
    histories = await _get_player_histories(session, group_id)
    order = {pid: index for index, pid in enumerate(candidates)}

    def played(pid: uuid.UUID) -> int:
        history = histories.get(pid)
        return history.played if history is not None else 0

    return max(candidates, key=lambda pid: (played(pid), order[pid]))


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
    （FR-002）；人數為奇數時，先由 `_choose_bye()` 挑一人本輪輪空。

    037：正式搭檔有一人休息時整隊這一輪不排，另一人也不進自動補位——否則他
    會被臨時配給別人，休息者一回來就落單（research.md Decision 2）。"""
    active_ids = await _get_ready_roster_ordered(session, group.id)
    active_set = set(active_ids)

    all_formal_teams = await _get_active_partnership_teams(session, group.id)
    formal_teams = [
        team for team in all_formal_teams if team[0] in active_set and team[1] in active_set
    ]
    covered = {pid for pair in all_formal_teams for pid in pair}

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
    if len(remaining) % 2 == 1:
        bye = await _choose_bye(session, group.id, remaining)
        remaining = [pid for pid in remaining if pid != bye]
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
    auto-fill pass over anyone still uncovered ensure the round covers
    every active member (FR-002/FR-003/FR-007) — see
    `_resolve_manual_fixed_partner_teams()` — except the one bye when the
    headcount is odd."""
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
    """The full participant set (both teams) of the given round's closing
    match — the last one to start, or failing that the last in call-up
    order — or None if that round has no matches (e.g. round_number < 1, or
    nothing generated yet). Lets a new round's shuffle avoid reseating the
    previous round's closing lineup into its own first slot."""
    if round_number < 1:
        return None

    last_match_result = await session.execute(
        select(Match.id)
        .where(Match.group_id == group_id, Match.round_number == round_number)
        .order_by(
            Match.started_at.desc().nulls_last(),
            Match.queue_position.desc().nulls_last(),
            Match.created_at.desc(),
        )
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
    runs after all of them). Writes `queue_position`, which the pull, the
    "next up" preview and `build_round_matches_list` all order by.

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

    await _write_queue_positions(session, match_ids)


async def _write_queue_positions(session: AsyncSession, match_ids: Sequence[uuid.UUID]) -> None:
    for index, match_id in enumerate(match_ids):
        await session.execute(
            update(Match).where(Match.id == match_id).values(queue_position=index)
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
    or its court/order. PairHistory only holds matches that already took a
    court, so a queued match needs no correction; for an `in_progress` one
    the old lineup's counts move to the new lineup
    (`_move_started_pair_history()`). Publishes via
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

    async def swap() -> None:
        participant_1.roster_entry_id, participant_2.roster_entry_id = (
            roster_entry_id_2,
            roster_entry_id_1,
        )

    await _move_started_pair_history(session, list(matches_by_id.values()), swap)
    await session.commit()
    await _publish_lineup_changed(session, group, list(matches_by_id.values()))


async def _move_started_pair_history(
    session: AsyncSession,
    matches: Sequence[Match],
    change_lineup: Callable[[], Awaitable[None]],
) -> None:
    """Runs `change_lineup()` (which edits participants of `matches`) and
    keeps PairHistory in step for whichever of them already started: their
    old lineup is taken out of the counts and the new one put in. Queued
    matches aren't counted yet, so they need nothing."""
    started = [match for match in matches if match.status == "in_progress"]
    for match in started:
        team_a, team_b = await _match_participants_by_team(session, match.id)
        await _record_pair_history(session, match.group_id, team_a, team_b, delta=-1)
    await change_lineup()
    await session.flush()
    for match in started:
        team_a, team_b = await _match_participants_by_team(session, match.id)
        await _record_pair_history(session, match.group_id, team_a, team_b)


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
    pulled onto a court at a time). PairHistory is kept in step the same
    way as in `swap_planned_match_players()`. Publishes via `_publish_lineup_changed()`
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

    async def substitute() -> None:
        target.roster_entry_id = new_roster_entry_id

    await _move_started_pair_history(session, [match], substitute)
    await session.commit()
    await _publish_lineup_changed(session, group, [match])


async def reorder_planned_matches(
    session: AsyncSession, group: Group, match_ids: Sequence[uuid.UUID]
) -> None:
    """018-plan-then-start: lets the admin drag-reorder the round's still-
    `queued` call-up order — same `queue_position` write as
    `_shuffle_round_match_order` (random.shuffle), just admin-driven instead
    of random. The order is what a freed court follows once everyone
    involved has sat out `RESTED_AFTER_MATCHES` since their last match;
    before that, a candidate whose players sat out more can go first
    (`_choose_next_queued_match()`).
    Follow-up requirement: this now works whether the round is still fully
    `awaiting_start` or already `in_progress` (some matches already on
    courts, the rest still queued) — only a match that hasn't been pulled
    onto a court yet has a "call-up order" left to adjust, so the eligible
    set is exactly `status == "queued"`, not the whole round. `match_ids`
    MUST be a permutation of exactly that queued set — the whole point is
    reordering, not adding/removing matches, so anything else is rejected
    outright rather than guessed at. Broadcasts
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

    await _write_queue_positions(session, match_ids)
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
    pulled = await pull_queued_match_for_court(
        session, match.group_id, match.round_number, match.court_id
    )
    if pulled is None:
        pulled = await _seat_waiting_players_on_court(
            session, group, match.court_id, match.round_number
        )
    return pulled


def _continuous_rotation_applies(group: Group) -> bool:
    return (
        group.continuous_rotation
        and group.scheduling_mechanism == "fair_rotation"
        and group.team_size == 2
    )


async def _seat_waiting_players_on_court(
    session: AsyncSession, group: Group, court_id: uuid.UUID, round_number: int
) -> Match | None:
    """Continuous rotation: with nothing left in the queue, puts the four
    highest-priority players who aren't on a court straight onto
    `court_id`, as a new match in the current round. Without it, a fair_
    rotation doubles court that finishes early sits empty until every other
    court is done and the next round is generated. Priority is stage 1's
    (wait_count, then fewest matches played, then longest since playing);
    the four picked go to wait_count 0 and the idle players passed over
    wait one more, so wait_count keeps meaning "matches sat out". None if
    the mode is off, the round has moved on, the court was filled
    meanwhile, or fewer than four players are free. Flushes, never
    commits."""
    if not _continuous_rotation_applies(group) or round_number != group.current_round_number:
        return None

    # Two courts finishing at once must not seat the same idle players
    # twice. Unlike round generation's NOWAIT lock, this waits its turn.
    await session.execute(select(Group.id).where(Group.id == group.id).with_for_update())
    occupied = await session.execute(
        select(Match.id).where(Match.court_id == court_id, Match.status == "in_progress")
    )
    if occupied.scalar_one_or_none() is not None:
        return None

    busy_result = await session.execute(
        select(MatchParticipant.roster_entry_id)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(Match.group_id == group.id, Match.status == "in_progress")
    )
    busy = set(busy_result.scalars())
    active_roster = await _get_active_roster_for_selection(session, group.id)
    idle_roster = [row for row in active_roster if row[0] not in busy]
    counts = await _load_pair_counts(session, group.id)
    selected = stage1_select_players(
        idle_roster,
        _DOUBLES_PER_MATCH,
        await _get_player_histories(session, group.id),
        _met_count(counts),
    )
    if len(selected) < _DOUBLES_PER_MATCH:
        return None

    passed_over = [row[0] for row in idle_roster if row[0] not in selected]
    await session.execute(
        update(RosterEntry).where(RosterEntry.id.in_(selected)).values(wait_count=0)
    )
    if passed_over:
        await session.execute(
            update(RosterEntry)
            .where(RosterEntry.id.in_(passed_over))
            .values(wait_count=func.coalesce(RosterEntry.wait_count, 0) + 1)
        )

    [(team_a, team_b)] = _pair_doubles(selected, counts)
    return await create_match_with_participants(
        session,
        group,
        court_id=court_id,
        round_number=round_number,
        status="in_progress",
        team_a=list(team_a),
        team_b=list(team_b),
    )


async def round_is_stalled_by_rest(session: AsyncSession, group: Group) -> bool:
    """037-rest-ready-toggle (FR-020): the current round can't go on until a
    resting player comes back — nothing on court, something queued, every
    queued match has a resting player, and none of them can be called
    (the mechanism keeps such matches, or no substitute is free). Such a
    round never "completes" on its own: its matches stay queued."""
    round_filter = (
        Match.group_id == group.id,
        Match.round_number == group.current_round_number,
    )
    live = await session.execute(
        select(Match.id).where(*round_filter, Match.status == "in_progress").limit(1)
    )
    if live.scalar_one_or_none() is not None:
        return False
    queued = await session.execute(
        select(Match.id).where(*round_filter, Match.status == "queued").limit(1)
    )
    if queued.scalar_one_or_none() is None:
        return False
    callable_now = await session.execute(
        select(Match.id)
        .where(*round_filter, Match.status == "queued", ~_has_resting_participant())
        .limit(1)
    )
    if callable_now.scalar_one_or_none() is not None:
        return False
    choice = await _choose_next_queued_match(
        session, group.id, group.current_round_number, lock=False
    )
    return choice is None


async def _can_generate_any_match(session: AsyncSession, group: Group) -> bool:
    """037: whether a new round would have at least one match, going by the
    ready players (FR-011). Guards the rest-driven auto advance: advancing
    into a round with nothing in it would only abandon the matches kept for
    a resting player — and each toggle would burn a round number."""
    ready = await _get_ready_roster_ordered(session, group.id)
    if group.scheduling_mechanism == "fixed_partner":
        if group.partner_source == "auto":
            return len(ready) >= 4
        ready_set = set(ready)
        partnerships = await _get_active_partnership_teams(session, group.id)
        whole_teams = sum(1 for x, y in partnerships if x in ready_set and y in ready_set)
        partnered = {pid for team in partnerships for pid in team}
        free = sum(1 for pid in ready if pid not in partnered)
        return whole_teams + free // 2 >= 2
    return len(ready) >= (2 if group.team_size == 1 else _DOUBLES_PER_MATCH)


async def round_would_auto_advance(
    session: AsyncSession, group: Group, *, triggered_by_rest_change: bool
) -> bool:
    """Whether Auto Next Round advances now — the one rule both the advance
    itself and 037's REST_ENDS_ROUND reminder use, so the player is never
    warned about an advance that doesn't happen, or not warned about one
    that does. Reads only.

    - The round finished (every match terminal): advance, as before. After
      a rest change, only if the next round would have a match — otherwise
      toggling would spin through empty rounds (037, SC-006) — and only
      once a round has ever been generated: a group nobody has started
      yet mustn't start itself because someone pressed "rest".
    - The round is stalled by rest: advance if the next round would have a
      match (037 FR-020 and its exception)."""
    if group.scheduling_mechanism == "manual" or not group.auto_next_round:
        return False
    if not await _get_active_courts_ordered(session, group.id):
        return False
    if await round_is_complete(session, group.id, group.current_round_number):
        if not triggered_by_rest_change:
            return True
        started = await session.execute(
            select(RoundHistory.round_number).where(RoundHistory.group_id == group.id).limit(1)
        )
        return (
            started.scalar_one_or_none() is not None
            and await _can_generate_any_match(session, group)
        )
    if await round_is_stalled_by_rest(session, group):
        return await _can_generate_any_match(session, group)
    return False


async def check_round_complete_and_maybe_auto_advance(
    session: AsyncSession, group: Group, *, triggered_by_rest_change: bool = False
) -> bool:
    """FR-034/035: if Auto Next Round is on, the round has actually finished,
    and there's at least one court to generate for (FR-030 — zero courts
    MUST NOT even attempt generation), advance to the next round. 037: also
    a round stalled by rest (`round_would_auto_advance()`)."""
    if not await round_would_auto_advance(
        session, group, triggered_by_rest_change=triggered_by_rest_change
    ):
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


async def set_continuous_rotation(session: AsyncSession, group: Group, enabled: bool) -> Group:
    """Plain immediate toggle, same shape as `set_auto_next_round()`. Only
    fair_rotation doubles has a meaning for it (every other mechanism
    already pre-plans the whole round), so enabling it anywhere else is
    rejected; a group that later switches mechanism keeps the flag, and
    `_continuous_rotation_applies()` ignores it. Turning it on mid-round
    seats waiting players on any court that is idle right now."""
    if enabled and not (
        group.scheduling_mechanism == "fair_rotation" and group.team_size == 2
    ):
        raise ApiError("CONTINUOUS_ROTATION_NOT_SUPPORTED", status_code=400)
    group.continuous_rotation = enabled
    await session.commit()
    await session.refresh(group)
    if enabled and await get_round_phase(session, group) == "in_progress":
        await _advance_other_idle_courts(
            session, group, group.current_round_number, exclude_court_id=None
        )
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
                serve=await registry.get(entry[0].type_key).serve_station(session, entry[0]),
                detailed_scoring_enabled=entry[0].detailed_scoring_enabled,
                target_score=entry[0].target_score,
                cap_score=entry[0].cap_score,
                **match_sport_fields(entry[0]),
                sport_state=await registry.get(entry[0].type_key).live_state(session, entry[0]),
            )
            waiting_reason = None
        else:
            current_match = None
            waiting_reason, next_up = await _idle_court_status(session, group, court.id)
        court_statuses.append(
            CourtScheduleStatus(
                court_id=str(court.id),
                name=court.name,
                current_match=current_match,
                waiting_reason=waiting_reason,
                next_up=next_up,
            )
        )

    partners = await _round_partners(session, group)
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
            resting=entry.resting_since is not None,
            resting_since=entry.resting_since,
            partner_roster_entry_id=partners.get(entry.id),
        )
        for entry in roster_result.scalars()
    ]

    round_phase = (
        None if group.scheduling_mechanism == "manual" else await get_round_phase(session, group)
    )

    return ScheduleResponse(
        current_round_number=group.current_round_number,
        scheduling_mechanism=group.scheduling_mechanism,
        match_mode=group.match_mode,
        auto_next_round=group.auto_next_round,
        continuous_rotation=group.continuous_rotation,
        round_phase=round_phase,
        courts=court_statuses,
        roster=roster_statuses,
        sport=group_sport_summary(group),
    )


async def _round_partners(session: AsyncSession, group: Group) -> dict[uuid.UUID, str]:
    """037 FR-022: fixed_partner only — who each player teams with in this
    round's matches, so a player can see their partner is resting. Taken
    from the matches rather than `partnerships`, so it's right for auto
    partners and this round's temporary pairings too."""
    if group.scheduling_mechanism != "fixed_partner":
        return {}
    result = await session.execute(
        select(MatchParticipant.match_id, MatchParticipant.team, MatchParticipant.roster_entry_id)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(
            Match.group_id == group.id,
            Match.round_number == group.current_round_number,
            _COUNTS_TOWARD_ROUND,
        )
    )
    sides: dict[tuple[uuid.UUID, str], list[uuid.UUID]] = {}
    for match_id, team, roster_entry_id in result.all():
        sides.setdefault((match_id, team), []).append(roster_entry_id)
    partners: dict[uuid.UUID, str] = {}
    for side in sides.values():
        if len(side) == 2:
            partners[side[0]] = str(side[1])
            partners[side[1]] = str(side[0])
    return partners


async def build_round_matches_list(session: AsyncSession, group: Group) -> RoundMatchesResponse:
    """011-round-robin-scheduling: the admin-facing "本輪賽程清單" — unlike
    `build_schedule_snapshot()` above (which only shows each court's
    *current* match), this returns every match in the current round
    regardless of status (queued/in_progress/completed/abandoned), so the
    admin can see the whole pre-generated round-robin schedule rather than
    just what's on court right now. Also how much of the round is left
    and roughly how long it will take, which a round-robin round (up to
    dozens of matches) otherwise gives no hint of, and who has no match in
    it at all."""
    result = await session.execute(
        select(Match)
        .where(Match.group_id == group.id, Match.round_number == group.current_round_number)
        # Matches that already went on court first, in the order they did;
        # then the queue in call-up order.
        .order_by(Match.started_at.asc().nulls_last(), *_QUEUE_ORDER)
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

    remaining = [match for match in matches if match.status in _ACTIVE_MATCH_STATUSES]
    scheduled = {
        participant.roster_entry_id
        for match in matches
        if match.status != "abandoned" or match.started_at is not None
        for participant in participants_by_match.get(match.id, [])
    }
    # Resting players have no match by choice, not as a bye (037).
    roster_result = await session.execute(
        select(RosterEntry.id, RosterEntry.nickname)
        .where(RosterEntry.group_id == group.id, RosterEntry.status == "active", _IS_READY)
        .order_by(RosterEntry.joined_at, RosterEntry.id)
    )
    sitting_out = [
        RosterSummary(roster_entry_id=str(row.id), nickname=row.nickname)
        for row in roster_result.all()
        if str(row.id) not in scheduled
    ]

    # 037-rest-ready-toggle: which queued matches wait on a resting player,
    # and what happens when they come up (FR-016／FR-018, FR-021).
    resting_result = await session.execute(
        select(RosterEntry.id, RosterEntry.nickname)
        .where(
            RosterEntry.group_id == group.id,
            RosterEntry.status == "active",
            RosterEntry.resting_since.is_not(None),
        )
        .order_by(RosterEntry.joined_at, RosterEntry.id)
    )
    resting = {str(row.id): row.nickname for row in resting_result.all()}
    effect: RestEffect = (
        "substitute"
        if _substitutes_for_rest(group.scheduling_mechanism, group.match_mode)
        else "held"
    )
    rest_effects: dict[uuid.UUID, RestEffect] = {}
    waiting_on: list[str] = []
    for match in matches:
        if match.status != "queued":
            continue
        in_match = [p.roster_entry_id for p in participants_by_match.get(match.id, [])]
        if any(pid in resting for pid in in_match):
            rest_effects[match.id] = effect
            waiting_on.extend(pid for pid in in_match if pid in resting and pid not in waiting_on)
    waiting_on_rest = None
    if rest_effects:
        waiting_on_rest = WaitingOnRest(
            match_count=len(rest_effects),
            players=[
                RosterSummary(roster_entry_id=pid, nickname=nickname)
                for pid, nickname in resting.items()
                if pid in waiting_on
            ],
            stalled=await round_is_stalled_by_rest(session, group),
        )

    return RoundMatchesResponse(
        round_number=group.current_round_number,
        remaining_count=len(remaining),
        estimated_remaining_minutes=await _estimate_remaining_minutes(
            session,
            group,
            [
                [p.roster_entry_id for p in participants_by_match.get(match.id, [])]
                for match in remaining
            ],
        ),
        sitting_out=sitting_out,
        waiting_on_rest=waiting_on_rest,
        matches=[
            RoundMatchSummary(
                match_id=str(match.id),
                status=match.status,
                court_name=court_names.get(match.court_id) if match.court_id else None,
                participants=participants_by_match.get(match.id, []),
                score_a=match.score_a,
                score_b=match.score_b,
                winner_team=cast("Team | None", match.winner_team),
                rest_effect=rest_effects.get(match.id),
            )
            for match in matches
        ],
    )


# Used until the group has finished enough matches of its own to measure:
# the sport type's own guess (043 research Decision 18; net rally: roughly
# 0.6 minutes per point of the target score — about 13 minutes for a
# 21-point game, 9 for 15 points).
_MIN_MATCHES_FOR_MEASURED_DURATION = 3
_MEASURED_DURATION_SAMPLE = 30


async def _typical_match_minutes(session: AsyncSession, group: Group) -> float:
    """Median length of the group's last `_MEASURED_DURATION_SAMPLE`
    completed matches, or a target-score-based guess before there are
    enough of them."""
    result = await session.execute(
        select(Match.started_at, Match.ended_at)
        .where(
            Match.group_id == group.id,
            Match.status == "completed",
            Match.started_at.is_not(None),
            Match.ended_at.is_not(None),
        )
        .order_by(Match.ended_at.desc())
        .limit(_MEASURED_DURATION_SAMPLE)
    )
    durations = [
        (ended - started).total_seconds() / 60 for started, ended in result.all() if ended > started
    ]
    if len(durations) >= _MIN_MATCHES_FOR_MEASURED_DURATION:
        return float(statistics.median(durations))
    guess = registry.get(group.type_key).estimate_minutes(
        end_mode=group.end_mode, target_score=group.target_score, type_params=group.type_params
    )
    return max(guess, 5.0)


async def _estimate_remaining_minutes(
    session: AsyncSession, group: Group, remaining_lineups: Sequence[Sequence[str]]
) -> int | None:
    """Rough minutes until the round's last match ends: the remaining
    matches spread over the courts, but never fewer rounds of play than
    the busiest player still has matches (they can only play one at a
    time). Counts an in-progress match as a whole one, so it leans long.
    None when nothing remains or there are no courts."""
    if not remaining_lineups:
        return None
    court_count = len(await _get_active_courts_ordered(session, group.id))
    if court_count == 0:
        return None
    per_player: dict[str, int] = {}
    for lineup in remaining_lineups:
        for player in lineup:
            per_player[player] = per_player.get(player, 0) + 1
    busiest_player = max(per_player.values(), default=0)
    slots = max(math.ceil(len(remaining_lineups) / court_count), busiest_player)
    return math.ceil(slots * await _typical_match_minutes(session, group))


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
    """Everyone in the group, resting or not, in join order — for formal
    partnerships, which resting doesn't affect (037 FR-034). Anything
    deciding who plays uses `_get_ready_roster_ordered()` instead."""
    result = await session.execute(
        select(RosterEntry.id)
        .where(RosterEntry.group_id == group_id, RosterEntry.status == "active")
        .order_by(RosterEntry.joined_at, RosterEntry.id)
    )
    return [row[0] for row in result.all()]


async def _get_ready_roster_ordered(session: AsyncSession, group_id: uuid.UUID) -> list[uuid.UUID]:
    """037: `_get_active_roster_ordered()` without resting players, for
    everything that decides who plays — this round's teams, late joiners'
    matches, substitutes, the temporary pairing preview."""
    result = await session.execute(
        select(RosterEntry.id)
        .where(RosterEntry.group_id == group_id, RosterEntry.status == "active", _IS_READY)
        .order_by(RosterEntry.joined_at, RosterEntry.id)
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
) -> bool:
    """FR-022 (fixed_partner auto-pairing, when applicable), then
    `_schedule_late_joiner_matches()`. Returns whether the current round's
    schedule gained matches, in which case the caller MUST call
    `refresh_courts_after_roster_change()` once it has committed."""
    if group.scheduling_mechanism == "fixed_partner":
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
    return await _schedule_late_joiner_matches(session, group)


async def _schedule_late_joiner_matches(session: AsyncSession, group: Group) -> bool:
    """Gives members who joined after the current round was planned their
    share of that round, instead of making them wait for the next one — a
    full round-robin round can run for hours. Adds queued matches to the
    end of the call-up order; the freshly arrived players have rested the
    longest, so `pick_next_match()` calls them early anyway.
      - singles round-robin: the newcomer against everyone they haven't
        met this round;
      - fixed_partner: newcomers are paired up (their formal partnership
        if both are new, otherwise in join order; an odd one waits for the
        next arrival), and each new team plays every team in the round;
      - individual_mixed: the newcomer partners every other member once,
        against the two members with the fewest matches this round.
    fair_rotation doubles needs nothing: a never-played member already
    tops the next selection (wait_count NULL), and with continuous
    rotation they're seated at the next free court. Nothing happens
    before the round is planned or after it's over (the next plan includes
    everyone). Flushes, never commits. Returns whether any match was
    added."""
    mechanism = group.scheduling_mechanism
    if mechanism == "manual" or (mechanism == "fair_rotation" and group.team_size != 1):
        return False
    if await get_round_phase(session, group) == "awaiting_plan":
        return False

    round_number = group.current_round_number
    rows = await session.execute(
        select(MatchParticipant.match_id, MatchParticipant.roster_entry_id, MatchParticipant.team)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(
            Match.group_id == group.id,
            Match.round_number == round_number,
            _COUNTS_TOWARD_ROUND,
        )
    )
    sides: dict[tuple[uuid.UUID, str], list[uuid.UUID]] = {}
    for match_id, roster_entry_id, team in rows.all():
        sides.setdefault((match_id, team), []).append(roster_entry_id)
    scheduled = {pid for ids in sides.values() for pid in ids}

    active = await _get_ready_roster_ordered(session, group.id)
    newcomers = [pid for pid in active if pid not in scheduled]
    if not newcomers:
        return False

    planned: list[tuple[list[uuid.UUID], list[uuid.UUID]]] = []

    def plan(side_1: Sequence[uuid.UUID], side_2: Sequence[uuid.UUID]) -> None:
        # Alternate who takes side A, so no newcomer is stuck on one side.
        if len(planned) % 2 == 0:
            planned.append((list(side_1), list(side_2)))
        else:
            planned.append((list(side_2), list(side_1)))

    if mechanism == "fair_rotation":
        met: set[frozenset[uuid.UUID]] = set()
        match_ids = {match_id for match_id, _team in sides}
        for match_id in match_ids:
            met.add(frozenset(sides.get((match_id, "A"), []) + sides.get((match_id, "B"), [])))
        for newcomer in newcomers:
            for opponent in active:
                pair = frozenset((newcomer, opponent))
                if opponent == newcomer or pair in met:
                    continue
                met.add(pair)
                plan([newcomer], [opponent])
    elif mechanism == "fixed_partner":
        round_teams: list[tuple[uuid.UUID, ...]] = []
        for ids in sides.values():
            team = tuple(sorted(ids))
            if len(team) == 2 and team not in round_teams:
                round_teams.append(team)
        for new_team in await _teams_for_newcomers(session, group, newcomers):
            for other_team in round_teams:
                plan(new_team, other_team)
            round_teams.append(tuple(sorted(new_team)))
    else:
        appearances: dict[uuid.UUID, int] = dict.fromkeys(active, 0)
        for ids in sides.values():
            for pid in ids:
                if pid in appearances:
                    appearances[pid] += 1
        counts = await _load_pair_counts(session, group.id)
        opponent_count = _opponent_cost(counts)
        join_order = {pid: index for index, pid in enumerate(active)}
        def opponent_rank(
            pid: uuid.UUID, newcomer: uuid.UUID, partner: uuid.UUID
        ) -> tuple[int, int, int]:
            return (
                appearances[pid],
                opponent_count(newcomer, pid) + opponent_count(partner, pid),
                join_order[pid],
            )

        for newcomer in newcomers:
            for partner in active:
                if partner == newcomer:
                    continue
                ranked = sorted(
                    (
                        (opponent_rank(pid, newcomer, partner), pid)
                        for pid in active
                        if pid not in (newcomer, partner)
                    ),
                )
                opponents = [pid for _rank, pid in ranked[:2]]
                if len(opponents) < 2:
                    break
                plan([newcomer, partner], opponents)
                for pid in (newcomer, partner, *opponents):
                    appearances[pid] += 1
                _count_planned_match(counts, [newcomer, partner], opponents)

    if not planned:
        return False

    position_result = await session.execute(
        select(func.max(Match.queue_position)).where(
            Match.group_id == group.id, Match.round_number == round_number
        )
    )
    last_position = position_result.scalar_one()
    next_position = 0 if last_position is None else last_position + 1
    for offset, (team_a, team_b) in enumerate(planned):
        await create_match_with_participants(
            session,
            group,
            court_id=None,
            round_number=round_number,
            status="queued",
            team_a=team_a,
            team_b=team_b,
            queue_position=next_position + offset,
        )
    return True


async def _teams_for_newcomers(
    session: AsyncSession, group: Group, newcomers: Sequence[uuid.UUID]
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """fixed_partner late-joiner teams: formal partnerships whose both
    members are newcomers (manual partner source only), then the rest in
    join order. An odd one out stays unscheduled until someone else
    arrives. A newcomer whose formal partner is resting waits for them
    instead of being paired with someone else (037 research.md Decision 8)."""
    newcomer_set = set(newcomers)
    teams: list[tuple[uuid.UUID, uuid.UUID]] = []
    covered: set[uuid.UUID] = set()
    if group.partner_source == "manual":
        ready = set(await _get_ready_roster_ordered(session, group.id))
        for team in await _get_active_partnership_teams(session, group.id):
            if team[0] in newcomer_set and team[1] in newcomer_set:
                teams.append(team)
            elif any(pid not in ready for pid in team):
                covered.update(team)
    covered.update(pid for team in teams for pid in team)
    rest = [pid for pid in newcomers if pid not in covered]
    teams.extend(zip(rest[0::2], rest[1::2], strict=False))
    return teams


async def refresh_courts_after_roster_change(session: AsyncSession, group: Group) -> None:
    """Post-commit follow-up to a join, leave or kick: a newcomer's matches
    or a substitute may let an idle court start right away, and every
    court's "next up" preview may have changed. Courts are only filled
    while the round is actually under way — a planned round waits for the
    admin's "start", and pulling a match here would start it for them.
    Callers MUST have already committed."""
    if group.scheduling_mechanism == "manual":
        return
    if await get_round_phase(session, group) == "in_progress":
        await _advance_other_idle_courts(
            session, group, group.current_round_number, exclude_court_id=None
        )
    for court in await _get_active_courts_ordered(session, group.id):
        await publish(
            court_channel(str(group.id), str(court.id)),
            "match.nextRound",
            {"round_number": group.current_round_number},
        )


async def remove_roster_entry_from_schedule(
    session: AsyncSession, group: Group, roster_entry_id: uuid.UUID
) -> None:
    """FR-039/040/041, shared by a member leaving and being kicked. Each of
    the member's queued matches in the current round either gets a
    substitute or is abandoned:
      - fair_rotation doubles and individual_mixed: a substitute
        (`_pick_substitute()`) takes the empty slot, so the other three
        still play. Abandoning used to cost all three a match.
      - singles round-robin and fixed_partner: abandoned. Every other
        player (or team) was due exactly one match against the leaver, so
        each loses exactly one and the round stays even; a substitute would
        hand someone a repeat match instead.
    Also abandoned when nobody is free to substitute. In-progress matches
    are left completely untouched (FR-040); this never regenerates a round
    (FR-041), it only mutates the already-generated schedule for the
    current round."""
    result = await session.execute(
        select(Match.id)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(
            Match.group_id == group.id,
            Match.round_number == group.current_round_number,
            Match.status == "queued",
            MatchParticipant.roster_entry_id == roster_entry_id,
        )
        .order_by(*_QUEUE_ORDER)
    )
    match_ids = list(result.scalars().all())
    if not match_ids:
        return

    to_abandon = match_ids
    if group.team_size == 2 and group.scheduling_mechanism in (
        "fair_rotation",
        "individual_mixed",
    ):
        to_abandon = []
        appearances = await _round_appearances(session, group)
        for match_id in match_ids:
            substitute = await _pick_substitute(
                session, group, match_id, roster_entry_id, appearances
            )
            if substitute is None:
                to_abandon.append(match_id)
                continue
            await session.execute(
                update(MatchParticipant)
                .where(
                    MatchParticipant.match_id == match_id,
                    MatchParticipant.roster_entry_id == roster_entry_id,
                )
                .values(roster_entry_id=substitute)
            )
            appearances[substitute] = appearances.get(substitute, 0) + 1
            if group.scheduling_mechanism == "fair_rotation":
                # Same as being picked by stage 1: they're playing now.
                await session.execute(
                    update(RosterEntry).where(RosterEntry.id == substitute).values(wait_count=0)
                )

    if to_abandon:
        await session.execute(
            update(Match)
            .where(Match.id.in_(to_abandon))
            .values(status="abandoned", ended_at=datetime.now(UTC))
        )
    await session.flush()


async def _round_appearances(session: AsyncSession, group: Group) -> dict[uuid.UUID, int]:
    """roster_entry_id -> matches in the current round (`_COUNTS_TOWARD_ROUND`)."""
    result = await session.execute(
        select(MatchParticipant.roster_entry_id, func.count())
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(
            Match.group_id == group.id,
            Match.round_number == group.current_round_number,
            _COUNTS_TOWARD_ROUND,
        )
        .group_by(MatchParticipant.roster_entry_id)
    )
    return {row[0]: row[1] for row in result.all()}


async def _pick_substitute(
    session: AsyncSession,
    group: Group,
    match_id: uuid.UUID,
    leaving_id: uuid.UUID,
    appearances: dict[uuid.UUID, int],
    *,
    must_be_free: bool = False,
    exclude: Collection[uuid.UUID] = (),
) -> uuid.UUID | None:
    """Who replaces `leaving_id` in queued doubles match `match_id`: a ready
    member not already in it, with the fewest matches this round, then the
    fewest past meetings with the three who stay, then the earliest joiner.
    Players busy on another court right now are fine for a leaver — the
    match is queued, and won't be called while they're playing.

    037-rest-ready-toggle: substituting for a resting player happens as the
    match is called, so `must_be_free` also rules out anyone on court now;
    `exclude` holds substitutes already picked for the same match."""
    participants_result = await session.execute(
        select(MatchParticipant.roster_entry_id).where(MatchParticipant.match_id == match_id)
    )
    in_match = set(participants_result.scalars())
    staying = [pid for pid in in_match if pid != leaving_id]
    unavailable = set(exclude)
    if must_be_free:
        busy = await session.execute(
            select(MatchParticipant.roster_entry_id)
            .join(Match, Match.id == MatchParticipant.match_id)
            .where(Match.group_id == group.id, Match.status == "in_progress")
        )
        unavailable.update(busy.scalars())
    candidates = [
        pid
        for pid in await _get_ready_roster_ordered(session, group.id)
        if pid != leaving_id and pid not in in_match and pid not in unavailable
    ]
    if not candidates:
        return None

    counts = await _load_pair_counts(session, group.id)

    def met(a: uuid.UUID, b: uuid.UUID) -> int:
        return sum(counts.get(frozenset((a, b)), [0, 0]))

    join_order = {pid: index for index, pid in enumerate(candidates)}
    return min(
        candidates,
        key=lambda pid: (
            appearances.get(pid, 0),
            sum(met(pid, other) for other in staying),
            join_order[pid],
        ),
    )


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
    await refresh_courts_after_roster_change(session, group)

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

    active_ids = await _get_ready_roster_ordered(session, group.id)
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


def match_wins(
    score_x: int,
    score_y: int,
    target_score: int,
    cap_score: int | None,
    win_by: int = 2,
) -> bool:
    """達標判定公式（research.md #2）——`deuce_threshold` 不參與運算：
    001 之兩組固定預設值（21/20/30、15/14/21）已交叉驗證此公式與其定義
    完全一致，無需額外讀取 deuce 門檻欄位。

    043 起委派 `app.sports.scoring.match_wins`（research Decision 3）；
    `win_by` 預設 2 讓既有呼叫端與羽球行為不變。"""
    return scoring.match_wins(score_x, score_y, target=target_score, win_by=win_by, cap=cap_score)


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
    sport_state: object = None,
    follow_up_score_event_id: uuid.UUID | None = None,
) -> ScoreMutationResult:
    return ScoreMutationResult(
        applied=applied,
        match_id=str(match.id),
        status=match.status,
        score_a=match.score_a,
        score_b=match.score_b,
        winner_team=cast("Literal['A', 'B', 'D'] | None", match.winner_team),
        score_event_id=str(score_event_id) if score_event_id is not None else None,
        serve=serve,
        sport_state=sport_state,
        follow_up_score_event_id=(
            str(follow_up_score_event_id) if follow_up_score_event_id is not None else None
        ),
    )


def match_sport_fields(match: Match) -> dict[str, Any]:
    """043 contracts/match-events-api.md §7: the activity and common-parameter
    snapshot every live match view carries (sport_state is added by the
    caller, from the plugin)."""
    return {
        "sport": catalog.summary_for(
            sport_key=match.sport_key, type_key=match.type_key, sport_name=match.sport_name
        ),
        "end_mode": match.end_mode,
        "win_by": match.win_by,
        "allow_draw": match.allow_draw,
        "score_steps": list(match.score_steps),
    }


def group_sport_summary(group: Group) -> SportSummary:
    return catalog.summary_for(
        sport_key=group.sport_key, type_key=group.type_key, sport_name=group.sport_name
    )


async def _publish_match_ended(
    session: AsyncSession, match: Match, court: Court, pulled: Match | None
) -> None:
    """contracts/ably-events.md `match.ended` — `waiting_reason` is `null`
    when `pulled` is not None (a `rotation.updated` is published right after,
    research.md #7), otherwise reports why the court is idle."""
    waiting_reason: WaitingReason | None = None
    if pulled is None:
        group_result = await session.execute(select(Group).where(Group.id == match.group_id))
        waiting_reason, _next_up = await _idle_court_status(
            session, group_result.scalar_one(), court.id
        )
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
        if pulled is None:
            pulled = await _seat_waiting_players_on_court(session, group, court.id, round_number)
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
    轉為 `completed` 並依序呼叫 003 既有 hook。

    032-score-then-record: a `+1` in detailed-scoring mode is applied here
    exactly like a plain one — score-then-record (see attach_shot_placement()
    below) never blocks the score itself on the scorer filling in landing
    detail. The returned ScoreMutationResult.score_event_id is what a caller
    then hands to attach_shot_placement().

    043 research Decision 8 — a fixed skeleton around the sport type plugin:
    atomic UPDATE → group activity → spine `point` event → the plugin's
    `on_spine_event()` (badminton: serve advance/restore, shot-placement
    cleanup) → commit → win test → terminal hooks → publish. The plugin only
    returns what clients should see (`serve`, `sport_state`); every publish
    stays here."""
    match = await _fetch_match_for_court(session, court, match_id)
    plugin = registry.get(match.type_key)
    # 043: a sport type may only move the score through its own events
    # (frames), and a step must be one the group allows; a negative step is
    # net rally's −1 correction only (other types undo instead).
    if not plugin.direct_points:
        raise ApiError("EVENT_KIND_NOT_ALLOWED", status_code=422, detail={"kind": "point"})
    if (
        delta == 0
        or abs(delta) not in match.score_steps
        or (delta < 0 and not plugin.negative_points)
    ):
        raise ApiError("SCORE_STEP_NOT_ALLOWED", status_code=422)

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
    event = ScoreEvent(
        id=uuid.uuid4(),
        match_id=match_id,
        group_id=match.group_id,
        kind="point",
        side=side,
        delta=delta,
        score_a=row.score_a,
        score_b=row.score_b,
        source=source,
    )
    session.add(event)
    effect = await plugin.on_spine_event(session, SpineEventContext(match=match, event=event))

    await session.commit()
    await session.refresh(match)

    my_score, opp_score = (
        (match.score_a, match.score_b) if side == "A" else (match.score_b, match.score_a)
    )
    # feature/control-panel-scoreboard-style: also handed back on this same
    # response below (not just published) — None when the match ends this
    # point (no more serve state to show).
    serve_payload: dict[str, str | None] | None = None
    sport_state: object = None
    if match.end_mode == "target" and match_wins(
        my_score, opp_score, match.target_score, match.cap_score, match.win_by
    ):
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
        # event as the score itself.
        serve_payload = effect.serve
        sport_state = effect.sport_state
        await publish(
            court_channel(str(match.group_id), str(court.id)),
            "match.scoreUpdated",
            {
                "match_id": str(match.id),
                "score_a": match.score_a,
                "score_b": match.score_b,
                "serve": serve_payload,
                "sport_state": sport_state,
            },
        )

    return _score_mutation_result(
        applied=True,
        match=match,
        score_event_id=event.id,
        serve=ServeStationInfo(**serve_payload) if serve_payload is not None else None,
        sport_state=sport_state,
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

        # Reverses _start_match()'s writes exactly: the court binding, serve
        # state and the PairHistory it recorded. wait_count is untouched by
        # a plain pull, so there's nothing else to unwind here.
        replacement_team_a, replacement_team_b = await _match_participants_by_team(
            session, replacement.id
        )
        await _record_pair_history(
            session, replacement.group_id, replacement_team_a, replacement_team_b, delta=-1
        )
        replacement.court_id = None
        replacement.status = "queued"
        replacement.started_at = None
        # 043: whatever on_match_start() set up (badminton: serve state).
        await registry.get(replacement.type_key).on_match_requeued(session, replacement)
        await session.flush()

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

    Every one of `roster_entry_id`, `losing_roster_entry_id`, the
    `landing_x`/`landing_y` pair and `ending_type` is independently optional
    (032/035); whichever ARE supplied are validated against the credited
    side, the match's singles/doubles court width and the serve that started
    the rally.

    043 research Decision 9: shot placement is a module of the net rally
    sport type, and its rules and table belong to that plugin
    (`app/sports/types/net_rally/placement.py`, where the full rules are
    documented). Core only finds the match on this court and hands over; a
    sport type without the module refuses with MODULE_NOT_SUPPORTED."""
    match = await _fetch_match_for_court(session, court, match_id)
    await registry.get(match.type_key).record_point_detail(
        session,
        match,
        score_event_id,
        PointDetail(
            roster_entry_id=roster_entry_id,
            losing_roster_entry_id=losing_roster_entry_id,
            landing_x=landing_x,
            landing_y=landing_y,
            ending_type=ending_type,
        ),
    )


async def _complete_match(
    session: AsyncSession, match: Match, court: Court, winner_team: str
) -> None:
    """Mark an in-progress match completed with `winner_team` (A, B or 043's
    D for a draw) and run the terminal hooks and publishes, like a natural
    win in apply_score_delta()."""
    await session.execute(
        update(Match)
        .where(Match.id == match.id, Match.status == "in_progress")
        .values(status="completed", winner_team=winner_team, ended_at=datetime.now(UTC))
    )
    await session.commit()
    await session.refresh(match)
    pulled = await _advance_after_terminal(session, match)
    await _publish_match_ended(session, match, court, pulled)


async def apply_plugin_event(
    session: AsyncSession,
    court: Court,
    match_id: uuid.UUID,
    kind: str,
    payload: dict[str, Any],
    source: str = "control_panel",
) -> ScoreMutationResult:
    """043 contracts/match-events-api.md §2: an event the match's sport type
    declares (frames: an in-frame point, the end of a frame). Core puts it on
    the spine (delta 0), the plugin writes its own rows, and a follow-up
    `point` the plugin asks for (a frame won) moves the match score in the
    same transaction — ending the match if that reaches the target.

    Every row one call writes shares one `created_at`: that is what makes it
    one action for undo_last_event()."""
    match = await _fetch_match_for_court(session, court, match_id)
    plugin = registry.get(match.type_key)
    if match.status != "in_progress":
        raise ApiError("MATCH_NOT_IN_PROGRESS", status_code=409)
    schema = plugin.event_schemas().get(kind)
    if schema is None:
        raise ApiError("EVENT_KIND_NOT_ALLOWED", status_code=422, detail={"kind": kind})
    try:
        parsed = schema.model_validate(payload)
    except ValidationError as error:
        raise ApiError("VALIDATION_ERROR", status_code=422) from error

    now = datetime.now(UTC)
    await session.execute(
        update(Group).where(Group.id == match.group_id).values(last_activity_at=now)
    )
    event = ScoreEvent(
        id=uuid.uuid4(),
        match_id=match.id,
        group_id=match.group_id,
        kind=kind,
        side=getattr(parsed, "side", None),
        delta=0,
        score_a=match.score_a,
        score_b=match.score_b,
        source=source,
        created_at=now,
    )
    session.add(event)
    await session.flush()
    result = await plugin.apply_event(
        session, PluginEventContext(match=match, event=event, payload=parsed)
    )

    follow_up = result.follow_up_point
    if follow_up is not None:
        column = Match.score_a if follow_up.side == "A" else Match.score_b
        row = (
            await session.execute(
                update(Match)
                .where(Match.id == match.id, Match.status == "in_progress")
                .values(**{column.key: column + follow_up.delta})
                .returning(Match.score_a, Match.score_b)
            )
        ).first()
        if row is None:
            await session.rollback()
            raise ApiError("MATCH_NOT_IN_PROGRESS", status_code=409)
        point = ScoreEvent(
            id=follow_up.event_id,
            match_id=match.id,
            group_id=match.group_id,
            kind="point",
            side=follow_up.side,
            delta=follow_up.delta,
            score_a=row.score_a,
            score_b=row.score_b,
            source=source,
            created_at=now,
        )
        session.add(point)
        await plugin.on_spine_event(session, SpineEventContext(match=match, event=point))

    await session.commit()
    await session.refresh(match)

    if follow_up is not None and match.end_mode == "target":
        mine, theirs = (
            (match.score_a, match.score_b)
            if follow_up.side == "A"
            else (match.score_b, match.score_a)
        )
        if match_wins(mine, theirs, match.target_score, match.cap_score, match.win_by):
            await _complete_match(session, match, court, follow_up.side)
            return _score_mutation_result(
                applied=True,
                match=match,
                score_event_id=event.id,
                follow_up_score_event_id=follow_up.event_id,
            )

    await publish(
        court_channel(str(match.group_id), str(court.id)),
        "match.eventApplied",
        {
            "match_id": str(match.id),
            "score_a": match.score_a,
            "score_b": match.score_b,
            "sport_state": result.live_payload,
            "score_event_id": str(event.id),
        },
    )
    return _score_mutation_result(
        applied=True,
        match=match,
        score_event_id=event.id,
        sport_state=result.live_payload,
        follow_up_score_event_id=follow_up.event_id if follow_up is not None else None,
    )


async def undo_last_event(
    session: AsyncSession, court: Court, match_id: uuid.UUID
) -> ScoreMutationResult:
    """043 contracts/match-events-api.md §4: take back the match's last
    action — every spine row with the latest `created_at` (one call of
    apply_score_delta() or apply_plugin_event()). The plugin's own rows go
    with them (ON DELETE CASCADE) and the match score drops by the removed
    points. Net rally refuses (it corrects with −1 instead)."""
    match = await _fetch_match_for_court(session, court, match_id)
    plugin = registry.get(match.type_key)
    if match.status != "in_progress":
        raise ApiError("MATCH_NOT_IN_PROGRESS", status_code=409)
    if not plugin.can_undo(match):
        raise ApiError("UNDO_NOT_SUPPORTED", status_code=409)

    latest = (
        await session.execute(
            select(func.max(ScoreEvent.created_at)).where(ScoreEvent.match_id == match.id)
        )
    ).scalar_one_or_none()
    if latest is None:
        raise ApiError("NOTHING_TO_UNDO", status_code=409)
    rows = (
        (
            await session.execute(
                select(ScoreEvent).where(
                    ScoreEvent.match_id == match.id, ScoreEvent.created_at == latest
                )
            )
        )
        .scalars()
        .all()
    )
    taken_a = sum(row.delta for row in rows if row.kind == "point" and row.side == "A")
    taken_b = sum(row.delta for row in rows if row.kind == "point" and row.side == "B")
    if match.score_a - taken_a < 0 or match.score_b - taken_b < 0:
        raise ApiError("UNDO_CONFLICT", status_code=409)

    await session.execute(
        update(Match)
        .where(Match.id == match.id)
        .values(score_a=Match.score_a - taken_a, score_b=Match.score_b - taken_b)
    )
    await session.execute(delete(ScoreEvent).where(ScoreEvent.id.in_([row.id for row in rows])))
    await session.execute(
        update(Group).where(Group.id == match.group_id).values(last_activity_at=datetime.now(UTC))
    )
    await plugin.after_undo(session, match)
    await session.commit()
    await session.refresh(match)

    sport_state = await plugin.live_state(session, match)
    await publish(
        court_channel(str(match.group_id), str(court.id)),
        "match.eventApplied",
        {
            "match_id": str(match.id),
            "score_a": match.score_a,
            "score_b": match.score_b,
            "sport_state": sport_state,
            "score_event_id": None,
        },
    )
    return _score_mutation_result(applied=True, match=match, sport_state=sport_state)


async def finish_match(
    session: AsyncSession, court: Court, match_id: uuid.UUID
) -> ScoreMutationResult:
    """043 FR-017 / contracts/match-events-api.md §3: "end and record the
    result" of a manual-end match — the higher score wins; a level score is a
    draw (`D`) where the group allows draws, otherwise refused. Target-mode
    matches only ever end by reaching the target (or are abandoned)."""
    match = await _fetch_match_for_court(session, court, match_id)
    if match.end_mode != "manual":
        raise ApiError("FINISH_NOT_AVAILABLE", status_code=409)
    if match.status != "in_progress":
        raise ApiError("MATCH_NOT_IN_PROGRESS", status_code=409)
    if match.score_a > match.score_b:
        winner = "A"
    elif match.score_b > match.score_a:
        winner = "B"
    elif match.allow_draw:
        winner = "D"
    else:
        raise ApiError("DRAW_NOT_ALLOWED", status_code=409)
    await _complete_match(session, match, court, winner)
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
    """唯讀版本的「即將登場」預告查詢（research.md #11）——與
    `pull_queued_match_for_court` 共用 `_choose_next_queued_match()` 的挑選
    規則（略過有球員正在其他場地比賽的場次、優先休息較久的球員），只是不帶
    `with_for_update`、不修改 `court_id`/`status`，避免與真正的領取路徑爭搶
    列鎖。以前這裡只取排序第一的場次，連球員還在別的場地上的場次也會被預告，
    跟實際叫到的不一樣。`court_id` 參數目前未用於篩選（同一輪的排隊比賽尚未
    綁定場地），保留供未來場地優先序邏輯使用，並使函式簽章與「這是哪個場地
    的預告」語意保持明確。"""
    choice = await peek_next_call(session, group_id, round_number, court_id)
    return choice.match if choice is not None else None


async def peek_next_call(
    session: AsyncSession, group_id: uuid.UUID, round_number: int, court_id: uuid.UUID
) -> NextMatchChoice | None:
    """037-rest-ready-toggle: `peek_next_queued_match()` plus the
    substitutions the real call-up would make, for the "next up" preview
    (FR-015: it MUST promise exactly what gets called). Read-only — the
    queued match's participants don't change until it is called."""
    del court_id  # 見 peek_next_queued_match()——目前排隊比賽皆未綁定場地
    return await _choose_next_queued_match(session, group_id, round_number, lock=False)


async def court_live_state(session: AsyncSession, court: Court) -> CourtLiveState:
    """組出 `CourtLiveState`（data-model.md）——供公開 `GET .../state` 端點
    與管理頁場地控制區塊共用。`next_up` 由 US3 補上（`peek_next_queued_match`
    尚未接入時恆為 `None`）。"""
    group = (await session.execute(select(Group).where(Group.id == court.group_id))).scalar_one()
    round_number = group.current_round_number

    match_result = await session.execute(
        select(Match).where(Match.court_id == court.id, Match.status == "in_progress")
    )
    match = match_result.scalar_one_or_none()

    current_match: MatchLiveDetail | None = None
    waiting_reason: WaitingReason | None = None
    next_up: NextUpPreview | None = None
    if match is not None:
        participants = await _match_participants_payload(session, match.id)
        current_match = MatchLiveDetail(
            match_id=str(match.id),
            status="in_progress",
            score_a=match.score_a,
            score_b=match.score_b,
            participants=[ParticipantSummary(**p) for p in participants],
            serve=await registry.get(match.type_key).serve_station(session, match),
            detailed_scoring_enabled=match.detailed_scoring_enabled,
            target_score=match.target_score,
            cap_score=match.cap_score,
            **match_sport_fields(match),
            sport_state=await registry.get(match.type_key).live_state(session, match),
        )
    else:
        waiting_reason, next_up = await _idle_court_status(session, group, court.id)

    return CourtLiveState(
        court_id=str(court.id),
        round_number=round_number,
        current_match=current_match,
        waiting_reason=waiting_reason,
        next_up=next_up,
    )


async def _idle_court_status(
    session: AsyncSession, group: Group, court_id: uuid.UUID
) -> tuple[WaitingReason, NextUpPreview | None]:
    """Why an idle court is waiting, and the match it calls next — shared by
    every view of a court (admin/member schedule, live court state,
    `match.ended`) so they all say the same thing.

    037-rest-ready-toggle: the preview is what will actually be called,
    substitutes included (FR-015). When nothing can be called, the reason
    says whether it's resting players holding things up (FR-011, FR-017)."""
    if group.scheduling_mechanism == "manual":
        return "manual_assignment", None
    choice = await peek_next_call(session, group.id, group.current_round_number, court_id)
    if choice is not None:
        return "no_queued_match", await _next_up_preview(session, choice)
    return await _rest_waiting_reason(session, group), None


async def _next_up_preview(session: AsyncSession, choice: NextMatchChoice) -> NextUpPreview:
    """037: the lineup that will play, each substitute in the seat of the
    resting player they replace."""
    participants = await _match_participants_payload(session, choice.match.id)
    if not choice.substitutions:
        return NextUpPreview(
            match_id=str(choice.match.id),
            participants=[ParticipantSummary(**p) for p in participants],
        )
    ids = [pid for pair in choice.substitutions for pid in pair]
    nickname_result = await session.execute(
        select(RosterEntry.id, RosterEntry.nickname).where(RosterEntry.id.in_(ids))
    )
    nicknames = {str(row.id): row.nickname for row in nickname_result.all()}
    substitute_for = {str(resting): str(sub) for resting, sub in choice.substitutions}
    lineup = [
        ParticipantSummary(
            roster_entry_id=substitute_for.get(p["roster_entry_id"], p["roster_entry_id"]),
            nickname=nicknames.get(substitute_for.get(p["roster_entry_id"], ""), p["nickname"]),
            team=cast("Team", p["team"]),
        )
        for p in participants
    ]
    return NextUpPreview(
        match_id=str(choice.match.id),
        participants=lineup,
        substitutions=[
            SubstitutionPreview(
                resting=RosterSummary(roster_entry_id=resting, nickname=nicknames[resting]),
                substitute=RosterSummary(roster_entry_id=sub, nickname=nicknames[sub]),
            )
            for resting, sub in substitute_for.items()
        ],
    )


async def _rest_waiting_reason(session: AsyncSession, group: Group) -> WaitingReason:
    """037: the reason an idle court gives when nothing can be called.
    - held_for_rest: this round's queued matches all wait on resting players;
    - not_enough_ready: nothing queued, continuous rotation can't make a
      four from the idle ready players, and someone is resting;
    - otherwise the old no_queued_match."""
    round_filter = (
        Match.group_id == group.id,
        Match.round_number == group.current_round_number,
        Match.status == "queued",
    )
    queued = await session.execute(select(Match.id).where(*round_filter).limit(1))
    if queued.scalar_one_or_none() is not None:
        playable = await session.execute(
            select(Match.id).where(*round_filter, ~_has_resting_participant()).limit(1)
        )
        return "no_queued_match" if playable.scalar_one_or_none() else "held_for_rest"
    if not _continuous_rotation_applies(group):
        return "no_queued_match"
    anyone_resting = await session.execute(
        select(RosterEntry.id)
        .where(
            RosterEntry.group_id == group.id,
            RosterEntry.status == "active",
            RosterEntry.resting_since.is_not(None),
        )
        .limit(1)
    )
    if anyone_resting.scalar_one_or_none() is None:
        return "no_queued_match"
    busy_result = await session.execute(
        select(MatchParticipant.roster_entry_id)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(Match.group_id == group.id, Match.status == "in_progress")
    )
    busy = set(busy_result.scalars())
    ready = await _get_active_roster_for_selection(session, group.id)
    idle_ready = [pid for pid, _wait, _joined in ready if pid not in busy]
    return "not_enough_ready" if len(idle_ready) < _DOUBLES_PER_MATCH else "no_queued_match"
