"""The sport type plugin interface (spec 043 data-model §10,
contracts/plugin-boundary.md §2).

Core calls these hooks at fixed points of its own flows; a plugin never calls
core services and never publishes realtime events (constitution XII): what it
wants published it returns (`SpineEffect.live_payload`,
`PluginEventResult.live_payload`), and core sends it.

`BasePlugin` gives every hook a do-nothing default so a sport type only
overrides what it needs.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.schedule.models import Match, MatchParticipant, ScoreEvent
from app.domains.schedule.schemas import ServeStationInfo
from app.sports.presentation import Section

Team = Literal["A", "B"]


class UnknownSportType(KeyError):
    """No plugin is registered under this type key."""


class EmptyParams(BaseModel):
    """`type_params` of a sport type without type-specific parameters."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class SpineEventContext:
    """A `point` row core has just added (not yet committed). `event.score_a`
    / `event.score_b` are the totals the scoring UPDATE just produced —
    `match.score_a`/`score_b` are not refreshed until after the commit."""

    match: Match
    event: ScoreEvent


@dataclass(frozen=True)
class SpineEffect:
    """What a plugin wants sent to clients with a scoring change: `serve` is
    the serve station (ServeStationInfo's shape) for sport types that track
    one, `sport_state` any other live state."""

    serve: dict[str, str | None] | None = None
    sport_state: Any = None


@dataclass(frozen=True)
class PointDetail:
    """Detail attached to one point after it was scored (badminton's shot
    placement: who scored, who lost it, where it landed, how it ended)."""

    roster_entry_id: uuid.UUID | None
    losing_roster_entry_id: uuid.UUID | None
    landing_x: float | None
    landing_y: float | None
    ending_type: str | None


@dataclass(frozen=True)
class PluginEventContext:
    """A plugin-declared event core has just put on the spine."""

    match: Match
    event: ScoreEvent
    payload: BaseModel


@dataclass(frozen=True)
class FollowUpPoint:
    """A `point` core must add in the same transaction (e.g. a frame won).
    `event_id` is chosen by the plugin so its own row can reference the
    point; both are written in the same flush."""

    side: Team
    event_id: uuid.UUID
    delta: int = 1


@dataclass(frozen=True)
class DashboardRow:
    """One completed match from one player's point of view."""

    match: Match
    player_key: str
    my_team: Team
    result: Literal["win", "loss", "draw"]
    opponent_keys: tuple[str, ...]
    opponent_names: tuple[str, ...]


@dataclass(frozen=True)
class DashboardContext:
    """What a sport type builds a member's per-activity dashboard from:
    their own matches (newest first) and, for group averages (FR-027), every
    player's matches in the same groups."""

    mine: Sequence[DashboardRow]
    peers: Mapping[str, Sequence[DashboardRow]]
    me_key: str


@dataclass(frozen=True)
class PluginEventResult:
    follow_up_point: FollowUpPoint | None = None
    live_payload: Any = None


@dataclass(frozen=True)
class StatExtras:
    """A sport type's per-point history beyond the spine, as the pure
    `match_stats` functions take it (badminton: serve snapshots and shot
    placements, keyed by score event id)."""

    snapshots: Mapping[uuid.UUID, Any]
    placements: Mapping[uuid.UUID, Any]


NO_STAT_EXTRAS = StatExtras(snapshots={}, placements={})


@dataclass(frozen=True)
class MatchDetailContext:
    """What core has already loaded for one completed match's detail page."""

    match: Match
    summary: Any  # group.schemas.MatchRecordSummary
    point_events: Sequence[ScoreEvent]  # kind == 'point', in created_at, id order
    raw_events: Sequence[Any]  # match_stats.RawEvent for point_events
    completeness: str  # complete | partial | none


