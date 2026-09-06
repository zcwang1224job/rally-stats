"""Unit test: court name validation + active-scope uniqueness (spec FR-002/FR-003)."""

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.schemas import CreateCourtRequest
from app.domains.court.service import create_court, delete_court, get_court_by_id
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Court Test Group",
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


def test_blank_name_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateCourtRequest(name="   ")


def test_name_over_20_chars_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateCourtRequest(name="x" * 21)


def test_name_trimmed() -> None:
    request = CreateCourtRequest(name="  1號場  ")
    assert request.name == "1號場"


@pytest.mark.asyncio
async def test_duplicate_active_name_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await create_court(db_session, group, CreateCourtRequest(name="1號場"))

    with pytest.raises(ApiError) as exc_info:
        await create_court(db_session, group, CreateCourtRequest(name="1號場"))
    assert exc_info.value.error_code == "COURT_NAME_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_deleted_court_name_reusable(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    first = await create_court(db_session, group, CreateCourtRequest(name="1號場"))
    court = await get_court_by_id(db_session, first.id)
    await delete_court(db_session, court)

    # Same name, now that the original is soft-deleted, must be accepted.
    second = await create_court(db_session, group, CreateCourtRequest(name="1號場"))
    assert second.id != first.id
