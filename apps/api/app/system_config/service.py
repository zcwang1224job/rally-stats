"""Read-only accessors for system_config parameters."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.system_config.models import SystemConfig


async def _get_value(session: AsyncSession, key: str) -> str | None:
    result = await session.execute(select(SystemConfig.value).where(SystemConfig.key == key))
    return result.scalar_one_or_none()


async def get_max_group_members(session: AsyncSession) -> int:
    value = await _get_value(session, "max_group_members")
    return int(value) if value is not None else 200


async def get_verification_token_ttl_hours(session: AsyncSession) -> int:
    value = await _get_value(session, "verification_token_ttl_hours")
    return int(value) if value is not None else 24


async def get_resend_verification_cooldown_minutes(session: AsyncSession) -> int:
    value = await _get_value(session, "resend_verification_cooldown_minutes")
    return int(value) if value is not None else 5


async def get_password_reset_token_ttl_hours(session: AsyncSession) -> int:
    value = await _get_value(session, "password_reset_token_ttl_hours")
    return int(value) if value is not None else 1


async def _get_sport_value(session: AsyncSession, key: str, sport_key: str | None) -> str | None:
    """043 data-model §6: `<key>.<sport_key>` first, then the plain `<key>`
    (which is what every pre-043 badminton group has always read). Custom
    activities share the "other" row."""
    if sport_key is not None:
        lookup = "other" if sport_key == "custom" else sport_key
        value = await _get_value(session, f"{key}.{lookup}")
        if value is not None:
            return value
    return await _get_value(session, key)


async def get_default_group_name_suffix(
    session: AsyncSession, sport_key: str | None = None
) -> str:
    value = await _get_sport_value(session, "default_group_name_suffix", sport_key)
    return value if value is not None else "的羽球團"


async def get_default_court_name(session: AsyncSession, sport_key: str | None = None) -> str:
    value = await _get_sport_value(session, "default_court_name", sport_key)
    return value if value is not None else "球場一"


async def get_default_page_size(session: AsyncSession) -> int:
    value = await _get_value(session, "default_page_size")
    return int(value) if value is not None else 20


async def get_match_records_page_size(session: AsyncSession) -> int:
    """A member's match records (their own 對戰紀錄, a friend's, one of 我的團's
    history) page shorter than other lists: each row is a tall scorecard, so
    twenty of them is a long scroll on a phone."""
    value = await _get_value(session, "match_records_page_size")
    return int(value) if value is not None else 10
