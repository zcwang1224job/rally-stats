"""043 contracts/sports-api.md §4–§5: the `sport` filter of a member's match
records and dashboards, and the member's list of activities.

Values: a built-in `sport_key`, `custom:<custom_sport_id>`, `other:<name>`
(an "other" activity by its name) or `custom_or_other`. Left out, only net
rally matches count — activities are never added up together (FR-026), and
a badminton-only member sees exactly what they saw before."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.member.sports_models import MemberSport
from app.domains.schedule.models import Match
from app.sports.catalog import CUSTOM_SPORT_KEY, OTHER_SPORT_KEY, get_builtin, summary_for
from app.sports.presentation import SportSummary

LEGACY_TYPE_KEY = "net_rally"
CUSTOM_OR_OTHER = "custom_or_other"
_CUSTOM_PREFIX = "custom:"
_OTHER_PREFIX = "other:"


@dataclass(frozen=True)
class SportFilter:
    value: str
    sport_key: str | None = None
    custom_sport_id: uuid.UUID | None = None
    other_name: str | None = None
    custom_or_other: bool = False


def parse_sport_filter(value: str | None) -> SportFilter | None:
    """Errors: `INVALID_SPORT_FILTER` (422)."""
    if value is None:
        return None
    if value == CUSTOM_OR_OTHER:
        return SportFilter(value=value, custom_or_other=True)
    if value.startswith(_CUSTOM_PREFIX):
        try:
            return SportFilter(
                value=value, custom_sport_id=uuid.UUID(value.removeprefix(_CUSTOM_PREFIX))
            )
        except ValueError as error:
            raise ApiError("INVALID_SPORT_FILTER", status_code=422) from error
    if value.startswith(_OTHER_PREFIX):
        name = value.removeprefix(_OTHER_PREFIX).strip()
        if not name or len(name) > 20:
            raise ApiError("INVALID_SPORT_FILTER", status_code=422)
        return SportFilter(value=value, other_name=name)
    if get_builtin(value) is None:
        raise ApiError("INVALID_SPORT_FILTER", status_code=422)
    return SportFilter(value=value, sport_key=value)


def sport_condition(sport: SportFilter | None) -> ColumnElement[bool]:
    """A WHERE clause over `Match` joined with its `Group`."""
    if sport is None:
        return Match.type_key == LEGACY_TYPE_KEY
    if sport.custom_or_other:
        return Match.sport_key.in_((CUSTOM_SPORT_KEY, OTHER_SPORT_KEY))
    if sport.custom_sport_id is not None:
        return Group.custom_sport_id == sport.custom_sport_id
    if sport.other_name is not None:
        # A custom activity its owner deleted is shown under its name too.
        return and_(
            Match.sport_name == sport.other_name,
            or_(
                Match.sport_key == OTHER_SPORT_KEY,
                and_(Match.sport_key == CUSTOM_SPORT_KEY, Group.custom_sport_id.is_(None)),
            ),
        )
    return Match.sport_key == sport.sport_key


@dataclass(frozen=True)
class ResolvedActivity:
    """The one activity a filter names: its sport type and default params.
    `type_key` is None for `custom_or_other` (possibly several types) and
    for a custom activity that no longer exists."""

    type_key: str | None
    type_params: Mapping[str, Any]
    summary: SportSummary | None


async def resolve_activity(session: AsyncSession, sport: SportFilter | None) -> ResolvedActivity:
    if sport is None:
        builtin = get_builtin("badminton")
        assert builtin is not None
        return ResolvedActivity(LEGACY_TYPE_KEY, builtin.defaults.type_params, builtin.summary())
    if sport.custom_or_other:
        return ResolvedActivity(None, {}, None)
    if sport.custom_sport_id is not None:
        custom = await session.get(MemberSport, sport.custom_sport_id)
        if custom is None:
            return ResolvedActivity(None, {}, None)
        params = custom.defaults.get("type_params") or {}
        return ResolvedActivity(
            custom.type_key,
            params,
            summary_for(
                sport_key=CUSTOM_SPORT_KEY, type_key=custom.type_key, sport_name=custom.name
            ),
        )
    if sport.other_name is not None:
        other = get_builtin(OTHER_SPORT_KEY)
        assert other is not None
        return ResolvedActivity(
            other.type_key,
            other.defaults.type_params,
            summary_for(
                sport_key=OTHER_SPORT_KEY, type_key=other.type_key, sport_name=sport.other_name
            ),
        )
    builtin = get_builtin(sport.sport_key or "")
    assert builtin is not None
    return ResolvedActivity(builtin.type_key, builtin.defaults.type_params, builtin.summary())


def filter_value_for(
    *, sport_key: str, sport_name: str | None, custom_sport_id: uuid.UUID | None
) -> str:
    """The `sport` value that selects exactly this activity (sports-api §5)."""
    if sport_key == CUSTOM_SPORT_KEY and custom_sport_id is not None:
        return f"{_CUSTOM_PREFIX}{custom_sport_id}"
    if sport_key in (CUSTOM_SPORT_KEY, OTHER_SPORT_KEY):
        return f"{_OTHER_PREFIX}{sport_name or ''}"
    return sport_key
