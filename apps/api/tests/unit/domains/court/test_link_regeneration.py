"""Unit test: link regeneration guard ordering (FR-028) and independent
version fields (FR-036)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.schemas import CreateCourtRequest
from app.domains.court.service import (
    create_court,
    delete_court,
    get_court_by_id,
    regenerate_control_panel_link,
    regenerate_scoreboard_link,
)
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Link Regen Test",
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
async def test_deleted_court_check_takes_priority_over_version_conflict(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="1號場"))
    court = await get_court_by_id(db_session, court.id)
    await delete_court(db_session, court)

    # Even with the CORRECT expected_version, a deleted court must be
    # rejected as COURT_DELETED, not silently accepted or VERSION_CONFLICT.
    with pytest.raises(ApiError) as exc_info:
        await regenerate_scoreboard_link(db_session, group.id, court, 0)
    assert exc_info.value.error_code == "COURT_DELETED"


@pytest.mark.asyncio
async def test_stale_version_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="1號場"))

    with pytest.raises(ApiError) as exc_info:
        await regenerate_scoreboard_link(db_session, group.id, court, 5)
    assert exc_info.value.error_code == "VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_scoreboard_and_control_panel_versions_are_independent(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="1號場"))

    # Regenerating the scoreboard link must not bump (or be blocked by) the
    # control_panel_link_version, and vice versa.
    updated = await regenerate_scoreboard_link(db_session, group.id, court, 0)
    assert updated.scoreboard_link_version == 1
    assert updated.control_panel_link_version == 0

    updated = await regenerate_control_panel_link(db_session, group.id, updated, 0)
    assert updated.control_panel_link_version == 1
    assert updated.scoreboard_link_version == 1
