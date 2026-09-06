"""Unit test: FR-020 match-mode-vs-member-cap connected validation, and
FR-014 custom scoring validation on edit."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.schemas import EditGroupRequest, EditScoringSettingsRequest
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import edit_group, edit_scoring_settings

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = dict(
        name="Edit Test",
        max_members=2,
        match_mode="singles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    defaults.update(overrides)
    group = Group(**defaults)  # type: ignore[arg-type]
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def test_switching_to_doubles_with_low_cap_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, max_members=2, match_mode="singles")
    payload = EditGroupRequest(expected_version=0, match_mode="doubles")
    with pytest.raises(ApiError) as exc_info:
        await edit_group(db_session, group, payload)
    assert exc_info.value.error_code == "MATCH_MODE_MEMBER_CAP_CONFLICT"


async def test_switching_to_doubles_with_raised_cap_in_same_request_succeeds(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, max_members=2, match_mode="singles")
    payload = EditGroupRequest(expected_version=0, match_mode="doubles", max_members=4)
    updated = await edit_group(db_session, group, payload)
    assert updated.match_mode == "doubles"
    assert updated.max_members == 4


async def test_custom_scoring_cap_below_target_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    payload = EditScoringSettingsRequest(
        expected_version=0, scoring_mode="custom", target_score=10, deuce_threshold=5, cap_score=8
    )
    with pytest.raises(ApiError) as exc_info:
        await edit_scoring_settings(db_session, group, payload)
    assert exc_info.value.error_code == "INVALID_CUSTOM_SCORING"
