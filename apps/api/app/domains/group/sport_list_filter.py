"""043 US6 (contracts/sports-api.md §4): the `sport` filter of the group
list and of a member's own groups. Values: a built-in `sport_key`,
`custom_or_other`, and — only for a member's own list — `custom:<id>` of one
of their custom activities (someone else's id gives an empty list)."""

import uuid

from sqlalchemy import ColumnElement, and_, select

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.member.sports_models import MemberSport
from app.sports.catalog import CUSTOM_SPORT_KEY, OTHER_SPORT_KEY, get_builtin

CUSTOM_OR_OTHER = "custom_or_other"
_CUSTOM_PREFIX = "custom:"


def group_sport_condition(
    value: str | None, *, member_id: uuid.UUID | None = None
) -> ColumnElement[bool] | None:
    """None when there is nothing to filter. Errors: `INVALID_SPORT_FILTER`
    (422) — `custom:<id>` is only understood with a `member_id`."""
    if value is None:
        return None
    if value == CUSTOM_OR_OTHER:
        return Group.sport_key.in_((CUSTOM_SPORT_KEY, OTHER_SPORT_KEY))
    if value.startswith(_CUSTOM_PREFIX):
        if member_id is None:
            raise ApiError("INVALID_SPORT_FILTER", status_code=422)
        try:
            sport_id = uuid.UUID(value.removeprefix(_CUSTOM_PREFIX))
        except ValueError as error:
            raise ApiError("INVALID_SPORT_FILTER", status_code=422) from error
        mine = (
            select(MemberSport.id)
            .where(MemberSport.id == sport_id, MemberSport.member_id == member_id)
            .exists()
        )
        return and_(Group.custom_sport_id == sport_id, mine)
    if value == CUSTOM_SPORT_KEY or get_builtin(value) is None:
        raise ApiError("INVALID_SPORT_FILTER", status_code=422)
    return Group.sport_key == value


