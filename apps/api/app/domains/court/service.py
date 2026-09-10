"""Court domain business logic — create/list/rename/delete + link regeneration,
per specs/002-court-management/contracts/courts-api.md."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.realtime import court_channel, group_notifications_channel, publish
from app.domains.court.models import Court
from app.domains.court.schemas import CreateCourtRequest, RenameCourtRequest
from app.domains.group.models import Group

AbandonCourtMatchesHook = Callable[[AsyncSession, uuid.UUID], Awaitable[bool]]


async def _default_abandon_hook(_session: AsyncSession, _court_id: uuid.UUID) -> bool:
    """No-op until 003 spec's Match domain module exists (research.md #2)."""
    return False


async def create_court(session: AsyncSession, group: Group, payload: CreateCourtRequest) -> Court:
    if group.status == "disbanded":
        raise ApiError("GROUP_DISBANDED", status_code=409)

    court = Court(group_id=group.id, name=payload.name)
    session.add(court)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError("COURT_NAME_ALREADY_EXISTS", status_code=409) from exc
    await session.refresh(court)

    # All-courts control panel screens sync their court list live (FR-015)
    # via the same team-level notifications channel the all-courts token
    # already subscribes to (architecture.md §3.2 Token capability table).
    await publish(
        group_notifications_channel(str(group.id)),
        "court.added",
        {"court_id": str(court.id), "name": court.name},
    )
    return court


async def list_active_courts(session: AsyncSession, group_id: uuid.UUID) -> list[Court]:
    result = await session.execute(
        select(Court)
        .where(Court.group_id == group_id, Court.deleted_at.is_(None))
        .order_by(Court.created_at)
    )
    return list(result.scalars().all())


async def get_court_by_id(session: AsyncSession, court_id: uuid.UUID) -> Court:
    result = await session.execute(select(Court).where(Court.id == court_id))
    court = result.scalar_one_or_none()
    if court is None:
        raise ApiError("COURT_NOT_FOUND", status_code=404)
    return court


async def rename_court(session: AsyncSession, court: Court, payload: RenameCourtRequest) -> Court:
    """Rename a court, keeping its scoreboard/control-panel tokens unchanged.
    Previously exposed only via `PATCH /courts/{court_id}` with no caller and
    no test coverage; 021-group-creation-defaults added the 球場管理 UI entry
    point (T014/T015) and the first tests for this path (T011/T012,
    research.md #3)."""
    if court.deleted_at is not None:
        raise ApiError("COURT_DELETED", status_code=409)
    court.name = payload.name
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError("COURT_NAME_ALREADY_EXISTS", status_code=409) from exc
    await session.refresh(court)
    return court


async def delete_court(
    session: AsyncSession,
    court: Court,
    *,
    abandon_unfinished_matches: AbandonCourtMatchesHook | None = None,
) -> bool:
    """Soft-delete. Not idempotent (unlike 001's disband_group) — re-deleting an
    already-deleted court raises COURT_DELETED, per contracts/courts-api.md."""
    if court.deleted_at is not None:
        raise ApiError("COURT_DELETED", status_code=409)

    hook = abandon_unfinished_matches or _default_abandon_hook
    had_active_match = await hook(session, court.id)

    court.deleted_at = datetime.now(UTC)
    await session.commit()

    await publish(
        group_notifications_channel(str(court.group_id)),
        "court.deleted",
        {"court_id": str(court.id)},
    )
    return had_active_match


async def regenerate_scoreboard_link(
    session: AsyncSession, group_id: uuid.UUID, court: Court, expected_version: int
) -> Court:
    if court.deleted_at is not None:
        raise ApiError("COURT_DELETED", status_code=409)
    if expected_version != court.scoreboard_link_version:
        raise ApiError("VERSION_CONFLICT", status_code=409)

    court.scoreboard_token = uuid.uuid4()
    court.scoreboard_link_version += 1
    await session.commit()
    await session.refresh(court)

    await publish(
        court_channel(str(group_id), str(court.id)),
        "link.regenerated",
        {"court_id": str(court.id), "link_type": "scoreboard"},
    )
    return court


async def regenerate_control_panel_link(
    session: AsyncSession, group_id: uuid.UUID, court: Court, expected_version: int
) -> Court:
    if court.deleted_at is not None:
        raise ApiError("COURT_DELETED", status_code=409)
    if expected_version != court.control_panel_link_version:
        raise ApiError("VERSION_CONFLICT", status_code=409)

    court.control_panel_token = uuid.uuid4()
    court.control_panel_link_version += 1
    await session.commit()
    await session.refresh(court)

    await publish(
        court_channel(str(group_id), str(court.id)),
        "link.regenerated",
        {"court_id": str(court.id), "link_type": "control_panel"},
    )
    return court


async def get_court_by_token(
    session: AsyncSession, token: uuid.UUID
) -> tuple[Court, Group, Literal["scoreboard", "control_panel"]]:
    """Resolves a scoreboard OR control_panel token to its court + owning group."""
    result = await session.execute(select(Court).where(Court.scoreboard_token == token))
    court = result.scalar_one_or_none()
    link_type: Literal["scoreboard", "control_panel"] = "scoreboard"
    if court is None:
        result = await session.execute(select(Court).where(Court.control_panel_token == token))
        court = result.scalar_one_or_none()
        link_type = "control_panel"
    if court is None:
        raise ApiError("LINK_NOT_FOUND", status_code=404)

    group_result = await session.execute(select(Group).where(Group.id == court.group_id))
    group = group_result.scalar_one_or_none()
    if group is None:
        raise ApiError("LINK_NOT_FOUND", status_code=404)

    return court, group, link_type
