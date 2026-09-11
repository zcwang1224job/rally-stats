"""Unit test: 019-group-final-standings's `build_group_final_standings()` —
「我的團」歷史頁面的最終團隊排名，涵蓋範圍/排序/合併/is_self 邏輯，
per research.md #1/#2/#3/#4. T001 (a)-(h)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import build_group_final_standings
from app.domains.member.models import Member
from app.domains.member.security import hash_password
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant

pytestmark = pytest.mark.asyncio

T2 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
BEFORE = T2 - timedelta(hours=1)
EARLIER = BEFORE - timedelta(hours=1)


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Final Standings Test",
        "max_members": 16,
        "match_mode": "doubles",
        "scheduling_mechanism": "fair_rotation",
        "current_member_count": 1,
        "current_round_number": 2,
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
        user_number=str(uuid.uuid4())[:8],
        nickname=nickname,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def _make_entry(
    session: AsyncSession,
    group: Group,
    *,
    joined_at: datetime,
    status: str = "active",
    left_at: datetime | None = None,
    nickname: str | None = None,
    member_id: uuid.UUID | None = None,
) -> RosterEntry:
    entry = RosterEntry(
        group_id=group.id,
        member_id=member_id,
        nickname=nickname or f"P-{uuid.uuid4().hex[:6]}",
        status=status,
        joined_at=joined_at,
        left_at=left_at,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def _make_match(
    session: AsyncSession,
    group: Group,
    *,
    status: str,
    winner_team: str | None,
    team_a: list[uuid.UUID],
    team_b: list[uuid.UUID],
    round_number: int = 2,
) -> Match:
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=round_number,
        status=status,
        winner_team=winner_team,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
    )
    session.add(match)
    await session.flush()
    for pid in team_a:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="A"))
    for pid in team_b:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="B"))
    await session.commit()
    return match


def _row(rows, roster_entry_id: uuid.UUID):  # type: ignore[no-untyped-def]
    for row in rows:
        if row.roster_entry_id == str(roster_entry_id):
            return row
    raise AssertionError("roster entry not found in final standings")


async def test_covers_active_left_and_kicked(db_session: AsyncSession) -> None:
    """(a) FR-002: active/left/kicked members all appear, each labeled."""
    group = await _make_group(db_session)
    active = await _make_entry(db_session, group, joined_at=BEFORE, status="active")
    left = await _make_entry(db_session, group, joined_at=BEFORE, status="left")
    kicked = await _make_entry(db_session, group, joined_at=BEFORE, status="kicked")

    rows = await build_group_final_standings(db_session, group.id, viewer_member_id=uuid.uuid4())

    ids = {row.roster_entry_id for row in rows}
    assert {str(active.id), str(left.id), str(kicked.id)} <= ids
    assert _row(rows, active.id).current_status == "active"
    assert _row(rows, left.id).current_status == "left"
    assert _row(rows, kicked.id).current_status == "kicked"


async def test_guest_participant_included_without_special_marking(
    db_session: AsyncSession,
) -> None:
    """(b) FR-002: a guest (member_id IS NULL) appears exactly like anyone
    else — same fields, no separate "guest" flag anywhere on the row."""
    group = await _make_group(db_session)
    guest = await _make_entry(db_session, group, joined_at=BEFORE, nickname="訪客小明")

    rows = await build_group_final_standings(db_session, group.id, viewer_member_id=uuid.uuid4())

    row = _row(rows, guest.id)
    assert row.nickname == "訪客小明"
    assert not hasattr(row, "is_guest")


async def test_same_member_rejoin_merges_into_one_row(db_session: AsyncSession) -> None:
    """(c) research.md #1 / spec.md Edge Cases: a member who left and
    rejoined has two RosterEntry rows — MUST collapse into a single final
    standings row, with wins/losses summed across both stints."""
    group = await _make_group(db_session)
    member = await _make_member(db_session, "rejoin@example.com", "小華")
    first_stint = await _make_entry(
        db_session,
        group,
        joined_at=EARLIER,
        status="left",
        left_at=BEFORE,
        member_id=member.id,
        nickname="小華",
    )
    opponent = await _make_entry(db_session, group, joined_at=EARLIER)
    second_stint = await _make_entry(
        db_session, group, joined_at=T2, status="active", member_id=member.id, nickname="小華"
    )
    # First stint: 2 wins. Second stint: 3 wins.
    for _ in range(2):
        await _make_match(
            db_session, group, status="completed", winner_team="A",
            team_a=[first_stint.id], team_b=[opponent.id],
        )
    for _ in range(3):
        await _make_match(
            db_session, group, status="completed", winner_team="A",
            team_a=[second_stint.id], team_b=[opponent.id],
        )

    rows = await build_group_final_standings(db_session, group.id, viewer_member_id=uuid.uuid4())

    merged_rows = [r for r in rows if r.nickname == "小華"]
    assert len(merged_rows) == 1
    merged = merged_rows[0]
    assert merged.total_wins == 5
    assert merged.total_matches == 5
    # Representative attributes come from the latest stint.
    assert merged.current_status == "active"
    assert merged.roster_entry_id == str(second_stint.id)


async def test_ranks_by_total_wins_with_tie_break_by_joined_at(
    db_session: AsyncSession,
) -> None:
    """(d) research.md #1/#2: standard competition ranking over total_wins,
    ties broken by (merged) joined_at, next distinct rank skips accordingly."""
    group = await _make_group(db_session)
    first = await _make_entry(db_session, group, joined_at=EARLIER)
    tied_a = await _make_entry(db_session, group, joined_at=EARLIER)
    tied_b = await _make_entry(db_session, group, joined_at=BEFORE)
    last = await _make_entry(db_session, group, joined_at=EARLIER)
    for _ in range(3):
        await _make_match(
            db_session, group, status="completed", winner_team="A",
            team_a=[first.id], team_b=[last.id],
        )
    await _make_match(
        db_session, group, status="completed", winner_team="A",
        team_a=[tied_a.id], team_b=[last.id],
    )
    await _make_match(
        db_session, group, status="completed", winner_team="A",
        team_a=[tied_b.id], team_b=[last.id],
    )

    rows = await build_group_final_standings(db_session, group.id, viewer_member_id=uuid.uuid4())

    assert _row(rows, first.id).rank == 1
    assert _row(rows, tied_a.id).rank == 2
    assert _row(rows, tied_b.id).rank == 2
    assert _row(rows, last.id).rank == 4
    ids_in_order = [row.roster_entry_id for row in rows]
    assert ids_in_order.index(str(tied_a.id)) < ids_in_order.index(str(tied_b.id))


async def test_abandoned_match_not_counted(db_session: AsyncSession) -> None:
    """(e) FR-003: an abandoned match MUST NOT affect anyone's tally."""
    group = await _make_group(db_session)
    p1 = await _make_entry(db_session, group, joined_at=BEFORE)
    p2 = await _make_entry(db_session, group, joined_at=BEFORE)
    await _make_match(
        db_session, group, status="abandoned", winner_team=None, team_a=[p1.id], team_b=[p2.id],
    )

    rows = await build_group_final_standings(db_session, group.id, viewer_member_id=uuid.uuid4())

    assert _row(rows, p1.id).total_matches == 0
    assert _row(rows, p2.id).total_matches == 0


