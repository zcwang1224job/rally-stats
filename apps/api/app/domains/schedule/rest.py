"""037-rest-ready-toggle: putting a player on rest and back — the one
function both rest-state endpoints call once they have checked who may
(research.md Decision 7). This module imports `service`; `service` never
imports it.

Resting changes no match when it's pressed (FR-013). What happens to a
resting player's queued matches is decided when one of them is called
(`service._choose_next_queued_match()`), and who plays in a new round
simply leaves them out (`service._IS_READY`)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.realtime import group_notifications_channel, publish
from app.domains.group.models import Group
from app.domains.roster.models import RosterEntry, RosterRestPeriod
from app.domains.schedule import service
from app.domains.schedule.algorithms import returning_played_credit
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.schemas import RestStateResponse


async def set_rest_state(
    session: AsyncSession,
    group: Group,
    entry: RosterEntry,
    *,
    resting: bool,
    confirm_round_end: bool = False,
) -> RestStateResponse:
    """Puts `entry` into the requested state. A request for the state it is
    already in changes and publishes nothing (`changed=False`). Callers
    MUST have already checked the caller may change this entry."""
    del confirm_round_end  # 037 T023: REST_ENDS_ROUND
    if group.status == "disbanded":
        raise ApiError("GROUP_DISBANDED", status_code=409)

    # Same lock as continuous rotation and call-up substitution, so a court
    # being filled never reads a half-applied change.
    await session.execute(select(Group.id).where(Group.id == group.id).with_for_update())
    current = (
        await session.execute(select(RosterEntry).where(RosterEntry.id == entry.id))
    ).scalar_one_or_none()
    if current is None or current.group_id != group.id or current.status != "active":
        raise ApiError("ROSTER_ENTRY_NOT_FOUND", status_code=404)

    if (current.resting_since is not None) == resting:
        await session.commit()
        return await _response(session, current, changed=False)

    now = datetime.now(UTC)
    rested_since = current.resting_since
    if rested_since is None:
        current.resting_since = now
        await session.flush()
        # 037 T023: REST_ENDS_ROUND
    else:
        session.add(
            RosterRestPeriod(
                roster_entry_id=current.id,
                group_id=group.id,
                started_at=rested_since,
                ended_at=max(now, rested_since),
            )
        )
        current.played_credit += await _returning_credit(session, group, current)
        current.resting_since = None
        await session.flush()
        # 037 T024: late-joiner matches for this round

    await session.commit()
    await session.refresh(current)
    await session.refresh(group)

    # Fills courts a returning player (or a newly possible match) lets
    # start, and has every court refetch its "next up" preview.
    await service.refresh_courts_after_roster_change(session, group)
    # 037 T023: auto next round

    await publish(
        group_notifications_channel(str(group.id)),
        "roster.restChanged",
        {"roster_entry_id": str(current.id), "nickname": current.nickname, "resting": resting},
    )
    return await _response(session, current, changed=True)


async def _returning_credit(session: AsyncSession, group: Group, entry: RosterEntry) -> int:
    """Matches to credit `entry` on coming back (research.md Decision 4):
    up to the lower median of the other ready players' played count,
    credit included. Called while `entry` is still resting, so the ready
    roster doesn't include them. Someone who has never played gets none —
    they come back a newcomer, which already puts them first."""
    await session.flush()  # the rest period just added counts in histories
    histories = await service._get_player_histories(session, group.id)
    own = histories.get(entry.id)
    if own is None:
        return 0
    others = [
        histories[pid].played if pid in histories else 0
        for pid in await service._get_ready_roster_ordered(session, group.id)
    ]
    return returning_played_credit(own.played, others)


async def _response(
    session: AsyncSession, entry: RosterEntry, *, changed: bool
) -> RestStateResponse:
    playing = await session.execute(
        select(MatchParticipant.id)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(MatchParticipant.roster_entry_id == entry.id, Match.status == "in_progress")
        .limit(1)
    )
    return RestStateResponse(
        roster_entry_id=str(entry.id),
        resting=entry.resting_since is not None,
        resting_since=entry.resting_since,
        currently_playing=playing.scalar_one_or_none() is not None,
        changed=changed,
    )
