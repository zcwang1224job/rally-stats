"""Unit test: by-all-courts-token resolution excludes deleted courts and
reports group-disbanded status (spec US3, contracts/courts-api.md)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.schemas import CreateCourtRequest
from app.domains.court.service import create_court, delete_court, get_court_by_id
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import disband_group, get_group_by_all_courts_token


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="All Courts Link Test",
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
async def test_resolves_group_and_active_courts_only(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    kept = await create_court(db_session, group, CreateCourtRequest(name="1號場"))
    removed = await create_court(db_session, group, CreateCourtRequest(name="2號場"))
    removed_court = await get_court_by_id(db_session, removed.id)
    await delete_court(db_session, removed_court)

    resolved_group, courts = await get_group_by_all_courts_token(
        db_session, group.all_courts_control_panel_token
    )
    assert resolved_group.id == group.id
    assert [c.id for c in courts] == [kept.id]


@pytest.mark.asyncio
async def test_reports_group_disbanded(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await disband_group(db_session, group)

    resolved_group, _courts = await get_group_by_all_courts_token(
        db_session, group.all_courts_control_panel_token
    )
    assert resolved_group.status == "disbanded"


@pytest.mark.asyncio
async def test_unknown_token_raises_link_not_found(db_session: AsyncSession) -> None:
    import uuid

    with pytest.raises(ApiError) as exc_info:
        await get_group_by_all_courts_token(db_session, uuid.uuid4())
    assert exc_info.value.error_code == "LINK_NOT_FOUND"
