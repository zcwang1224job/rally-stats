"""Regression tests: _raise_if_active_elsewhere() used to have a TOCTOU
(time-of-check-to-time-of-use) race — a plain, unlocked SELECT followed
later by the caller's INSERT+commit meant two near-simultaneous requests
for the same Member (a double-click, two browser tabs) could both read
"not active anywhere" before either committed, and both succeed — putting
the same Member "active" in two groups at once.

Fixed by a `SELECT ... FOR UPDATE` on the Member's own row inside
_raise_if_active_elsewhere(), held for the rest of the caller's
transaction (same pessimistic-lock technique as schedule/service.py's
_lock_group_for_round_generation). These tests use two independent
AsyncSessions (each its own connection, like two real concurrent HTTP
requests would get) and asyncio.gather to actually race them against a
real Postgres instance — a single shared db_session can't reproduce this,
since everything on one session is inherently sequential."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import create_group, join_group
from app.domains.member.models import Member
from app.domains.member.security import hash_password
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Race Test Group",
        "max_members": 8,
        "match_mode": "doubles",
        "scheduling_mechanism": "manual",
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


async def _make_member(session: AsyncSession, email: str, nickname: str) -> Member:
    member = Member(
        email=email,
        password_hash=hash_password("abc12345"),
        user_number=email[:8].upper().ljust(8, "A"),
        nickname=nickname,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


def _create_payload(**overrides: object) -> CreateGroupRequest:
    defaults: dict[str, object] = {
        "name": "Race Second Group",
        "max_members": 4,
        "match_mode": "doubles",
        "scheduling_mechanism": "manual",
        "turnstile_token": "unused",
    }
    defaults.update(overrides)
    return CreateGroupRequest(**defaults)  # type: ignore[arg-type]


def _second_session() -> AsyncSession:
    """A fully independent engine/connection — asyncio.gather'ing two
    coroutines that share one AsyncSession would just serialize through
    that one connection anyway, masking the race this is meant to
    reproduce."""
    engine = create_async_engine(TEST_DATABASE_URL)
    return async_sessionmaker(engine, expire_on_commit=False)()


def _outcome(results: list[object]) -> tuple[list[object], list[ApiError]]:
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, ApiError)]
    assert len(successes) + len(failures) == len(results), results
    return successes, failures


async def test_concurrent_create_group_for_same_member_only_one_succeeds(
    db_session: AsyncSession,
) -> None:
    member = await _make_member(db_session, "race-create-create@example.com", "小明")

    async with _second_session() as session_b:
        # Warms up session_b's connection (TCP + auth handshake) before the
        # race starts — otherwise that one-time setup cost dwarfs
        # create_group()'s own runtime and db_session (already warm, reused
        # from the fixture) reliably finishes and commits before session_b
        # even issues its first query, masking the race entirely.
        await session_b.execute(select(1))
        results = await asyncio.gather(
            create_group(db_session, _create_payload(name="Race A"), member=member),
            create_group(session_b, _create_payload(name="Race B"), member=member),
            return_exceptions=True,
        )
    successes, failures = _outcome(results)

    assert len(successes) == 1, results
    assert len(failures) == 1, results
    assert failures[0].error_code == "ALREADY_ACTIVE_IN_ANOTHER_GROUP"


async def test_concurrent_join_group_for_same_member_only_one_succeeds(
    db_session: AsyncSession,
) -> None:
    member = await _make_member(db_session, "race-join-join@example.com", "小華")
    group_a = await _make_group(db_session, name="Race Join A")

    async with _second_session() as session_b:
        group_b = await _make_group(session_b, name="Race Join B")
        results = await asyncio.gather(
            join_group(db_session, group_a, member=member, password=None, nickname=None),
            join_group(session_b, group_b, member=member, password=None, nickname=None),
            return_exceptions=True,
        )
    successes, failures = _outcome(results)

    assert len(successes) == 1, results
    assert len(failures) == 1, results
    assert failures[0].error_code == "ALREADY_ACTIVE_IN_ANOTHER_GROUP"