async def test_fixed_partner_ranks_individually(db_session: AsyncSession) -> None:
    """(f) FR-009: fixed_partner doubles still ranks each of the 4 players
    independently, never merged as a partnership."""
    group = await _make_group(db_session, scheduling_mechanism="fixed_partner")
    a1 = await _make_entry(db_session, group, joined_at=BEFORE)
    a2 = await _make_entry(db_session, group, joined_at=BEFORE)
    b1 = await _make_entry(db_session, group, joined_at=BEFORE)
    b2 = await _make_entry(db_session, group, joined_at=BEFORE)
    await _make_match(
        db_session, group, status="completed", winner_team="A",
        team_a=[a1.id, a2.id], team_b=[b1.id, b2.id],
    )

    rows = await build_group_final_standings(db_session, group.id, viewer_member_id=uuid.uuid4())

    assert _row(rows, a1.id).total_wins == 1
    assert _row(rows, a2.id).total_wins == 1
    assert _row(rows, b1.id).total_losses == 1
    assert _row(rows, b2.id).total_losses == 1


async def test_no_matches_yet_still_appears_with_zero_totals(db_session: AsyncSession) -> None:
    """(g) FR-007: a participant with no completed matches still appears,
    with total_matches == 0 (not excluded, not miscounted)."""
    group = await _make_group(db_session)
    bench = await _make_entry(db_session, group, joined_at=BEFORE)

    rows = await build_group_final_standings(db_session, group.id, viewer_member_id=uuid.uuid4())

    row = _row(rows, bench.id)
    assert row.total_matches == 0
    assert row.total_wins == 0
    assert row.total_losses == 0


async def test_is_self_marks_viewer_and_no_one_else(db_session: AsyncSession) -> None:
    """(h) research.md #4: is_self is true only for the group whose
    member_id matches viewer_member_id — including across a merged
    multi-stint group."""
    group = await _make_group(db_session)
    viewer = await _make_member(db_session, "viewer@example.com", "自己")
    other = await _make_member(db_session, "other@example.com", "別人")
    viewer_entry = await _make_entry(db_session, group, joined_at=BEFORE, member_id=viewer.id)
    other_entry = await _make_entry(db_session, group, joined_at=BEFORE, member_id=other.id)
    guest_entry = await _make_entry(db_session, group, joined_at=BEFORE)

    rows = await build_group_final_standings(db_session, group.id, viewer_member_id=viewer.id)

    assert _row(rows, viewer_entry.id).is_self is True
    assert _row(rows, other_entry.id).is_self is False
    assert _row(rows, guest_entry.id).is_self is False


async def test_empty_group_returns_empty_list(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)

    rows = await build_group_final_standings(db_session, group.id, viewer_member_id=uuid.uuid4())

    assert rows == []
