"""Unit tests for 028-guest-stats-binding's shared primitives
(`resolve_guest_binding_target()`/`bind_roster_entry_to_member()`, both in
`app.domains.group.service`) and the orchestration built on top of them
(`complete_guest_bind()`, in `app.domains.member.service` — research.md #2,
kept out of `group/service.py` to avoid a circular import back into
`member/service.py`).

`resolve_guest_session()` (015, active-only) is deliberately untouched by
this feature (research.md #1) — one regression test below confirms it."""

import asyncio
import secrets

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import (
    bind_roster_entry_to_member,
    join_group,
    resolve_guest_binding_target,
    resolve_guest_session,
)
from app.domains.member.models import Member
from app.domains.member.security import hash_password
from app.domains.member.service import complete_guest_bind
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, *, status: str = "active") -> Group:
    group = Group(
        name="Guest Binding Test",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status=status,
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_member(session: AsyncSession, email: str, password: str = "abc12345") -> Member:
    member = Member(
        email=email,
        password_hash=hash_password(password),
        user_number=secrets.token_hex(4),
        verification_status="verified",
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def _fake_verify_turnstile(*_args: object, **_kwargs: object) -> None:
    return None


# --- T004: resolve_guest_binding_target() -------------------------------


async def test_binding_target_active_roster_active_group(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    resolved = await resolve_guest_binding_target(db_session, roster_entry.guest_session_token)
    assert resolved.id == roster_entry.id


@pytest.mark.parametrize("roster_status", ["left", "kicked"])
async def test_binding_target_non_active_roster_active_group(
    db_session: AsyncSession, roster_status: str
) -> None:
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    roster_entry.status = roster_status
    await db_session.commit()

    resolved = await resolve_guest_binding_target(db_session, roster_entry.guest_session_token)
    assert resolved.id == roster_entry.id


async def test_binding_target_active_roster_disbanded_group(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    group.status = "disbanded"
    await db_session.commit()

    resolved = await resolve_guest_binding_target(db_session, roster_entry.guest_session_token)
    assert resolved.id == roster_entry.id


async def test_binding_target_left_roster_disbanded_group(db_session: AsyncSession) -> None:
    """FR-004/Acceptance Scenario 4/5: both axes non-active at once."""
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    roster_entry.status = "kicked"
    group.status = "disbanded"
    await db_session.commit()

    resolved = await resolve_guest_binding_target(db_session, roster_entry.guest_session_token)
    assert resolved.id == roster_entry.id


async def test_binding_target_unknown_token_raises(db_session: AsyncSession) -> None:
    with pytest.raises(ApiError) as exc_info:
        await resolve_guest_binding_target(db_session, "not-a-real-token")
    assert exc_info.value.error_code == "LINK_NOT_FOUND"


async def test_resolve_guest_session_still_active_only_regression(
    db_session: AsyncSession,
) -> None:
    """research.md #1: resolve_guest_binding_target() is additive, not a
    replacement — resolve_guest_session() MUST still reject exactly as
    before."""
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    roster_entry.status = "left"
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await resolve_guest_session(db_session, roster_entry.guest_session_token)
    assert exc_info.value.error_code == "LINK_NOT_FOUND"


# --- T005: bind_roster_entry_to_member() ---------------------------------


async def test_bind_roster_entry_to_member_success(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    member = await _make_member(db_session, "bind-target@example.com")

    await bind_roster_entry_to_member(db_session, roster_entry.id, member.id)

    await db_session.refresh(roster_entry)
    assert roster_entry.member_id == member.id
    # FR-011 / /speckit-analyze 2026-09-15 remediation finding E1: binding
    # MUST NOT touch the roster entry's existing nickname.
    assert roster_entry.nickname == "小美"


async def test_bind_roster_entry_to_member_already_bound_raises(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    member_a = await _make_member(db_session, "a@example.com")
    member_b = await _make_member(db_session, "b@example.com")

    await bind_roster_entry_to_member(db_session, roster_entry.id, member_a.id)

    with pytest.raises(ApiError) as exc_info:
        await bind_roster_entry_to_member(db_session, roster_entry.id, member_b.id)
    assert exc_info.value.error_code == "ROSTER_ENTRY_ALREADY_BOUND"

    await db_session.refresh(roster_entry)
    assert roster_entry.member_id == member_a.id
    assert roster_entry.nickname == "小美"


def _second_session() -> AsyncSession:
    """A fully independent engine/connection, same technique as
    test_one_active_group_race.py — asyncio.gather'ing two coroutines that
    share one AsyncSession would just serialize through that one
    connection anyway, masking the race this is meant to reproduce."""
    engine = create_async_engine(TEST_DATABASE_URL)
    return async_sessionmaker(engine, expire_on_commit=False)()


async def test_bind_roster_entry_to_member_concurrent_only_one_succeeds(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    member_a = await _make_member(db_session, "race-a@example.com")
    member_b = await _make_member(db_session, "race-b@example.com")

    async with _second_session() as session_b:
        await session_b.execute(select(1))
        results = await asyncio.gather(
            bind_roster_entry_to_member(db_session, roster_entry.id, member_a.id),
            bind_roster_entry_to_member(session_b, roster_entry.id, member_b.id),
            return_exceptions=True,
        )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, ApiError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].error_code == "ROSTER_ENTRY_ALREADY_BOUND"

    await db_session.refresh(roster_entry)
    assert roster_entry.member_id in (member_a.id, member_b.id)


# --- T010/T011: complete_guest_bind() success paths ----------------------


async def test_complete_guest_bind_mode_register_success(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.domains.member.service.verify_turnstile_token", _fake_verify_turnstile
    )
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )

    result = await complete_guest_bind(
        db_session,
        roster_entry.guest_session_token,
        current_member=None,
        mode="register",
        email="new-guest@example.com",
        password="abc12345",
        turnstile_token="unused",
    )

    assert result.group_id == group.id
    assert result.access_token is not None
    assert result.refresh_token is not None

    await db_session.refresh(roster_entry)
    new_member = (
        await db_session.execute(select(Member).where(Member.email == "new-guest@example.com"))
    ).scalar_one()
    assert roster_entry.member_id == new_member.id


async def test_complete_guest_bind_already_logged_in_ignores_body(
    db_session: AsyncSession,
) -> None:
    """Clarifications 2026-09-15 / FR-012."""
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    current_member = await _make_member(db_session, "already-logged-in@example.com")

    result = await complete_guest_bind(
        db_session,
        roster_entry.guest_session_token,
        current_member=current_member,
        mode="register",
        email="ignored@example.com",
        password="ignored-too",
        turnstile_token=None,
    )

    assert result.access_token is None
    assert result.refresh_token is None
    await db_session.refresh(roster_entry)
    assert roster_entry.member_id == current_member.id

    ignored = (
        await db_session.execute(select(Member).where(Member.email == "ignored@example.com"))
    ).scalar_one_or_none()
    assert ignored is None


# --- T012: mode="register" edge cases -------------------------------------


async def test_complete_guest_bind_register_turnstile_failure(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fail_verify(*_args: object, **_kwargs: object) -> None:
        raise ApiError("CAPTCHA_INVALID", status_code=400)

    monkeypatch.setattr("app.domains.member.service.verify_turnstile_token", _fail_verify)
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )

    with pytest.raises(ApiError) as exc_info:
        await complete_guest_bind(
            db_session,
            roster_entry.guest_session_token,
            current_member=None,
            mode="register",
            email="turnstile-fail@example.com",
            password="abc12345",
            turnstile_token="bad-token",
        )
    assert exc_info.value.error_code == "CAPTCHA_INVALID"
    await db_session.refresh(roster_entry)
    assert roster_entry.member_id is None


async def test_complete_guest_bind_register_email_already_registered(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.domains.member.service.verify_turnstile_token", _fake_verify_turnstile
    )
    await _make_member(db_session, "taken@example.com")
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )

    with pytest.raises(ApiError) as exc_info:
        await complete_guest_bind(
            db_session,
            roster_entry.guest_session_token,
            current_member=None,
            mode="register",
            email="taken@example.com",
            password="abc12345",
            turnstile_token="unused",
        )
    assert exc_info.value.error_code == "EMAIL_ALREADY_REGISTERED"
    await db_session.refresh(roster_entry)
    assert roster_entry.member_id is None


async def test_complete_guest_bind_roster_already_bound(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.domains.member.service.verify_turnstile_token", _fake_verify_turnstile
    )
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    already_bound_to = await _make_member(db_session, "first@example.com")
    await bind_roster_entry_to_member(db_session, roster_entry.id, already_bound_to.id)

    with pytest.raises(ApiError) as exc_info:
        await complete_guest_bind(
            db_session,
            roster_entry.guest_session_token,
            current_member=None,
            mode="register",
            email="second@example.com",
            password="abc12345",
            turnstile_token="unused",
        )
    assert exc_info.value.error_code == "ROSTER_ENTRY_ALREADY_BOUND"


# --- T013: disbanded/left/kicked all still bindable -----------------------


async def test_complete_guest_bind_disbanded_group(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.domains.member.service.verify_turnstile_token", _fake_verify_turnstile
    )
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    group.status = "disbanded"
    await db_session.commit()

    result = await complete_guest_bind(
        db_session,
        roster_entry.guest_session_token,
        current_member=None,
        mode="register",
        email="disbanded-guest@example.com",
        password="abc12345",
        turnstile_token="unused",
    )
    assert result.group_id == group.id


@pytest.mark.parametrize("roster_status", ["left", "kicked"])
async def test_complete_guest_bind_left_or_kicked_roster(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, roster_status: str
) -> None:
    monkeypatch.setattr(
        "app.domains.member.service.verify_turnstile_token", _fake_verify_turnstile
    )
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )
    roster_entry.status = roster_status
    await db_session.commit()

    result = await complete_guest_bind(
        db_session,
        roster_entry.guest_session_token,
        current_member=None,
        mode="register",
        email=f"{roster_status}-guest@example.com",
        password="abc12345",
        turnstile_token="unused",
    )
    assert result.group_id == group.id


# --- T029: mode="login" ----------------------------------------------------


async def test_complete_guest_bind_mode_login_success(db_session: AsyncSession) -> None:
    existing = await _make_member(db_session, "existing-account@example.com", "s3cret123")
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )

    result = await complete_guest_bind(
        db_session,
        roster_entry.guest_session_token,
        current_member=None,
        mode="login",
        email="existing-account@example.com",
        password="s3cret123",
        turnstile_token=None,
    )

    assert result.access_token is not None
    await db_session.refresh(roster_entry)
    assert roster_entry.member_id == existing.id

    # SC-004: no duplicate account created.
    members = (
        await db_session.execute(
            select(Member).where(Member.email == "existing-account@example.com")
        )
    ).scalars().all()
    assert len(members) == 1


async def test_complete_guest_bind_mode_login_invalid_credentials(
    db_session: AsyncSession,
) -> None:
    await _make_member(db_session, "wrong-password@example.com", "correct-password")
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )

    with pytest.raises(ApiError) as exc_info:
        await complete_guest_bind(
            db_session,
            roster_entry.guest_session_token,
            current_member=None,
            mode="login",
            email="wrong-password@example.com",
            password="not-the-password",
            turnstile_token=None,
        )
    assert exc_info.value.error_code == "INVALID_CREDENTIALS"
    await db_session.refresh(roster_entry)
    assert roster_entry.member_id is None


# --- T030: mode="register" email collision guides to login (FR-009) -------


async def test_complete_guest_bind_register_collision_does_not_bind(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.domains.member.service.verify_turnstile_token", _fake_verify_turnstile
    )
    existing = await _make_member(db_session, "collides@example.com")
    group = await _make_group(db_session)
    roster_entry, _ = await join_group(
        db_session, group, member=None, password=None, nickname="小美"
    )

    with pytest.raises(ApiError) as exc_info:
        await complete_guest_bind(
            db_session,
            roster_entry.guest_session_token,
            current_member=None,
            mode="register",
            email="collides@example.com",
            password="abc12345",
            turnstile_token="unused",
        )
    assert exc_info.value.error_code == "EMAIL_ALREADY_REGISTERED"

    await db_session.refresh(roster_entry)
    assert roster_entry.member_id is None
    assert roster_entry.member_id != existing.id
