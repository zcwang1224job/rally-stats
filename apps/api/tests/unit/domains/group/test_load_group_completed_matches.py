"""Unit test: load_group_completed_matches() — 036 US3's bulk loader."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.service import load_group_completed_matches
from tests.unit.domains._match_history import (
    make_entry,
    make_group,
    make_member,
    make_played_match,
)
from tests.unit.domains.group.test_match_stat_inputs import count_selects

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


async def test_only_this_groups_completed_matches_newest_first(db_session: AsyncSession) -> None:
    member = await make_member(db_session, "loader@example.com")
    group = await make_group(db_session, "Loader", match_mode="singles")
    other = await make_group(db_session, "Other", match_mode="singles")
    a = await make_entry(db_session, group, "小明", member.id)
    b = await make_entry(db_session, group, "小美")
    x = await make_entry(db_session, other, "外人一")
    y = await make_entry(db_session, other, "外人二")
    old = await make_played_match(
        db_session,
        group,
        team_a=[a.id],
        team_b=[b.id],
        sides="A" * 21,
        ended_at=NOW - timedelta(days=3),
    )
    new = await make_played_match(
        db_session,
        group,
        team_a=[a.id],
        team_b=[b.id],
        sides="B" * 21,
        ended_at=NOW - timedelta(days=1),
    )
    abandoned = await make_played_match(
        db_session, group, team_a=[a.id], team_b=[b.id], sides="A" * 21, ended_at=NOW
    )
    abandoned.status = "abandoned"
    await db_session.commit()
    await make_played_match(db_session, other, team_a=[x.id], team_b=[y.id], sides="A" * 21)

    loaded = await load_group_completed_matches(db_session, group.id)

    assert [match.id for match, _ in loaded] == [new.id, old.id]
    match, summary = loaded[0]
    assert summary.match_id == str(match.id)
    assert [(p.nickname, p.member_id) for p in summary.team_a] == [("小明", str(member.id))]
    assert [(p.nickname, p.member_id) for p in summary.team_b] == [("小美", None)]


async def test_a_group_without_matches(db_session: AsyncSession) -> None:
    group = await make_group(db_session, "Empty")
    assert await load_group_completed_matches(db_session, group.id) == []


async def test_query_count_does_not_grow_with_the_number_of_matches(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session, "Counted", match_mode="singles")
    a = await make_entry(db_session, group, "小明")
    b = await make_entry(db_session, group, "小美")
    await make_played_match(db_session, group, team_a=[a.id], team_b=[b.id], sides="A" * 21)
    with count_selects(db_session) as few:
        await load_group_completed_matches(db_session, group.id)
    for _ in range(6):
        await make_played_match(db_session, group, team_a=[a.id], team_b=[b.id], sides="A" * 21)
    with count_selects(db_session) as many:
        await load_group_completed_matches(db_session, group.id)
    assert len(few) == len(many) == 2
