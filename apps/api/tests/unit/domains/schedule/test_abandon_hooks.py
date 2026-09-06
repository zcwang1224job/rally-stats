"""Unit test: abandon_group_matches (001's AbandonMatchesHook) and
abandon_court_matches (002's AbandonCourtMatchesHook) — Foundational T010/T011,
per research.md #2."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.schedule.models import Match
from app.domains.schedule.service import abandon_court_matches, abandon_group_matches


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Abandon Hooks Test",
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


async def _make_court(session: AsyncSession, group: Group) -> Court:
    court = Court(group_id=group.id, name="1號場")
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


def _make_match(group: Group, court: Court | None, status: str, round_number: int = 1) -> Match:
    return Match(
        group_id=group.id,
        court_id=court.id if court else None,
        round_number=round_number,
        status=status,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
    )


@pytest.mark.asyncio
async def test_abandon_group_matches_abandons_queued_and_in_progress(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    queued = _make_match(group, None, "queued")
    in_progress = _make_match(group, court, "in_progress")
    already_completed = _make_match(group, court, "completed")
    db_session.add_all([queued, in_progress, already_completed])
    await db_session.commit()

    await abandon_group_matches(db_session, group.id)
    await db_session.commit()

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id).order_by(Match.status)
    )
    statuses = {m.id: m.status for m in result.scalars().all()}
    assert statuses[queued.id] == "abandoned"
    assert statuses[in_progress.id] == "abandoned"
    assert statuses[already_completed.id] == "completed"  # untouched


@pytest.mark.asyncio
async def test_abandon_group_matches_noop_when_nothing_active(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    # No matches at all — must not raise.
    await abandon_group_matches(db_session, group.id)
    await db_session.commit()


@pytest.mark.asyncio
async def test_abandon_court_matches_returns_true_when_match_abandoned(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    in_progress = _make_match(group, court, "in_progress")
    db_session.add(in_progress)
    await db_session.commit()

    had_active_match = await abandon_court_matches(db_session, court.id)
    await db_session.commit()

    assert had_active_match is True
    await db_session.refresh(in_progress)
    assert in_progress.status == "abandoned"


@pytest.mark.asyncio
async def test_abandon_court_matches_returns_false_when_nothing_active(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)

    had_active_match = await abandon_court_matches(db_session, court.id)
    assert had_active_match is False


@pytest.mark.asyncio
async def test_abandon_court_matches_does_not_touch_other_courts(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    court_a = await _make_court(db_session, group)
    court_b = Court(group_id=group.id, name="2號場")
    db_session.add(court_b)
    await db_session.commit()
    await db_session.refresh(court_b)

    match_b = _make_match(group, court_b, "in_progress")
    db_session.add(match_b)
    await db_session.commit()

    had_active_match = await abandon_court_matches(db_session, court_a.id)
    await db_session.commit()

    assert had_active_match is False
    await db_session.refresh(match_b)
    assert match_b.status == "in_progress"


@pytest.mark.asyncio
async def test_abandon_court_matches_unknown_court_is_noop(db_session: AsyncSession) -> None:
    had_active_match = await abandon_court_matches(db_session, uuid.uuid4())
    assert had_active_match is False
