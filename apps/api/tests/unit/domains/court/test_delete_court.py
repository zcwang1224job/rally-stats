"""Unit test: soft-delete excludes from active queries; deleted names reusable
(spec FR-008/FR-009, US2)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.schemas import CreateCourtRequest
from app.domains.court.service import create_court, delete_court, list_active_courts
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Delete Court Test Group",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


@pytest.mark.asyncio
async def test_delete_excludes_court_from_active_list(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="1號場"))

    await delete_court(db_session, court)

    active = await list_active_courts(db_session, group.id)
    assert active == []
    assert court.deleted_at is not None


@pytest.mark.asyncio
async def test_deleting_already_deleted_court_raises(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="1號場"))
    await delete_court(db_session, court)

    with pytest.raises(ApiError) as exc_info:
        await delete_court(db_session, court)
    assert exc_info.value.error_code == "COURT_DELETED"


@pytest.mark.asyncio
async def test_delete_invokes_abandon_matches_hook(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="1號場"))
    calls: list[str] = []

    async def hook(_session: AsyncSession, court_id: object) -> bool:
        calls.append(str(court_id))
        return True

    had_active_match = await delete_court(db_session, court, abandon_unfinished_matches=hook)
    assert calls == [str(court.id)]
    assert had_active_match is True


@pytest.mark.asyncio
async def test_default_hook_reports_no_active_match(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="1號場"))

    had_active_match = await delete_court(db_session, court)
    assert had_active_match is False
