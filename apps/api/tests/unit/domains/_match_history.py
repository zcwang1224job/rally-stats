"""Shared fixtures for 034-clutch-points-player-dashboard: a completed match
WITH its point-level history (score events, serve records, shot placements)
written in one commit. Used by both the group-side batch loader test and the
member-side dashboard tests, which is why it lives above either directory.

The serve records are deliberately simple — the team that just scored
serves next, always with its first-listed player from the right court — so
every expectation in a test can be worked out by reading `sides`: point i is
served by whoever won point i-1, and the receiver is the other team's
first-listed player."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member.models import Member
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import (
    Match,
    MatchParticipant,
    ScoreEvent,
    ScoreServeRecord,
    ShotPlacementRecord,
)


@dataclass(frozen=True)
class Shot:
    """What the scorer recorded for one point (index into `sides`)."""

    scorer: uuid.UUID | None = None
    loser: uuid.UUID | None = None
    landing: tuple[float, float] | None = None
    ending: str | None = None  # 035: winner / out / net / serve_fault / other_error


async def make_group(
    session: AsyncSession, name: str = "Dashboard Test", match_mode: str = "doubles"
) -> Group:
    group = Group(
        name=name,
        max_members=8,
        match_mode=match_mode,
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def make_member(
    session: AsyncSession, email: str, verification_status: str = "verified"
) -> Member:
    member = Member(
        email=email,
        password_hash="x",
        nickname="小明",
        user_number=str(uuid.uuid4())[:8],
        verification_status=verification_status,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def make_entry(
    session: AsyncSession,
    group: Group,
    nickname: str,
    member_id: uuid.UUID | None = None,
    *,
    status: str = "active",
    joined_at: datetime | None = None,
) -> RosterEntry:
    """036: `status` / `joined_at` let a test model a member who left and
    rejoined (two rows for the same member in one group)."""
    entry = RosterEntry(group_id=group.id, nickname=nickname, member_id=member_id, status=status)
    if joined_at is not None:
        entry.joined_at = joined_at
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def make_played_match(
    session: AsyncSession,
    group: Group,
    *,
    team_a: list[uuid.UUID],
    team_b: list[uuid.UUID],
    sides: str,
    target_score: int = 21,
    cap_score: int = 30,
    ended_at: datetime | None = None,
    round_number: int = 1,
    log: str = "complete",
    serve_records: bool = True,
    shots: dict[int, Shot] | None = None,
) -> Match:
    """`sides` is the correction-free point sequence ("ABBA..."); the final
    score and winner follow from it. `log`: "complete" writes every point,
    "partial" drops the first two events (recording started mid-match),
    "none" writes no events at all."""
    final = {"A": sides.count("A"), "B": sides.count("B")}
    ended = ended_at if ended_at is not None else datetime.now(UTC)
    started = ended - timedelta(seconds=20 * len(sides) + 60)
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=round_number,
        status="completed",
        winner_team=sides[-1],
        score_a=final["A"],
        score_b=final["B"],
        target_score=target_score,
        deuce_threshold=max(1, target_score - 1),
        cap_score=cap_score,
        started_at=started,
        ended_at=ended,
    )
    session.add(match)
    await session.flush()
    for pid in team_a:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="A"))
    for pid in team_b:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="B"))

    teams = {"A": team_a, "B": team_b}
    score = {"A": 0, "B": 0}
    skip = {"complete": 0, "partial": 2, "none": len(sides)}[log]
    for index, side in enumerate(sides):
        score[side] += 1
        if index < skip:
            continue
        event = ScoreEvent(
            match_id=match.id,
            group_id=group.id,
            side=side,
            delta=1,
            score_a=score["A"],
            score_b=score["B"],
            source="control_panel",
            created_at=started + timedelta(seconds=20 * (index + 1)),
        )
        session.add(event)
        await session.flush()
        if serve_records:
            session.add(
                ScoreServeRecord(
                    score_event_id=event.id,
                    match_id=match.id,
                    group_id=group.id,
                    server_roster_entry_id=teams[side][0],
                    server_team=side,
                    team_a_right_roster_entry_id=team_a[0],
                    team_a_left_roster_entry_id=team_a[1] if len(team_a) > 1 else None,
                    team_b_right_roster_entry_id=team_b[0],
                    team_b_left_roster_entry_id=team_b[1] if len(team_b) > 1 else None,
                )
            )
        shot = (shots or {}).get(index)
        if shot is not None:
            session.add(
                ShotPlacementRecord(
                    score_event_id=event.id,
                    match_id=match.id,
                    group_id=group.id,
                    roster_entry_id=shot.scorer,
                    losing_roster_entry_id=shot.loser,
                    team=side,
                    landing_x=shot.landing[0] if shot.landing else None,
                    landing_y=shot.landing[1] if shot.landing else None,
                    ending_type=shot.ending,
                )
            )
    await session.commit()
    await session.refresh(match)
    return match
