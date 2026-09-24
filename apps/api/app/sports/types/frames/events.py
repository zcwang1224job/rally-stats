"""Frames events (spec 043 data-model §7 事件規則): in-frame points and the
end of a frame. Each is a spine event core has already added; this writes the
plugin's own rows and says whether the match score moves."""

import uuid
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.schedule.models import Match
from app.sports.plugin import FollowUpPoint, PluginEventContext, PluginEventResult
from app.sports.types.frames.models import FramePoint, FrameResult
from app.sports.types.frames.params import FramesParams, parse_params

FRAME_POINT = "frames.frame_point"
FRAME_END = "frames.frame_end"


class FramePointPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["A", "B"]
    delta: Literal[1, -1]


class FrameEndPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    winner_team: Literal["A", "B"]


async def current_frame(session: AsyncSession, match_id: uuid.UUID) -> tuple[int, int, int]:
    """(frame number being played, its in-frame score A, B)."""
    finished = (
        await session.execute(
            select(func.count()).select_from(FrameResult).where(FrameResult.match_id == match_id)
        )
    ).scalar_one()
    frame_no = int(finished) + 1
    last = (
        await session.execute(
            select(FramePoint.frame_score_a, FramePoint.frame_score_b)
            .where(FramePoint.match_id == match_id, FramePoint.frame_no == frame_no)
            .order_by(FramePoint.created_at.desc(), FramePoint.score_event_id.desc())
            .limit(1)
        )
    ).first()
    if last is None:
        return frame_no, 0, 0
    return frame_no, int(last.frame_score_a), int(last.frame_score_b)


def _frame_won(mine: int, theirs: int, params: FramesParams) -> bool:
    return (
        params.frame_target is not None
        and mine >= params.frame_target
        and mine - theirs >= params.frame_win_by
    )


def _end_frame(
    session: AsyncSession,
    match: Match,
    *,
    frame_no: int,
    winner: Literal["A", "B"],
    score: tuple[int, int] | None,
    ended_by: Literal["target", "manual"],
) -> FollowUpPoint:
    point_id = uuid.uuid4()
    session.add(
        FrameResult(
            score_event_id=point_id,
            match_id=match.id,
            frame_no=frame_no,
            winner_team=winner,
            score_a=score[0] if score is not None else None,
            score_b=score[1] if score is not None else None,
            ended_by=ended_by,
        )
    )
    return FollowUpPoint(side=winner, event_id=point_id)


async def apply_event(session: AsyncSession, ctx: PluginEventContext) -> PluginEventResult:
    match = ctx.match
    params = parse_params(match.type_params)
    frame_no, score_a, score_b = await current_frame(session, match.id)

    if isinstance(ctx.payload, FramePointPayload):
        if not params.frame_scoring_enabled:
            raise ApiError("FRAME_SCORING_DISABLED", status_code=409)
        side, delta = ctx.payload.side, ctx.payload.delta
        new_a = score_a + (delta if side == "A" else 0)
        new_b = score_b + (delta if side == "B" else 0)
        if new_a < 0 or new_b < 0:
            raise ApiError("FRAME_SCORE_FLOOR", status_code=409)
        session.add(
            FramePoint(
                score_event_id=ctx.event.id,
                match_id=match.id,
                frame_no=frame_no,
                side=side,
                delta=delta,
                frame_score_a=new_a,
                frame_score_b=new_b,
            )
        )
        winner: Literal["A", "B"] | None = None
        if delta > 0 and _frame_won(new_a, new_b, params):
            winner = "A"
        elif delta > 0 and _frame_won(new_b, new_a, params):
            winner = "B"
        if winner is None:
            return PluginEventResult(live_payload=_state(params, match, frame_no, new_a, new_b))
        follow_up = _end_frame(
            session,
            match,
            frame_no=frame_no,
            winner=winner,
            score=(new_a, new_b),
            ended_by="target",
        )
        return PluginEventResult(
            follow_up_point=follow_up,
            live_payload=_state(params, match, frame_no + 1, 0, 0),
        )

    assert isinstance(ctx.payload, FrameEndPayload)
    follow_up = _end_frame(
        session,
        match,
        frame_no=frame_no,
        winner=ctx.payload.winner_team,
        score=(score_a, score_b) if params.frame_scoring_enabled else None,
        ended_by="manual",
    )
    return PluginEventResult(
        follow_up_point=follow_up, live_payload=_state(params, match, frame_no + 1, 0, 0)
    )


def _state(
    params: FramesParams, match: Match, frame_no: int, score_a: int, score_b: int
) -> dict[str, object]:
    return {
        "frame_no": frame_no,
        "frame_score_a": score_a,
        "frame_score_b": score_b,
        "frames_to_win": match.target_score,
        "frame_scoring_enabled": params.frame_scoring_enabled,
        "frame_target": params.frame_target,
    }


async def live_state(session: AsyncSession, match: Match) -> dict[str, object]:
    params = parse_params(match.type_params)
    frame_no, score_a, score_b = await current_frame(session, match.id)
    return _state(params, match, frame_no, score_a, score_b)


async def frame_results(
    session: AsyncSession, match_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[FrameResult]]:
    by_match: dict[uuid.UUID, list[FrameResult]] = {match_id: [] for match_id in match_ids}
    if not match_ids:
        return by_match
    rows = await session.execute(
        select(FrameResult)
        .where(FrameResult.match_id.in_(list(match_ids)))
        .order_by(FrameResult.match_id, FrameResult.frame_no)
    )
    for row in rows.scalars():
        by_match[row.match_id].append(row)
    return by_match
