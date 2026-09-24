"""Net rally sport type (badminton, table tennis, pickleball, tennis
tie-break): one game per match, every rally scores, first to target with a
win_by lead or to the cap. Badminton's serve tracking and shot placement are
optional modules of this type (spec 043 FR-002, research Decision 9)."""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, cast

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.schemas import ServeStationInfo, Team
from app.sports.plugin import (
    BasePlugin,
    DashboardContext,
    MatchDetailContext,
    MatchDetailParts,
    PointDetail,
    SpineEffect,
    SpineEventContext,
    StatExtras,
)
from app.sports.presentation import Section
from app.sports.types.net_rally import detail, placement, serve
from app.sports.types.net_rally.params import NetRallyParams, parse_params

# Match-dashboard metric keys fed by each module (034/035's catalogue).
SERVE_METRICS = frozenset({"team_serve", "team_receive", "own_serve", "own_receive"})
ENDING_METRICS = frozenset(
    {
        "winner_share",
        "winners_per_match",
        "errors_per_match",
        "error_share_of_lost",
        "winner_error_ratio",
    }
)


class NetRallyPlugin(BasePlugin):
    type_key: ClassVar[str] = "net_rally"
    modules: ClassVar[frozenset[str]] = frozenset({"serve_tracking", "shot_placement"})
    section_kinds: ClassVar[frozenset[str]] = frozenset(
        {"net_rally.match_detail", "net_rally.dashboard"}
    )
    negative_points: ClassVar[bool] = True

    def params_schema(self) -> type[BaseModel]:
        return NetRallyParams

    def tables(self) -> Sequence[str]:
        return ("score_serve_records", "shot_placement_records")

    def module_enabled(self, type_params: Mapping[str, Any], module: str) -> bool:
        modules = parse_params(type_params).modules
        return bool(getattr(modules, module, False))

    def hidden_dashboard_metrics(self, type_params: Mapping[str, Any]) -> frozenset[str]:
        modules = parse_params(type_params).modules
        hidden: set[str] = set()
        if not modules.serve_tracking:
            hidden |= SERVE_METRICS
        if not modules.shot_placement:
            hidden |= ENDING_METRICS | {"landing", "error_breakdown"}
        return frozenset(hidden)

    async def on_match_start(
        self, session: AsyncSession, match: Match, participants: Sequence[MatchParticipant]
    ) -> None:
        if parse_params(match.type_params).modules.serve_tracking:
            await serve._initialize_serve_state(session, match)

    async def on_match_requeued(self, session: AsyncSession, match: Match) -> None:
        # Reverses on_match_start(): a requeued match has no serve state.
        match.serving_team = None
        match.team_a_reference_server_id = None
        match.team_b_reference_server_id = None

    async def on_spine_event(self, session: AsyncSession, ctx: SpineEventContext) -> SpineEffect:
        match, event = ctx.match, ctx.event
        side = cast(Team, event.side)
        tracks_serve = parse_params(match.type_params).modules.serve_tracking
        if event.delta > 0:
            if not tracks_serve:
                return SpineEffect()
            # 030-score-serve-record FR-001/FR-004: only a genuine point
            # advances the serve state and leaves a snapshot — `-1` MUST NOT.
            record = await serve._advance_serve_state_and_snapshot(
                session, match, side, event.score_a, event.score_b
            )
            record.score_event_id = event.id
            session.add(record)
            return SpineEffect(serve=serve.station_payload(record))

        # 031-shot-placement-scoring FR-007/research.md Decision 3: a
        # correction (-1) collapses the last point for this side —
        # unconditional: a match without shot placement never has a row, so
        # this is a harmless no-op there.
        await placement._remove_last_shot_placement_record(session, match.id, side)
        if not tracks_serve:
            return SpineEffect()
        await serve._restore_serve_state_after_correction(
            session, match, event.score_a, event.score_b
        )
        # `-1` never advances the serve state (030 Decision 5): recompute the
        # station from the (restored) serve state and the corrected score.
        station = await serve._build_serve_station(session, match, event.score_a, event.score_b)
        return SpineEffect(serve=station.model_dump() if station is not None else None)

    async def serve_station(self, session: AsyncSession, match: Match) -> ServeStationInfo | None:
        return await serve._build_serve_station(session, match)

    async def record_point_detail(
        self, session: AsyncSession, match: Match, score_event_id: uuid.UUID, detail: PointDetail
    ) -> None:
        if not self.module_enabled(match.type_params, "shot_placement"):
            raise ApiError("MODULE_NOT_SUPPORTED", status_code=409)
        await placement.record_shot_placement(
            session,
            match,
            score_event_id,
            detail.roster_entry_id,
            detail.losing_roster_entry_id,
            detail.landing_x,
            detail.landing_y,
            detail.ending_type,
        )

    async def load_stat_extras(
        self, session: AsyncSession, matches: Sequence[Match]
    ) -> dict[uuid.UUID, StatExtras]:
        return await detail.load_stat_extras(session, matches)

    async def match_detail(
        self, session: AsyncSession, ctx: MatchDetailContext
    ) -> MatchDetailParts:
        return await detail.match_detail(session, ctx)

    async def dashboard_sections(
        self, session: AsyncSession, ctx: DashboardContext
    ) -> list[Section]:
        # A marker: the section fetches /match-dashboard itself, which keeps
        # badminton's dashboard exactly as it was (research Decision 12).
        return [Section(kind="net_rally.dashboard")]

    def can_undo(self, match: Match) -> bool:
        # Net rally corrects with −1 (a negative point on the timeline);
        # deleting spine rows would leave its serve snapshots inconsistent.
        return False
