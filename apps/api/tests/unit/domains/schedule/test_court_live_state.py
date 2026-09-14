"""Unit test: court_live_state() 之 next_up/waiting_reason 組裝邏輯
（FR-018）——手動安排模式恆為 null（改用 waiting_reason 表達），演算法
模式下有排隊中比賽時正確帶出其參賽者預告。"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member.models import Member
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import court_live_state, create_match_with_participants

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Court Live State Test",
        "max_members": 4,
        "match_mode": "singles",
        "scheduling_mechanism": "fair_rotation",
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


async def _make_court(session: AsyncSession, group: Group, name: str = "1號場") -> Court:
    court = Court(group_id=group.id, name=name)
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def _make_roster_entry(
    session: AsyncSession, group: Group, nickname: str, member_id: uuid.UUID | None = None
) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, member_id=member_id, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_manual_mode_next_up_always_null(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="manual")
    court = await _make_court(db_session, group)

    state = await court_live_state(db_session, court)

    assert state.current_match is None
    assert state.waiting_reason == "manual_assignment"
    assert state.next_up is None


async def test_algorithmic_mode_no_queued_match(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)

    state = await court_live_state(db_session, court)

    assert state.current_match is None
    assert state.waiting_reason == "no_queued_match"
    assert state.next_up is None


async def test_algorithmic_mode_shows_next_up_when_queued(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1 = await _make_roster_entry(db_session, group, "小明")
    p2 = await _make_roster_entry(db_session, group, "小美")
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    state = await court_live_state(db_session, court)

    assert state.current_match is None
    assert state.waiting_reason == "no_queued_match"
    assert state.next_up is not None
    assert state.next_up.match_id == str(queued.id)
    nicknames = {p.nickname for p in state.next_up.participants}
    assert nicknames == {"小明", "小美"}


async def test_current_match_present_reports_no_waiting_reason(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1 = await _make_roster_entry(db_session, group, "小明")
    p2 = await _make_roster_entry(db_session, group, "小美")
    await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    state = await court_live_state(db_session, court)

    assert state.current_match is not None
    assert state.waiting_reason is None
    assert state.next_up is None


async def test_current_match_and_next_up_never_carry_member_id(db_session: AsyncSession) -> None:
    """026-match-record-friend-invite research.md #1 (T030): court_live_state()
    backs the PUBLIC, no-login GET /courts/by-token/{token}/state endpoint
    and the Ably rotation.updated broadcast payload — even for a
    Member-linked participant, ParticipantSummary.member_id MUST stay None
    here. Only build_schedule_snapshot() (the authenticated member/admin
    schedule endpoints) is allowed to populate it."""
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    member = Member(
        email="court-live-state-participant@example.com",
        password_hash="x",
        nickname="會員",
        user_number=str(uuid.uuid4())[:8],
        verification_status="verified",
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)

    p1 = await _make_roster_entry(db_session, group, "會員", member.id)
    p2 = await _make_roster_entry(db_session, group, "訪客")
    await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    state = await court_live_state(db_session, court)

    assert state.current_match is not None
    for participant in state.current_match.participants:
        assert participant.member_id is None

    court2 = await _make_court(db_session, group, "2號場")
    p3 = await _make_roster_entry(db_session, group, "會員2", member.id)
    p4 = await _make_roster_entry(db_session, group, "訪客2")
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p3.id], team_b=[p4.id],
    )
    await db_session.commit()
    state2 = await court_live_state(db_session, court2)
    assert state2.next_up is not None
    assert state2.next_up.match_id == str(queued.id)
    for participant in state2.next_up.participants:
        assert participant.member_id is None
