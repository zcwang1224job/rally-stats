"""Badminton shot placement (031/032/035), moved here unchanged from
schedule/service.py by spec 043 (research Decision 9). `shot_placement_records`
is a table this plugin owns; core's `attach_shot_placement()` only fetches the
match and hands over.
"""

import uuid
from typing import cast, get_args

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.schedule.models import Match, MatchParticipant, ScoreEvent, ShotPlacementRecord
from app.domains.schedule.schemas import EndingType, Team
from app.sports.types.net_rally.serve import _serve_before_point

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

# A landing that got past the check above while on the CREDITED side's own
# half is a serve-fault landing — the credited side never returned it, so
# its own winner can't have landed there, the loser netting it would have
# left it on the loser's side, and it is in bounds. Only the loser's serve
# fault or some other fault explains it. Mirrors the picker's
# SERVE_FAULT_LANDING_CONTRADICTS.
_SERVE_FAULT_LANDING_CONTRADICTS = ("winner", "out", "net")


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


async def record_shot_placement(
    session: AsyncSession,
    match: Match,
    score_event_id: uuid.UUID,
    roster_entry_id: uuid.UUID | None,
    losing_roster_entry_id: uuid.UUID | None,
    landing_x: float | None,
    landing_y: float | None,
    ending_type: str | None,
) -> None:
    """The body of core's `attach_shot_placement()` — see its docstring for
    the full 031/032/035 rules. Validates, then adds the row and commits."""
    match_id = match.id

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
    if score_event.kind != "point" or score_event.delta <= 0:
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
            if (
                score_event.side == landing_side
                and ending_type in _SERVE_FAULT_LANDING_CONTRADICTS
            ):
                raise ApiError("ENDING_TYPE_CONTRADICTS_LANDING", status_code=422)
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
