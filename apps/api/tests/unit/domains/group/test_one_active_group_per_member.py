"""Unit test: a Member can only be an active RosterEntry in one Group at a
time (new requirement — no spec FR number yet). Deliberately Member-only:
a Guest's RosterEntry has no cross-group identity to check against
(guest_session_token is scoped to a single group by design, FR-022), so
this can't be — and isn't meant to be — enforced for Guests.

Full matrix, both roles: {created a group, joined a group} x {try to join
someone else's group, try to create another group}. Both create_group()
and join_group() are covered as the FIRST action too, since creating a
group makes the creator its first (active) RosterEntry — from this rule's
perspective that's just another way of becoming active in a group, and
the two aren't guaranteed identical without a test for each (create_group()
and join_group() are separate functions that each call
_raise_if_active_elsewhere() independently)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import create_group, disband_group, join_group
from app.domains.member.models import Member
from app.domains.member.security import hash_password

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "One Active Group Test",
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
        "name": "Second Group",
        "max_members": 4,
        "match_mode": "doubles",
        "scheduling_mechanism": "manual",
        "turnstile_token": "unused",
    }
    defaults.update(overrides)
    return CreateGroupRequest(**defaults)  # type: ignore[arg-type]


# --- Member: blocked in all four combinations ---------------------------


async def test_member_joined_a_group_cannot_join_someone_elses_group(
    db_session: AsyncSession,
) -> None:
    group_a = await _make_group(db_session, name="Group A")
    group_b = await _make_group(db_session, name="Group B")
    member = await _make_member(db_session, "joined-then-join@example.com", "小明")

    await join_group(db_session, group_a, member=member, password=None, nickname=None)

    with pytest.raises(ApiError) as exc_info:
        await join_group(db_session, group_b, member=member, password=None, nickname=None)
    assert exc_info.value.error_code == "ALREADY_ACTIVE_IN_ANOTHER_GROUP"


async def test_member_joined_a_group_cannot_create_another_group(
    db_session: AsyncSession,
) -> None:
    group_a = await _make_group(db_session, name="Group A")
    member = await _make_member(db_session, "joined-then-create@example.com", "小明")

    await join_group(db_session, group_a, member=member, password=None, nickname=None)

    with pytest.raises(ApiError) as exc_info:
        await create_group(db_session, _create_payload(), member=member)
    assert exc_info.value.error_code == "ALREADY_ACTIVE_IN_ANOTHER_GROUP"


async def test_member_created_a_group_cannot_join_someone_elses_group(
    db_session: AsyncSession,
) -> None:
    """The other half of the matrix from the two tests above: CREATING is
    the first action here, not joining — create_group() and join_group()
    each call _raise_if_active_elsewhere() independently, so a Member
    becoming active via create_group() must block a subsequent join_group()
    just as reliably as the reverse."""
    group_b = await _make_group(db_session, name="Group B (someone else's)")
    member = await _make_member(db_session, "created-then-join@example.com", "小明")

    await create_group(db_session, _create_payload(name="Group A"), member=member)

    with pytest.raises(ApiError) as exc_info:
        await join_group(db_session, group_b, member=member, password=None, nickname=None)
    assert exc_info.value.error_code == "ALREADY_ACTIVE_IN_ANOTHER_GROUP"


async def test_member_created_a_group_cannot_create_another_group(
    db_session: AsyncSession,
) -> None:
    member = await _make_member(db_session, "created-then-create@example.com", "小明")

    await create_group(db_session, _create_payload(name="Group A"), member=member)

    with pytest.raises(ApiError) as exc_info:
        await create_group(db_session, _create_payload(name="Group B"), member=member)
    assert exc_info.value.error_code == "ALREADY_ACTIVE_IN_ANOTHER_GROUP"


# --- Member: no longer blocked once the first group is left/disbanded ---


async def test_member_who_left_the_first_group_can_join_a_second(
    db_session: AsyncSession,
) -> None:
    group_a = await _make_group(db_session, name="Group A")
    group_b = await _make_group(db_session, name="Group B")
    member = await _make_member(db_session, "leftfirst@example.com", "小明")

    first_entry, _ = await join_group(
        db_session, group_a, member=member, password=None, nickname=None
    )
    first_entry.status = "left"
    await db_session.commit()

    second_entry, created_new = await join_group(
        db_session, group_b, member=member, password=None, nickname=None
    )
    assert created_new is True
    assert second_entry.group_id == group_b.id


async def test_member_whose_group_disbanded_can_create_a_new_one(
    db_session: AsyncSession,
) -> None:
    """Regression test: disband_group() deliberately never touches
    RosterEntry.status — a disbanded group stays readable/leavable
    (005-member-view's edge cases;
    test_already_active_member_short_circuits_even_on_disbanded_group in
    test_join_as_member.py relies on the same fact). Without excluding
    disbanded groups, get_active_group_id_for_member() would see the
    Member as "still active" there forever — including after an
    inactivity auto-disband the Member never even took an action for —
    and permanently lock them out of ever creating or joining another
    group."""
    group_a = await _make_group(db_session, name="Group A")
    member = await _make_member(db_session, "disbanded-create@example.com", "小明")
    await join_group(db_session, group_a, member=member, password=None, nickname=None)

    await disband_group(db_session, group_a)

    group, roster_entry, _admin_pin, _guest_token = await create_group(
        db_session, _create_payload(name="Group B"), member=member
    )
    assert group.name == "Group B"
    assert roster_entry.member_id == member.id


async def test_member_whose_group_disbanded_can_join_a_different_one(
    db_session: AsyncSession,
) -> None:
    group_a = await _make_group(db_session, name="Group A")
    group_b = await _make_group(db_session, name="Group B")
    member = await _make_member(db_session, "disbanded-join@example.com", "小明")
    await join_group(db_session, group_a, member=member, password=None, nickname=None)

    await disband_group(db_session, group_a)

    entry, created_new = await join_group(
        db_session, group_b, member=member, password=None, nickname=None
    )
    assert created_new is True
    assert entry.group_id == group_b.id


# --- Guest: exempt in all four combinations (hard technical limit, not a
# policy choice — see module docstring and each test's own note) --------


async def test_guest_joined_a_group_may_join_someone_elses_group(
    db_session: AsyncSession,
) -> None:
    """No cross-group identity exists for a Guest to check against — this
    is a hard technical limit (FR-022), not a policy choice: two Guest
    joins are indistinguishable from two different people."""
    group_a = await _make_group(db_session, name="Group A")
    group_b = await _make_group(db_session, name="Group B")

    entry_a, created_a = await join_group(
        db_session, group_a, member=None, password=None, nickname="訪客甲"
    )
    entry_b, created_b = await join_group(
        db_session, group_b, member=None, password=None, nickname="訪客甲"
    )
    assert created_a is True
    assert created_b is True
    assert entry_a.group_id == group_a.id
    assert entry_b.group_id == group_b.id


async def test_guest_joined_a_group_may_create_another_group(
    db_session: AsyncSession,
) -> None:
    group_a = await _make_group(db_session, name="Group A")

    entry_a, created_a = await join_group(
        db_session, group_a, member=None, password=None, nickname="訪客甲"
    )
    assert created_a is True

    group_b, roster_entry_b, _admin_pin, guest_token_b = await create_group(
        db_session, _create_payload(name="Group B", creator_nickname="訪客甲"), member=None
    )
    assert group_b.name == "Group B"
    assert roster_entry_b.member_id is None
    assert guest_token_b is not None
    assert roster_entry_b.group_id != entry_a.group_id


async def test_guest_created_a_group_may_join_someone_elses_group(
    db_session: AsyncSession,
) -> None:
    group_b = await _make_group(db_session, name="Group B (someone else's)")

    group_a, roster_entry_a, _admin_pin, guest_token_a = await create_group(
        db_session, _create_payload(name="Group A", creator_nickname="訪客甲"), member=None
    )
    assert guest_token_a is not None

    entry_b, created_b = await join_group(
        db_session, group_b, member=None, password=None, nickname="訪客甲"
    )
    assert created_b is True
    assert entry_b.group_id == group_b.id
    assert entry_b.group_id != group_a.id


async def test_guest_created_a_group_may_create_another_group(
    db_session: AsyncSession,
) -> None:
    group_a, _roster_entry_a, _admin_pin_a, guest_token_a = await create_group(
        db_session, _create_payload(name="Group A", creator_nickname="訪客甲"), member=None
    )
    assert guest_token_a is not None

    group_b, roster_entry_b, _admin_pin_b, guest_token_b = await create_group(
        db_session, _create_payload(name="Group B", creator_nickname="訪客乙"), member=None
    )
    assert group_b.name == "Group B"
    assert guest_token_b is not None
    assert roster_entry_b.group_id != group_a.id
