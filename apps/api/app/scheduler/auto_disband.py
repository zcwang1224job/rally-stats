"""1-hour idle auto-disband: periodic sweep reusing disband_group (spec FR-036,
research.md #4). In-process APScheduler is sufficient at this project's scale —
see research.md #4 for the accepted limitation if the backend ever scales to
multiple Task instances."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.domains.group.models import Group
from app.domains.group.service import disband_group
from app.domains.group_invite.service import invalidate_pending_invites_for_group

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


async def sweep_idle_groups(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Accepts an injectable session factory (defaulting to the app's own,
    resolved lazily) so tests can pass a factory bound to their own event
    loop/engine instead of the process-wide singleton in app.core.db —
    asyncpg connections are event-loop-bound, and pytest-asyncio gives each
    test function its own loop."""
    if session_factory is None:
        from app.core.db import async_session_factory

        session_factory = async_session_factory

    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.auto_disband_idle_minutes)

    async with session_factory() as session:
        result = await session.execute(
            select(Group).where(Group.status == "active", Group.last_activity_at < cutoff)
        )
        idle_groups = result.scalars().all()
        for group in idle_groups:
            logger.info("auto-disbanding idle group %s", group.id)
            await disband_group(
                session, group, invalidate_pending_invites=invalidate_pending_invites_for_group
            )


def start_scheduler() -> None:
    if not _scheduler.running:
        _scheduler.add_job(sweep_idle_groups, "interval", minutes=1, id="auto_disband_sweep")
        _scheduler.start()


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
