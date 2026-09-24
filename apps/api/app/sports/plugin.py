"""The sport type plugin interface (spec 043 data-model §10,
contracts/plugin-boundary.md §2).

Core calls these hooks at fixed points of its own flows; a plugin never calls
core services and never publishes realtime events (constitution XII): what it
wants published it returns (`SpineEffect.live_payload`,
`PluginEventResult.live_payload`), and core sends it.

`BasePlugin` gives every hook a do-nothing default so a sport type only
overrides what it needs.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match, MatchParticipant, ScoreEvent

Team = Literal["A", "B"]


class UnknownSportType(KeyError):
    """No plugin is registered under this type key."""


class EmptyParams(BaseModel):
    """`type_params` of a sport type without type-specific parameters."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class SpineEventContext:
    """A `point` row core has just added (not yet committed)."""

    match: Match
    event: ScoreEvent
    participants: Sequence[MatchParticipant]


@dataclass(frozen=True)
class SpineEffect:
    """What a plugin wants attached to a scoring change: `live_payload` is
    sent to clients with it (badminton: the serve station)."""

    live_payload: Any = None


@dataclass(frozen=True)
class PluginEventContext:
    """A plugin-declared event core has just put on the spine."""

    match: Match
    event: ScoreEvent
    payload: BaseModel
    participants: Sequence[MatchParticipant]


@dataclass(frozen=True)
class FollowUpPoint:
    """A `point` core must add in the same transaction (e.g. a frame won)."""

    side: Team
    delta: int = 1


@dataclass(frozen=True)
class PluginEventResult:
    follow_up_point: FollowUpPoint | None = None
    live_payload: Any = None


class BasePlugin:
    """Default hooks. Subclasses set the ClassVars and override hooks."""

    type_key: ClassVar[str]
    # Optional parts a sport of this type may switch on/off in type_params.
    modules: ClassVar[frozenset[str]] = frozenset()
    # Section kinds this type may emit besides the generic ones.
    section_kinds: ClassVar[frozenset[str]] = frozenset()
    team_size_range: ClassVar[tuple[int, int]] = (1, 2)

    def params_schema(self) -> type[BaseModel]:
        return EmptyParams

    def parse_params(self, raw: Mapping[str, Any]) -> BaseModel:
        return self.params_schema().model_validate(dict(raw))

    def event_schemas(self) -> Mapping[str, type[BaseModel]]:
        return {}

    def tables(self) -> Sequence[str]:
        """Names of the tables this plugin owns (core never queries them)."""
        return ()

    async def on_match_start(
        self, session: AsyncSession, match: Match, participants: Sequence[MatchParticipant]
    ) -> None:
        return None

    async def on_match_requeued(self, session: AsyncSession, match: Match) -> None:
        return None

    async def on_spine_event(self, session: AsyncSession, ctx: SpineEventContext) -> SpineEffect:
        return SpineEffect()

    async def apply_event(
        self, session: AsyncSession, ctx: PluginEventContext
    ) -> PluginEventResult:
        raise NotImplementedError(f"{self.type_key} declares no events")

    def can_undo(self, match: Match) -> bool:
        return True

    async def after_undo(self, session: AsyncSession, match: Match) -> None:
        return None

    async def live_state(self, session: AsyncSession, match: Match) -> Any:
        return None

    def estimate_minutes(self, match: Match) -> float:
        """Rough playing time of one match, for queue-time estimates."""
        if match.end_mode == "manual":
            return 15.0
        return 0.6 * match.target_score
