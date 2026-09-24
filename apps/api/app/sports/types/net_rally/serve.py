"""Badminton serve tracking (030-score-serve-record, 029-serve-rotation-
display), moved here unchanged from schedule/service.py by spec 043
(research Decision 9). The `net_rally` plugin is the only caller; core reaches
it through the plugin hooks.

The serve state itself stays on `matches` (serving_team and the two reference
servers — research F7); the snapshots live in `score_serve_records`, a table
this plugin owns.
"""

import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match, MatchParticipant, ScoreEvent, ScoreServeRecord
from app.domains.schedule.schemas import ServeStationInfo, Team


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
    """(team_a_roster_entry_ids, team_b_roster_entry_ids) of a match."""
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


def _opt_str(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None


def station_payload(station: StationResult | ScoreServeRecord) -> dict[str, str | None]:
    """The `serve` object clients receive (ServeStationInfo's shape)."""
    return {
        "server_roster_entry_id": str(station.server_roster_entry_id),
        "server_team": station.server_team,
        "team_a_right_roster_entry_id": _opt_str(station.team_a_right_roster_entry_id),
        "team_a_left_roster_entry_id": _opt_str(station.team_a_left_roster_entry_id),
        "team_b_right_roster_entry_id": _opt_str(station.team_b_right_roster_entry_id),
        "team_b_left_roster_entry_id": _opt_str(station.team_b_left_roster_entry_id),
    }


async def _build_serve_station(
    session: AsyncSession, match: Match, score_a: int | None = None, score_b: int | None = None
) -> ServeStationInfo | None:
    """029-serve-rotation-display: the *live* equivalent of a
    `ScoreServeRecord` snapshot — computed fresh from `match`'s currently
    persisted serve state + score, not stored anywhere itself. `None` when
    the match has no serve state yet (research.md Decision 4 — a match
    created before 030-score-serve-record's migration).

    `score_a`/`score_b` default to the match's own; the scoring path passes
    the totals its `UPDATE … RETURNING` just produced."""
    if match.serving_team is None:
        return None
    team_a, team_b = await _match_participants_by_team(session, match.id)
    station = _compute_station(
        cast(Team, match.serving_team),
        team_a,
        team_b,
        cast(uuid.UUID, match.team_a_reference_server_id),
        cast(uuid.UUID, match.team_b_reference_server_id),
        match.score_a if score_a is None else score_a,
        match.score_b if score_b is None else score_b,
    )
    return ServeStationInfo(**station_payload(station))


async def _initialize_serve_state(session: AsyncSession, match: Match) -> None:
    """030-score-serve-record FR-001/FR-002 (research.md Decision 4/5):
    called once, exactly when a match becomes `in_progress` — randomly
    assigns the serving team and, for doubles, each team's own reference
    server (both the serving and the receiving side, so `_compute_station()`
    has a starting point for all four slots). Mutates `match` in place;
    caller flushes/commits."""
    team_a, team_b = await _match_participants_by_team(session, match.id)
    match.serving_team = random.choice(("A", "B"))
    match.team_a_reference_server_id = random.choice(team_a)
    match.team_b_reference_server_id = random.choice(team_b)


async def _advance_serve_state_and_snapshot(
    session: AsyncSession, match: Match, side: Team, score_a: int, score_b: int
) -> ScoreServeRecord:
    """030-score-serve-record FR-001~003 (research.md Decision 2). Called
    ONLY for a `+1` — `-1` MUST NOT call this (Decision 5). `score_a`/
    `score_b` are the POST-increment totals from the scoring path's
    `UPDATE ... RETURNING` — NOT `match.score_a`/`score_b`, which the ORM
    instance doesn't reflect until refreshed.

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


async def _restore_serve_state_after_correction(
    session: AsyncSession, match: Match, score_a: int, score_b: int
) -> None:
    """feature/control-panel-scoreboard-style: a `-1` correcting the point
    that just advanced the serve state (a side-out rotation swap — see
    _advance_serve_state_and_snapshot()) previously left
    match.serving_team/team_{a,b}_reference_server_id at their POST-point
    values while only the score itself rolled back — a stale, inconsistent
    combination that showed the wrong server whenever the undone point was a
    side-out. 030-score-serve-record's ScoreServeRecord rows are read-only
    history per its Clarifications (never written or deleted by `-1`) — this
    only reads them to restore match's own LIVE columns. `score_a`/`score_b`
    are this correction's resulting totals; the historical point that
    originally produced that exact score is exactly the state to restore
    back to (robust to undoing several points in a row, not just the single
    most recent one, since it matches by score rather than by position in
    the history).

    043: only `point` spine events can have produced a score, so the lookup
    joins on those alone."""
    prior = (
        await session.execute(
            select(ScoreServeRecord)
            .join(ScoreEvent, ScoreServeRecord.score_event_id == ScoreEvent.id)
            .where(
                ScoreServeRecord.match_id == match.id,
                ScoreEvent.kind == "point",
                ScoreEvent.score_a == score_a,
                ScoreEvent.score_b == score_b,
            )
            .order_by(ScoreServeRecord.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if prior is not None:
        match.serving_team = prior.server_team
        match.team_a_reference_server_id = (
            prior.team_a_right_roster_entry_id
            if score_a % 2 == 0
            else prior.team_a_left_roster_entry_id
        )
        match.team_b_reference_server_id = (
            prior.team_b_right_roster_entry_id
            if score_b % 2 == 0
            else prior.team_b_left_roster_entry_id
        )
    # else: undoing all the way back past this match's first recorded
    # point — no earlier snapshot exists to restore from. If that first
    # point wasn't itself a side-out, match's serve columns were never
    # mutated for it and are already correct as-is; if it WAS, the true
    # pre-match-start random assignment (_initialize_serve_state()) was never
    # persisted anywhere and can't be recovered here — a narrow, accepted gap
    # rather than something this correction can fix.


async def _serve_before_point(
    session: AsyncSession, score_event: ScoreEvent
) -> tuple[str, int] | None:
    """(serving team, that team's own score) going into the rally that
    `score_event` (a +1) credited — the score's parity says which service
    court the serve came from. Its own ScoreServeRecord can't tell — that
    snapshot is taken AFTER the point, and the winner always serves next, so
    its server_team is always the scorer. The team that served this rally
    is the one serving at the PRE-point score, i.e. the server_team of the
    latest earlier +1 that produced that exact score — the same
    match-by-score lookup a -1 uses to restore the serve state, so undone
    points in between don't confuse it. None for a match's first point (the
    pre-match serve assignment isn't persisted) — callers then skip any
    serve-based check, the same fallback the picker uses when it has no
    `servingTeam`."""
    before_a = score_event.score_a - (1 if score_event.side == "A" else 0)
    before_b = score_event.score_b - (1 if score_event.side == "B" else 0)
    server_team = (
        await session.execute(
            select(ScoreServeRecord.server_team)
            .join(ScoreEvent, ScoreServeRecord.score_event_id == ScoreEvent.id)
            .where(
                ScoreServeRecord.match_id == score_event.match_id,
                ScoreEvent.kind == "point",
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
