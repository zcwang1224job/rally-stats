"""Read-only accessors for system_config parameters."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.system_config.models import SystemConfig


async def get_max_group_members(session: AsyncSession) -> int:
    result = await session.execute(
        select(SystemConfig.value).where(SystemConfig.key == "max_group_members")
    )
    value = result.scalar_one_or_none()
    return int(value) if value is not None else 200
