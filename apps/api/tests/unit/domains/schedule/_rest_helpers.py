"""037-rest-ready-toggle: builders shared by the rest tests. Not a test
module. `set_resting()` writes the column directly so scheduling tests
don't depend on `set_rest_state()`."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.service import _advance_after_terminal


async def make_group(
    session: AsyncSession,
    *,
    match_mode: str = "doubles",
    scheduling_mechanism: str = "fair_rotation",
    partner_source: str = "auto",
    continuous_rotation: bool = False,
    auto_next_round: bool = False,
) -> Group:
    group = Group(
        name="Rest Test",
        max_members=40,
        match_mode=match_mode,
        scheduling_mechanism=scheduling_mechanism,
        partner_source=partner_source,
        continuous_rotation=continuous_rotation,
        auto_next_round=auto_next_round,
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def make_courts(session: AsyncSession, group: Group, n: int) -> list[Court]:
    courts = [Court(group_id=group.id, name=f"{i + 1}號場") for i in range(n)]
    session.add_all(courts)
    await session.commit()
    for court in courts:
        await session.refresh(court)
    return courts


async def make_players(session: AsyncSession, group: Group, n: int) -> list[RosterEntry]:
    """Guests (no member_id), joined one after another, so join order is
    list order."""
    entries = []
    for i in range(n):
        entry = RosterEntry(group_id=group.id, nickname=f"P{i}", status="active")
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        entries.append(entry)
    return entries


async def set_resting(
    session: AsyncSession, entry: RosterEntry, since: datetime | None = None
) -> None:
    entry.resting_since = since or datetime.now(UTC)
    await session.commit()


async def set_ready(session: AsyncSession, entry: RosterEntry) -> None:
    entry.resting_since = None
    await session.commit()


async def finish_match(session: AsyncSession, match: Match, winner: str = "A") -> Match | None:
    """Completes an in_progress match and runs the same follow-up as a
    scored match ending (next match onto the court, auto next round).
    Returns whatever the court picked up next."""
    match.status = "completed"
    match.winner_team = winner
    match.ended_at = datetime.now(UTC)
    await session.commit()
    return await _advance_after_terminal(session, match)


async def participants(session: AsyncSession, match_id: object) -> set[object]:
    result = await session.execute(
        select(MatchParticipant.roster_entry_id).where(MatchParticipant.match_id == match_id)
    )
    return set(result.scalars())


async def round_matches(session: AsyncSession, group: Group, round_number: int | None = None) -> list[Match]:
    await session.refresh(group)
    result = await session.execute(
        select(Match)
        .where(
            Match.group_id == group.id,
            Match.round_number == (round_number or group.current_round_number),
        )
        .order_by(Match.queue_position.asc().nulls_last(), Match.created_at)
    )
    return list(result.scalars())


async def in_progress(session: AsyncSession, group: Group) -> list[Match]:
    result = await session.execute(
        select(Match).where(Match.group_id == group.id, Match.status == "in_progress")
    )
    return list(result.scalars())
