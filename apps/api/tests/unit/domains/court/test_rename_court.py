"""Unit test: 021-group-creation-defaults exposes the existing
`rename_court()` (002-court-management) via UI for the first time — it had
zero test coverage until now (research.md #3). Covers spec.md FR-009/
FR-011: successful rename, name-collision rejection, renaming a deleted
court, and renaming a court to its own current name (MUST succeed, not be
treated as a collision)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.schemas import CreateCourtRequest, RenameCourtRequest
from app.domains.court.service import create_court, delete_court, rename_court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Rename Court Test Group",
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
async def test_rename_succeeds_and_keeps_tokens(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="球場一"))
    original_scoreboard_token = court.scoreboard_token
    original_control_panel_token = court.control_panel_token

    updated = await rename_court(db_session, court, RenameCourtRequest(name="羽球場A"))

    assert updated.name == "羽球場A"
    assert updated.scoreboard_token == original_scoreboard_token
    assert updated.control_panel_token == original_control_panel_token


@pytest.mark.asyncio
async def test_rename_to_name_used_by_another_active_court_rejected(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await create_court(db_session, group, CreateCourtRequest(name="場地A"))
    court_b = await create_court(db_session, group, CreateCourtRequest(name="場地B"))

    with pytest.raises(ApiError) as exc_info:
        await rename_court(db_session, court_b, RenameCourtRequest(name="場地A"))
    assert exc_info.value.error_code == "COURT_NAME_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_rename_deleted_court_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="球場一"))
    await delete_court(db_session, court)

    with pytest.raises(ApiError) as exc_info:
        await rename_court(db_session, court, RenameCourtRequest(name="新名字"))
    assert exc_info.value.error_code == "COURT_DELETED"


@pytest.mark.asyncio
async def test_rename_to_own_current_name_succeeds(db_session: AsyncSession) -> None:
    """spec.md Edge Cases: renaming a court to the name it already has is a
    no-op-but-legal update, MUST NOT be misjudged as a duplicate."""
    group = await _make_group(db_session)
    court = await create_court(db_session, group, CreateCourtRequest(name="球場一"))

    updated = await rename_court(db_session, court, RenameCourtRequest(name="球場一"))

    assert updated.name == "球場一"
