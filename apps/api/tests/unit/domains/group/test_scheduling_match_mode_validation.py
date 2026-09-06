"""Unit test: FR-042 blocks singles + fixed_partner/individual_mixed combo,
on both the create and edit paths (spec 003, per 001's edit_group)."""

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.schemas import CreateGroupRequest, EditGroupRequest
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import edit_group


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "FR-042 Test",
        "max_members": 4,
        "match_mode": "doubles",
        "scheduling_mechanism": "fixed_partner",
        "current_member_count": 1,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
    }
    defaults.update(overrides)
    group = Group(**defaults)  # type: ignore[arg-type]
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


@pytest.mark.parametrize("scheduling_mechanism", ["fixed_partner", "individual_mixed"])
def test_create_group_rejects_singles_with_partner_mechanism(scheduling_mechanism: str) -> None:
    with pytest.raises(ValidationError):
        CreateGroupRequest(
            name="Test",
            max_members=2,
            match_mode="singles",
            scheduling_mechanism=scheduling_mechanism,
            creator_nickname="小明",
            turnstile_token="x",
        )


def test_create_group_accepts_doubles_with_partner_mechanism() -> None:
    request = CreateGroupRequest(
        name="Test",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="fixed_partner",
        creator_nickname="小明",
        turnstile_token="x",
    )
    assert request.match_mode == "doubles"


@pytest.mark.asyncio
async def test_edit_group_rejects_switching_match_mode_to_singles(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="fixed_partner")

    with pytest.raises(ApiError) as exc_info:
        await edit_group(
            db_session,
            group,
            EditGroupRequest(expected_version=0, match_mode="singles", max_members=2),
        )
    assert exc_info.value.error_code == "SCHEDULING_MECHANISM_MATCH_MODE_CONFLICT"


@pytest.mark.asyncio
async def test_edit_group_rejects_switching_mechanism_with_singles_mode(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(
        db_session, match_mode="singles", scheduling_mechanism="fair_rotation", max_members=2
    )

    with pytest.raises(ApiError) as exc_info:
        await edit_group(
            db_session,
            group,
            EditGroupRequest(expected_version=0, scheduling_mechanism="individual_mixed"),
        )
    assert exc_info.value.error_code == "SCHEDULING_MECHANISM_MATCH_MODE_CONFLICT"


@pytest.mark.asyncio
async def test_edit_group_allows_consistent_combo(db_session: AsyncSession) -> None:
    group = await _make_group(
        db_session, match_mode="singles", scheduling_mechanism="fair_rotation", max_members=2
    )

    updated = await edit_group(
        db_session, group, EditGroupRequest(expected_version=0, name="Renamed")
    )
    assert updated.name == "Renamed"
