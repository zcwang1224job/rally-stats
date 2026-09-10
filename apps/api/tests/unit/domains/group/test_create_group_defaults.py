"""Unit test: 021-group-creation-defaults's `create_group()` defaults —
blank/omitted 團名 falls back to "{暱稱}的羽球團" (member or guest
creator), an auto default court "球場一" is created in the same
transaction, a failed creation leaves no orphan court, and the existing
`court.added` event is published after commit. Per research.md #1/#2,
spec.md FR-001/FR-006/FR-007."""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.models import Court
from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.service import create_group
from app.domains.member.models import Member
from app.domains.member.security import hash_password

pytestmark = pytest.mark.asyncio


def _payload(**overrides: object) -> CreateGroupRequest:
    data: dict[str, object] = {
        "name": None,
        "max_members": 4,
        "match_mode": "singles",
        "scheduling_mechanism": "fair_rotation",
        "scoring_mode": "21pt",
        "creator_nickname": "阿明",
        "turnstile_token": "tok",
    }
    data.update(overrides)
    return CreateGroupRequest(**data)


async def _make_verified_member(session: AsyncSession, email: str, nickname: str) -> Member:
    member = Member(
        email=email,
        password_hash=hash_password("abc12345"),
        user_number=str(uuid.uuid4())[:8],
        nickname=nickname,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def test_provided_name_used_as_is(db_session: AsyncSession) -> None:
    """(a) research.md #1: a legal, non-blank name is kept verbatim."""
    group, *_ = await create_group(db_session, _payload(name="我的球隊"), member=None)
    assert group.name == "我的球隊"


async def test_blank_name_defaults_for_member_creator(db_session: AsyncSession) -> None:
    """(b) FR-001: blank name + member creator -> "{既有會員暱稱}的羽球團"."""
    member = await _make_verified_member(db_session, "creator1@example.com", "小華")
    group, *_ = await create_group(
        db_session, _payload(name=None, creator_nickname=None), member=member
    )
    assert group.name == "小華的羽球團"


async def test_blank_name_defaults_for_guest_creator(db_session: AsyncSession) -> None:
    """(c) FR-001: blank name + guest creator -> "{本次填寫的暱稱}的羽球團"."""
    group, *_ = await create_group(
        db_session, _payload(name=None, creator_nickname="阿明"), member=None
    )
    assert group.name == "阿明的羽球團"


async def test_whitespace_only_name_also_defaults(db_session: AsyncSession) -> None:
    """spec.md Edge Cases: purely-whitespace name MUST be treated the same
    as omitted (already normalized to None by the schema validator, T001)."""
    group, *_ = await create_group(
        db_session, _payload(name="   ", creator_nickname="小美"), member=None
    )
    assert group.name == "小美的羽球團"


async def test_default_court_created_regardless_of_name(db_session: AsyncSession) -> None:
    """(d) FR-006: exactly one active court named "球場一" is always
    created, whether or not the group name itself was customized."""
    group, *_ = await create_group(db_session, _payload(name="自訂團名"), member=None)

    result = await db_session.execute(select(Court).where(Court.group_id == group.id))
    courts = result.scalars().all()
    assert len(courts) == 1
    assert courts[0].name == "球場一"
    assert courts[0].deleted_at is None


async def test_failed_creation_leaves_no_orphan_court(db_session: AsyncSession) -> None:
    """(e) FR-007: a creation attempt that fails validation (e.g. exceeds
    the configured member cap) MUST NOT leave any Court row behind."""
    with pytest.raises(ApiError) as exc_info:
        await create_group(db_session, _payload(max_members=999999), member=None)
    assert exc_info.value.error_code == "GROUP_MEMBER_CAP_EXCEEDED"

    result = await db_session.execute(select(Court))
    assert result.scalars().all() == []


async def test_court_added_event_published_after_commit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(f) research.md #2: the auto-created court publishes the existing
    `court.added` event (same shape `create_court()` uses), after commit."""
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.domains.group.service.publish", publish_mock)

    group, *_ = await create_group(db_session, _payload(), member=None)

    court_added_calls = [
        call for call in publish_mock.await_args_list if call.args[1] == "court.added"
    ]
    assert len(court_added_calls) == 1
    channel, _event, payload = court_added_calls[0].args
    assert channel == f"group:{group.id}:notifications"
    assert payload["name"] == "球場一"
    assert "court_id" in payload
