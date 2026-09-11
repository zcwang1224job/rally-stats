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


async def get_default_group_name_suffix(session: AsyncSession) -> str:
    value = await _get_value(session, "default_group_name_suffix")
    return value if value is not None else "的羽球團"


async def get_default_court_name(session: AsyncSession) -> str:
    value = await _get_value(session, "default_court_name")
    return value if value is not None else "球場一"


async def get_default_page_size(session: AsyncSession) -> int:
    value = await _get_value(session, "default_page_size")
    return int(value) if value is not None else 20
