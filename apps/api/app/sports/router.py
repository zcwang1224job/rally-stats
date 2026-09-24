"""`GET /sports` — the activity catalogue (spec 043 contracts/sports-api.md §1).

Core: built from the registry and the catalogue, never from a plugin module.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domains.member.models import Member
from app.domains.member.security import optional_member
from app.domains.member.sports_models import MemberSport
from app.sports import catalog, registry
from app.sports.presentation import Nouns

router = APIRouter(tags=["sports"])


class SportTypeView(BaseModel):
    type_key: str
    team_size_range: list[int]
    modules: list[str]
    params_schema: dict[str, Any]
    section_kinds: list[str]


class BuiltinSportView(BaseModel):
    sport_key: str
    type_key: str
    name_key: str
    icon: str
    team_size_options: list[int]
    defaults: dict[str, Any]
    nouns: Nouns


class CustomSportView(BaseModel):
    id: str
    name: str
    type_key: str
    team_size_options: list[int]
    defaults: dict[str, Any]
    created_at: datetime


class SportsCatalogResponse(BaseModel):
    types: list[SportTypeView]
    builtin: list[BuiltinSportView]
    custom: list[CustomSportView]


def custom_sport_view(sport: MemberSport) -> CustomSportView:
    return CustomSportView(
        id=str(sport.id),
        name=sport.name,
        type_key=sport.type_key,
        team_size_options=list(sport.team_size_options),
        defaults=dict(sport.defaults),
        created_at=sport.created_at,
    )


@router.get("/sports", response_model=SportsCatalogResponse)
async def get_sports(
    session: Annotated[AsyncSession, Depends(get_session)],
    member: Annotated[Member | None, Depends(optional_member)],
) -> SportsCatalogResponse:
    """Every sport type (with its `type_params` JSON Schema), the built-in
    activities in catalogue order ("other" last), and — for a logged-in
    member — their own custom activities. Public."""
    types = [
        SportTypeView(
            type_key=plugin.type_key,
            team_size_range=list(plugin.team_size_range),
            modules=sorted(plugin.modules),
            params_schema=plugin.params_schema().model_json_schema(),
            section_kinds=sorted(plugin.section_kinds),
        )
        for plugin in registry.plugins()
    ]
    builtin = [
        BuiltinSportView(
            sport_key=sport.sport_key,
            type_key=sport.type_key,
            name_key=sport.name_key,
            icon=sport.icon,
            team_size_options=list(sport.team_size_options),
            defaults=sport.defaults.as_dict(),
            nouns=sport.nouns,
        )
        for sport in catalog.BUILTIN_SPORTS
    ]
    custom: list[CustomSportView] = []
    if member is not None:
        rows = await session.execute(
            select(MemberSport)
            .where(MemberSport.member_id == member.id)
            .order_by(MemberSport.created_at, MemberSport.name)
        )
        custom = [custom_sport_view(row) for row in rows.scalars()]
    return SportsCatalogResponse(types=types, builtin=builtin, custom=custom)
