"""Generic sport type: only a score and a result — the fallback for any
activity the catalogue does not cover (spec 043 US5). Points go straight on
the spine in any step the group allows (+N), matches end at the target or
when the scorer ends them, and a level manual end may be a draw."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.sports.plugin import (
    BasePlugin,
    DashboardContext,
    MatchDetailContext,
    MatchDetailParts,
)
from app.sports.presentation import Section
from app.sports.types.generic import presentation


class GenericParams(BaseModel):
    """No type-specific parameters this release (data-model §7)."""

    model_config = ConfigDict(extra="forbid")


class GenericPlugin(BasePlugin):
    type_key: ClassVar[str] = "generic"

    def params_schema(self) -> type[BaseModel]:
        return GenericParams

    async def match_detail(
        self, session: AsyncSession, ctx: MatchDetailContext
    ) -> MatchDetailParts:
        return await presentation.match_detail(session, ctx)

    async def dashboard_sections(
        self, session: AsyncSession, ctx: DashboardContext
    ) -> list[Section]:
        return await presentation.dashboard_sections(session, ctx)
