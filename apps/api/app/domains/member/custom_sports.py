"""043 US4 (contracts/sports-api.md §2, FR-004): a member's own activities —
a name, a sport type and its default parameters, reused whenever they open a
group. No PATCH this release (clarify Q3); a group keeps its own snapshot,
so deleting one never touches existing groups."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.sport_params import CommonParams, SportParamsError, validate_common_params
from app.domains.member.sports_models import MAX_CUSTOM_SPORTS_PER_MEMBER, MemberSport
from app.sports import registry
from app.sports.plugin import UnknownSportType
from app.sports.presentation import Nouns


class CustomSportDefaults(CommonParams):
    model_config = ConfigDict(extra="forbid")

    team_size: int
    type_params: dict[str, Any] = {}
    nouns: Nouns = Nouns(venue="venue", score="point", member="player")


class CustomSportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=20)
    type_key: str = Field(min_length=1, max_length=16)
    team_size_options: list[int] = Field(min_length=1)
    defaults: CustomSportDefaults

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


def _invalid(field: str) -> ApiError:
    return ApiError("VALIDATION_ERROR", status_code=422, detail={"field": field})


async def create_custom_sport(
    session: AsyncSession, member_id: uuid.UUID, payload: CustomSportCreate
) -> MemberSport:
    """Errors: `VALIDATION_ERROR` (422, `detail.field` names the rule),
    `CUSTOM_SPORT_NAME_TAKEN` (409), `CUSTOM_SPORT_LIMIT` (409). A name
    equal to a built-in activity's is fine — it is the member's own."""
    try:
        plugin = registry.get(payload.type_key)
    except UnknownSportType as error:
        raise _invalid("type_key") from error
    low, high = plugin.team_size_range
    options = payload.team_size_options
    if options != sorted(set(options)) or any(not low <= size <= high for size in options):
        raise _invalid("team_size_options")
    defaults = payload.defaults
    if defaults.team_size not in options:
        raise _invalid("defaults.team_size")
    try:
        validate_common_params(CommonParams.model_validate(defaults.model_dump(
            include=set(CommonParams.model_fields)
        )))
    except SportParamsError as error:
        raise _invalid(f"defaults.{error.field}") from error
    try:
        type_params = plugin.parse_params(defaults.type_params).model_dump(mode="json")
    except ValidationError as error:
        raise _invalid("defaults.type_params") from error

    count = (
        await session.execute(
            select(func.count()).select_from(MemberSport).where(MemberSport.member_id == member_id)
        )
    ).scalar_one()
    if count >= MAX_CUSTOM_SPORTS_PER_MEMBER:
        raise ApiError(
            "CUSTOM_SPORT_LIMIT",
            status_code=409,
            detail={"limit": MAX_CUSTOM_SPORTS_PER_MEMBER},
        )
    sport = MemberSport(
        member_id=member_id,
        name=payload.name,
        type_key=payload.type_key,
        team_size_options=options,
        defaults={**defaults.model_dump(mode="json"), "type_params": type_params},
    )
    session.add(sport)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ApiError("CUSTOM_SPORT_NAME_TAKEN", status_code=409) from error
    await session.refresh(sport)
    return sport


async def delete_custom_sport(
    session: AsyncSession, member_id: uuid.UUID, sport_id: uuid.UUID
) -> None:
    """Hard delete. Groups opened from it keep their name and parameters
    (their `custom_sport_id` becomes null). Errors:
    `CUSTOM_SPORT_NOT_FOUND` (404, also for someone else's)."""
    sport = await session.get(MemberSport, sport_id)
    if sport is None or sport.member_id != member_id:
        raise ApiError("CUSTOM_SPORT_NOT_FOUND", status_code=404)
    await session.delete(sport)
    await session.commit()
