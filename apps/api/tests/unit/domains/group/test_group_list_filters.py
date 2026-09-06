"""Unit test: GET /groups filter query logic — court name/ID substring
match (any court hits), activity time range overlap (US5)."""

from datetime import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import list_groups

pytestmark = pytest.mark.asyncio


async def _make_group(
    session: AsyncSession,
    name: str,
    *,
    activity_time_start: time | None = None,
    activity_time_end: time | None = None,
) -> Group:
    group = Group(
        name=name,
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        activity_time_start=activity_time_start,
        activity_time_end=activity_time_end,
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_court(session: AsyncSession, group: Group, name: str) -> Court:
    court = Court(group_id=group.id, name=name)
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def test_court_name_filter_matches_any_court_in_group(db_session: AsyncSession) -> None:
    match_group = await _make_group(db_session, "場地名稱篩選-命中")
    await _make_court(db_session, match_group, "北場")
    await _make_court(db_session, match_group, "南場")

    other_group = await _make_group(db_session, "場地名稱篩選-不命中")
    await _make_court(db_session, other_group, "東場")

    groups, _ = await list_groups(db_session, court_name="南")
    ids = {g.id for g in groups}
    assert match_group.id in ids
    assert other_group.id not in ids


async def test_court_id_filter_exact_match(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, "場地ID篩選")
    court = await _make_court(db_session, group, "唯一場地")
    other_group = await _make_group(db_session, "場地ID篩選-其他")
    await _make_court(db_session, other_group, "其他場地")

    groups, _ = await list_groups(db_session, court_id=court.id)
    ids = {g.id for g in groups}
    assert group.id in ids
    assert other_group.id not in ids


async def test_time_filter_excludes_groups_without_activity_time(
    db_session: AsyncSession,
) -> None:
    with_time = await _make_group(
        db_session, "有時間", activity_time_start=time(19, 0), activity_time_end=time(21, 0)
    )
    without_time = await _make_group(db_session, "無時間")

    groups, _ = await list_groups(
        db_session, time_start=time(18, 0), time_end=time(22, 0)
    )
    ids = {g.id for g in groups}
    assert with_time.id in ids
    assert without_time.id not in ids


async def test_no_time_filter_shows_groups_without_activity_time(
    db_session: AsyncSession,
) -> None:
    without_time = await _make_group(db_session, "無時間-不篩選")

    groups, _ = await list_groups(db_session)
    ids = {g.id for g in groups}
    assert without_time.id in ids


async def test_time_filter_uses_overlap_semantics(db_session: AsyncSession) -> None:
    evening_group = await _make_group(
        db_session, "晚場", activity_time_start=time(19, 0), activity_time_end=time(21, 0)
    )
    morning_group = await _make_group(
        db_session, "早場", activity_time_start=time(7, 0), activity_time_end=time(9, 0)
    )

    groups, _ = await list_groups(
        db_session, time_start=time(20, 0), time_end=time(22, 0)
    )
    ids = {g.id for g in groups}
    assert evening_group.id in ids
    assert morning_group.id not in ids
