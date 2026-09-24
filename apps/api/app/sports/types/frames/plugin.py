"""Frames sport type (billiards, darts, board games, esports): a match is
first to N frames; each frame only has a winner, optionally with an in-frame
score kept point by point (spec 043 US3).

The match score IS the frame count (each finished frame adds a spine `point`
to its winner), so core's win rule with win_by=1 and target=N already means
"first to N frames"."""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match
from app.sports.plugin import (
    BasePlugin,
    DashboardContext,
    MatchDetailContext,
    MatchDetailParts,
    PluginEventContext,
    PluginEventResult,
)
from app.sports.presentation import Section
from app.sports.types.frames import events, presentation
from app.sports.types.frames.params import FramesParams, parse_params


class FramesPlugin(BasePlugin):
    type_key: ClassVar[str] = "frames"
    section_kinds: ClassVar[frozenset[str]] = frozenset(
        {"frames.frame_list", "frames.frame_trend", "frames.dashboard_summary"}
    )
    direct_points: ClassVar[bool] = False

    def params_schema(self) -> type[BaseModel]:
        return FramesParams

    def event_schemas(self) -> Mapping[str, type[BaseModel]]:
        return {
            events.FRAME_POINT: events.FramePointPayload,
            events.FRAME_END: events.FrameEndPayload,
        }

    def tables(self) -> Sequence[str]:
        return ("frames_frame_results", "frames_frame_points")

    async def apply_event(
        self, session: AsyncSession, ctx: PluginEventContext
    ) -> PluginEventResult:
        return await events.apply_event(session, ctx)

    async def live_state(self, session: AsyncSession, match: Match) -> Any:
        return await events.live_state(session, match)

    async def match_detail(
        self, session: AsyncSession, ctx: MatchDetailContext
    ) -> MatchDetailParts:
        return await presentation.match_detail(session, ctx)

    async def dashboard_sections(
        self, session: AsyncSession, ctx: DashboardContext
    ) -> list[Section]:
        return await presentation.dashboard_sections(session, ctx)

    def estimate_minutes(
        self, *, end_mode: str, target_score: int, type_params: Mapping[str, Any]
    ) -> float:
        params = parse_params(type_params)
        per_frame = (
            0.5 * params.frame_target
            if params.frame_scoring_enabled and params.frame_target is not None
            else 4.0
        )
        # First to N frames plays at most 2N - 1; assume a typical N + N/2.
        return per_frame * (target_score + target_score / 2)
