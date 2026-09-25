"""043 US2/US4: turn a create-group request's activity choice and parameters
into the values a Group stores (contracts/sports-api.md §3).

Three sources of an activity: a built-in (app/sports/catalog.py), "other"
(the generic type, named on the spot, never saved) and a member's own custom
activity (member_sports). Whatever the request leaves out comes from the
activity's defaults; the result is validated as common parameters (core) and
as `type_params` by the sport type's plugin.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.sport_params import CommonParams, SportParamsError, validate_common_params
from app.domains.member.sports_models import MemberSport
from app.sports import catalog, registry

# Pre-043 named scoring presets: (target_score, deuce_threshold, cap_score).
SCORING_PRESETS: dict[str, tuple[int, int, int]] = {
    "21pt": (21, 20, 30),
    "15pt": (15, 14, 21),
}


@dataclass(frozen=True)
class ResolvedSport:
    sport_key: str
    type_key: str
    sport_name: str | None
    custom_sport_id: uuid.UUID | None
    team_size_options: tuple[int, ...]
    defaults: dict[str, Any]


@dataclass(frozen=True)
class ResolvedParams:
    scoring_mode: str
    target_score: int
    deuce_threshold: int
    cap_score: int | None
    end_mode: Literal["target", "manual"]
    win_by: int
    allow_draw: bool
    score_steps: list[int]
    type_params: dict[str, Any]


async def resolve_sport(
    session: AsyncSession,
    *,
    sport_key: str | None,
    custom_sport_id: uuid.UUID | None,
    name: str | None,
    member_id: uuid.UUID | None,
) -> ResolvedSport:
    """Which activity a new group is for. No sport at all means the default
    (badminton), so every pre-043 request keeps creating exactly the group
    it always did."""
    key = sport_key or catalog.DEFAULT_SPORT_KEY
    if key == catalog.CUSTOM_SPORT_KEY:
        if member_id is None or custom_sport_id is None:
            raise ApiError("CUSTOM_SPORT_FORBIDDEN", status_code=403)
        custom = (
            await session.execute(select(MemberSport).where(MemberSport.id == custom_sport_id))
        ).scalar_one_or_none()
        if custom is None or custom.member_id != member_id:
            raise ApiError("CUSTOM_SPORT_FORBIDDEN", status_code=403)
        return ResolvedSport(
            sport_key=catalog.CUSTOM_SPORT_KEY,
            type_key=custom.type_key,
            sport_name=custom.name,
            custom_sport_id=custom.id,
            team_size_options=tuple(custom.team_size_options),
            defaults=dict(custom.defaults),
        )
    builtin = catalog.get_builtin(key)
    if builtin is None:
        raise ApiError("UNKNOWN_SPORT", status_code=422, detail={"sport_key": key})
    if key == catalog.OTHER_SPORT_KEY and not name:
        raise ApiError("SPORT_NAME_REQUIRED", status_code=422)
    return ResolvedSport(
        sport_key=builtin.sport_key,
        type_key=builtin.type_key,
        sport_name=name if key == catalog.OTHER_SPORT_KEY else None,
        custom_sport_id=None,
        team_size_options=builtin.team_size_options,
        defaults=builtin.defaults.as_dict(),
    )


def resolve_params(
    sport: ResolvedSport,
    *,
    given: dict[str, Any],
    scoring_mode: str | None,
    custom_scoring: tuple[int, int, int] | None,
) -> ResolvedParams:
    """The activity's defaults, overridden by what the request gave.

    `given` holds only the fields the request actually sent (so an explicit
    `cap_score: null` — "no cap" — differs from leaving it out). A named
    preset (21pt/15pt) or `custom_scoring` supplies target/deuce/cap the
    pre-043 way; explicit top-level values win over both."""
    defaults = sport.defaults
    mode = scoring_mode or defaults.get("scoring_mode", "custom")
    if scoring_mode is None and mode in SCORING_PRESETS and (
        "target_score" in given or "cap_score" in given or "deuce_threshold" in given
    ):
        # Explicit numbers without a named preset are a custom scheme, not
        # the preset with its numbers quietly replaced.
        mode = "custom"
    if mode in SCORING_PRESETS:
        target, deuce, cap = SCORING_PRESETS[mode]
        base_cap: int | None = cap
    elif custom_scoring is not None:
        target, deuce, cap = custom_scoring
        base_cap = cap
    else:
        target = int(defaults["target_score"])
        base_cap = defaults.get("cap_score")
        deuce = max(target - 1, 0)

    target = int(given.get("target_score", target))
    if "target_score" in given and "deuce_threshold" not in given and mode not in SCORING_PRESETS:
        deuce = max(target - 1, 0)
    final_cap: int | None = given["cap_score"] if "cap_score" in given else base_cap

    common = CommonParams(
        end_mode=given.get("end_mode", defaults["end_mode"]),
        target_score=target,
        win_by=given.get("win_by", defaults["win_by"]),
        cap_score=final_cap,
        allow_draw=given.get("allow_draw", defaults["allow_draw"]),
        score_steps=list(given.get("score_steps", defaults["score_steps"])),
    )
    try:
        validate_common_params(common)
    except SportParamsError as error:
        raise ApiError(
            "INVALID_SPORT_PARAMS", status_code=422, detail={"field": error.field}
        ) from error

    raw_type_params = given.get("type_params", defaults.get("type_params", {}))
    type_params = validate_type_params(sport.type_key, raw_type_params or {})
    return ResolvedParams(
        scoring_mode=mode,
        target_score=common.target_score,
        deuce_threshold=deuce,
        cap_score=common.cap_score,
        end_mode=common.end_mode,
        win_by=common.win_by,
        allow_draw=common.allow_draw,
        score_steps=common.score_steps,
        type_params=type_params,
    )


def validate_type_params(type_key: str, raw: dict[str, Any]) -> dict[str, Any]:
    """The sport type plugin's own schema decides what `type_params` may hold."""
    try:
        parsed = registry.get(type_key).parse_params(raw)
    except ValidationError as error:
        raise ApiError(
            "INVALID_SPORT_PARAMS", status_code=422, detail={"field": "type_params"}
        ) from error
    return parsed.model_dump()


async def team_size_options_for(
    session: AsyncSession, *, sport_key: str, custom_sport_id: uuid.UUID | None
) -> tuple[int, ...]:
    """The team sizes a group's activity allows (editing may not leave them).
    A deleted custom activity no longer says; any size this release supports
    then stays allowed."""
    if custom_sport_id is not None:
        custom = (
            await session.execute(
                select(MemberSport.team_size_options).where(MemberSport.id == custom_sport_id)
            )
        ).scalar_one_or_none()
        if custom is not None:
            return tuple(custom)
    builtin = catalog.get_builtin(sport_key)
    if builtin is not None:
        return builtin.team_size_options
    return (1, 2)


def scoring_presets_for(sport_key: str) -> list[str]:
    """The named presets a group's activity offers (the admin page's scoring
    select): those of a built-in whose default is a preset, none otherwise."""
    builtin = catalog.get_builtin(sport_key)
    if builtin is not None and builtin.defaults.scoring_mode in SCORING_PRESETS:
        return list(SCORING_PRESETS)
    return []


def check_team_size(sport: ResolvedSport, team_size: int) -> None:
    if team_size not in sport.team_size_options:
        raise ApiError(
            "TEAM_SIZE_NOT_ALLOWED",
            status_code=422,
            detail={"allowed": list(sport.team_size_options)},
        )