@dataclass(frozen=True)
class MatchDetailParts:
    """The sport-type-specific part of MatchRecordDetailResponse: per-event
    detail (keyed by score event id), the derived blocks, and the sections
    the page renders (FR-021). Every field defaults to "nothing"."""

    event_details: Mapping[uuid.UUID, Any] = field(default_factory=dict)
    player_stats: list[Any] = field(default_factory=list)
    serve_stats: Any = None
    momentum_stats: Any = None
    tempo_stats: Any = None
    landing_distribution: list[Any] = field(default_factory=list)
    clutch_stats: Any = None
    ending_stats: Any = None
    sections: list[Section] = field(default_factory=list)


class BasePlugin:
    """Default hooks. Subclasses set the ClassVars and override hooks."""

    type_key: ClassVar[str]
    # Optional parts a sport of this type may switch on/off in type_params.
    modules: ClassVar[frozenset[str]] = frozenset()
    # Section kinds this type may emit besides the generic ones.
    section_kinds: ClassVar[frozenset[str]] = frozenset()
    team_size_range: ClassVar[tuple[int, int]] = (1, 2)
    # Whether POST …/score may change the match score directly (frames add
    # points only by ending a frame), and whether it may take a point back
    # with a negative step (net rally's −1; other types undo instead).
    direct_points: ClassVar[bool] = True
    negative_points: ClassVar[bool] = False

    def params_schema(self) -> type[BaseModel]:
        return EmptyParams

    def parse_params(self, raw: Mapping[str, Any]) -> BaseModel:
        return self.params_schema().model_validate(dict(raw))

    def event_schemas(self) -> Mapping[str, type[BaseModel]]:
        return {}

    def module_enabled(self, type_params: Mapping[str, Any], module: str) -> bool:
        """Whether an optional module (e.g. `shot_placement`) is on for a
        group or match with these `type_params`. Types without modules: never."""
        return False

    def tables(self) -> Sequence[str]:
        """Names of the tables this plugin owns (core never queries them)."""
        return ()

    async def on_match_start(
        self, session: AsyncSession, match: Match, participants: Sequence[MatchParticipant]
    ) -> None:
        return None

    async def on_match_requeued(self, session: AsyncSession, match: Match) -> None:
        """A match that had started goes back to the queue (undo of the
        previous match's completion): clear whatever on_match_start set."""
        return None

    async def on_spine_event(self, session: AsyncSession, ctx: SpineEventContext) -> SpineEffect:
        return SpineEffect()

    async def serve_station(self, session: AsyncSession, match: Match) -> ServeStationInfo | None:
        """The live serve station of an in-progress match, if this sport type
        tracks one."""
        return None

    async def record_point_detail(
        self, session: AsyncSession, match: Match, score_event_id: uuid.UUID, detail: PointDetail
    ) -> None:
        """Attach detail (e.g. badminton's shot placement) to a point already
        scored. Sport types without such a module refuse."""
        raise ApiError("MODULE_NOT_SUPPORTED", status_code=409)

    async def apply_event(
        self, session: AsyncSession, ctx: PluginEventContext
    ) -> PluginEventResult:
        raise NotImplementedError(f"{self.type_key} declares no events")

    async def load_stat_extras(
        self, session: AsyncSession, matches: Sequence[Match]
    ) -> dict[uuid.UUID, StatExtras]:
        """Batch-load this type's per-point history for many matches (the
        member dashboard and group benchmark). Missing matches mean none."""
        return {}

    async def match_detail(
        self, session: AsyncSession, ctx: MatchDetailContext
    ) -> MatchDetailParts:
        return MatchDetailParts()

    async def dashboard_sections(
        self, session: AsyncSession, ctx: DashboardContext
    ) -> list[Section]:
        """A member's dashboard for one activity of this type (FR-021)."""
        return []

    def can_undo(self, match: Match) -> bool:
        return True

    async def after_undo(self, session: AsyncSession, match: Match) -> None:
        return None

    async def live_state(self, session: AsyncSession, match: Match) -> Any:
        return None

    def estimate_minutes(
        self, *, end_mode: str, target_score: int, type_params: Mapping[str, Any]
    ) -> float:
        """Rough playing time of one match before the group has measured any
        (queue-time estimates). About 0.6 minutes per point of the target."""
        if end_mode == "manual":
            return 15.0
        return target_score * 0.6
