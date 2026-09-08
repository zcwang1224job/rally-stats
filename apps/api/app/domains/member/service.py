"""Member domain service layer: auth, verification, profile, and search.
Per specs/006-member-friends/plan.md."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from itertools import permutations
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import send_email
from app.core.errors import ApiError
from app.domains.friend.service import get_friendship_status
from app.domains.group.models import Group
from app.domains.group.schemas import (
    MemberMatchRecordsResponse,
    MemberMatchRecordSummary,
    OpponentRecord,
    RoundWinRatePoint,
)
from app.domains.group.service import (
    _completed_matches_query,
    build_group_match_records,
    get_group_by_id,
    verify_ever_group_member,
)
from app.domains.member.models import EmailVerificationToken, Member, PasswordResetToken
from app.domains.member.schemas import (
    MemberGroupHistoryResponse,
    MemberGroupStatsResponse,
    MyGroupsResponse,
    MyGroupSummary,
    SearchMemberResponse,
)
from app.domains.member.security import (
    generate_unique_user_number,
    hash_password,
    issue_access_token,
    issue_refresh_token,
    verify_password,
)
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.schemas import ParticipantSummary

_VERIFICATION_TOKEN_TTL = timedelta(hours=24)
_RESEND_VERIFICATION_COOLDOWN = timedelta(seconds=60)
_PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)
_MEMBER_MATCH_RECORDS_PAGE_SIZE = 20


async def login(session: AsyncSession, email: str, password: str) -> tuple[Member, str, str]:
    """FR-009: unverified members MUST still be able to log in successfully
    — verification-gating happens per-endpoint (`require_verified_member`),
    not at login itself."""
    result = await session.execute(select(Member).where(Member.email == email.lower()))
    member = result.scalar_one_or_none()
    if member is None or not verify_password(password, member.password_hash):
        raise ApiError("INVALID_CREDENTIALS", status_code=401)

    access_token = issue_access_token(str(member.id), member.token_version)
    refresh_token = issue_refresh_token(str(member.id), member.token_version)
    return member, access_token, refresh_token


def _verification_link(token: str) -> str:
    return f"{get_settings().frontend_base_url}/auth/verify-email/{token}"


async def _issue_verification_token_and_email(session: AsyncSession, member: Member) -> None:
    verification_token = EmailVerificationToken(
        member_id=member.id, expires_at=datetime.now(UTC) + _VERIFICATION_TOKEN_TTL
    )
    session.add(verification_token)
    await session.flush()
    await session.commit()
    await session.refresh(verification_token)
    await send_email(
        member.email,
        "請驗證你的信箱",
        f"請點擊以下連結完成信箱驗證：{_verification_link(str(verification_token.token))}",
    )


async def register(session: AsyncSession, email: str, password: str) -> Member:
    """Turnstile verification happens at the router layer (matches
    group/router.py's create_group precedent) — this function has no
    knowledge of it. FR-004: Email uniqueness is case-insensitive
    (normalized to lowercase, per FR-006)."""
    normalized_email = email.lower()
    existing = await session.execute(select(Member.id).where(Member.email == normalized_email))
    if existing.scalar_one_or_none() is not None:
        raise ApiError("EMAIL_ALREADY_REGISTERED", status_code=409)

    user_number = await generate_unique_user_number(session)
    member = Member(
        email=normalized_email, password_hash=hash_password(password), user_number=user_number
    )
    session.add(member)
    await session.flush()
    await session.refresh(member)

    await _issue_verification_token_and_email(session, member)
    return member


async def verify_email(session: AsyncSession, token: uuid.UUID) -> Member:
    result = await session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token == token)
    )
    verification_token = result.scalar_one_or_none()
    if verification_token is None:
        raise ApiError("VERIFICATION_TOKEN_INVALID", status_code=404)
    if verification_token.used_at is not None:
        raise ApiError("VERIFICATION_TOKEN_ALREADY_USED", status_code=409)
    if verification_token.expires_at < datetime.now(UTC):
        raise ApiError("VERIFICATION_TOKEN_EXPIRED", status_code=410)

    verification_token.used_at = datetime.now(UTC)
    member_result = await session.execute(
        select(Member).where(Member.id == verification_token.member_id)
    )
    member = member_result.scalar_one()
    member.verification_status = "verified"
    await session.commit()
    await session.refresh(member)
    return member


async def resend_verification(session: AsyncSession, member: Member) -> None:
    if member.verification_status == "verified":
        raise ApiError("ALREADY_VERIFIED", status_code=409)

    last_token_result = await session.execute(
        select(EmailVerificationToken.created_at)
        .where(EmailVerificationToken.member_id == member.id)
        .order_by(EmailVerificationToken.created_at.desc())
        .limit(1)
    )
    last_created_at = last_token_result.scalar_one_or_none()
    if last_created_at is not None and datetime.now(UTC) - last_created_at < (
        _RESEND_VERIFICATION_COOLDOWN
    ):
        raise ApiError("RESEND_RATE_LIMITED", status_code=429)

    await _issue_verification_token_and_email(session, member)


def _reset_link(token: str) -> str:
    return f"{get_settings().frontend_base_url}/auth/reset-password/{token}"


async def forgot_password(session: AsyncSession, email: str) -> None:
    """FR-013 (2026-09-01 clarification): silent no-op for an unregistered
    Email — never raises, never reveals whether the account exists."""
    result = await session.execute(select(Member).where(Member.email == email.lower()))
    member = result.scalar_one_or_none()
    if member is None:
        return

    reset_token = PasswordResetToken(
        member_id=member.id, expires_at=datetime.now(UTC) + _PASSWORD_RESET_TOKEN_TTL
    )
    session.add(reset_token)
    await session.flush()
    await session.commit()
    await session.refresh(reset_token)
    await send_email(
        member.email,
        "重設密碼",
        f"請點擊以下連結重設密碼：{_reset_link(str(reset_token.token))}",
    )


async def reset_password(session: AsyncSession, token: uuid.UUID, new_password: str) -> Member:
    """FR-014/015: also marks the account verified and bumps `token_version`
    — invalidating every device's session, including the one performing the
    reset (unlike change-password, which preserves the current device)."""
    result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token)
    )
    reset_token = result.scalar_one_or_none()
    if reset_token is None:
        raise ApiError("RESET_TOKEN_INVALID", status_code=404)
    if reset_token.used_at is not None:
        raise ApiError("RESET_TOKEN_ALREADY_USED", status_code=409)
    if reset_token.expires_at < datetime.now(UTC):
        raise ApiError("RESET_TOKEN_EXPIRED", status_code=410)

    reset_token.used_at = datetime.now(UTC)
    member_result = await session.execute(select(Member).where(Member.id == reset_token.member_id))
    member = member_result.scalar_one()
    member.password_hash = hash_password(new_password)
    member.verification_status = "verified"
    member.token_version += 1
    await session.commit()
    await session.refresh(member)
    return member


async def set_nickname(session: AsyncSession, member: Member, nickname: str) -> Member:
    """FR-023/024: updates `members.nickname` only — MUST NOT cascade to any
    existing `roster_entries` row (research.md #10)."""
    member.nickname = nickname
    await session.commit()
    await session.refresh(member)
    return member


async def change_password(
    session: AsyncSession, member: Member, current_password: str, new_password: str
) -> tuple[Member, str, str]:
    """FR-025/026: bumps `token_version` (invalidating every other device)
    but immediately issues a fresh token pair for the requesting device."""
    if not verify_password(current_password, member.password_hash):
        raise ApiError("CURRENT_PASSWORD_INCORRECT", status_code=400)

    member.password_hash = hash_password(new_password)
    member.token_version += 1
    await session.commit()
    await session.refresh(member)

    access_token = issue_access_token(str(member.id), member.token_version)
    refresh_token = issue_refresh_token(str(member.id), member.token_version)
    return member, access_token, refresh_token


async def _build_member_match_record_summaries(
    session: AsyncSession,
    matches: list[Match],
    my_team_by_match: dict[uuid.UUID, str],
) -> list[MemberMatchRecordSummary]:
    if not matches:
        return []
    match_ids = [match.id for match in matches]
    participants_result = await session.execute(
        select(MatchParticipant, RosterEntry)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(MatchParticipant.match_id.in_(match_ids))
    )
    participants_by_match: dict[uuid.UUID, list[tuple[MatchParticipant, RosterEntry]]] = (
        defaultdict(list)
    )
    for participant, entry in participants_result.all():
        participants_by_match[participant.match_id].append((participant, entry))

    group_ids = {match.group_id for match in matches}
    group_result = await session.execute(
        select(Group.id, Group.name).where(Group.id.in_(group_ids))
    )
    group_name_by_id = {row[0]: row[1] for row in group_result.all()}

    summaries = []
    for match in matches:
        team_a: list[ParticipantSummary] = []
        team_b: list[ParticipantSummary] = []
        for participant, entry in participants_by_match.get(match.id, []):
            summary = ParticipantSummary(
                roster_entry_id=str(entry.id), nickname=entry.nickname, team=participant.team
            )
            (team_a if participant.team == "A" else team_b).append(summary)
        summaries.append(
            MemberMatchRecordSummary(
                match_id=str(match.id),
                round_number=match.round_number,
                team_a=team_a,
                team_b=team_b,
                score_a=match.score_a,
                score_b=match.score_b,
                winner_team=match.winner_team,
                started_at=match.started_at,
                ended_at=match.ended_at,
                group_id=str(match.group_id),
                group_name=group_name_by_id.get(match.group_id, ""),
                won=my_team_by_match.get(match.id) == match.winner_team,
            )
        )
    return summaries


def _matches_distinct_terms(terms: list[str] | None, candidates: list[str]) -> bool:
    """True if every search term in `terms` can be matched (case-insensitive
    substring) against a *distinct* nickname in `candidates` — doubles has
    (at most) two opponents/partners, and two search terms filtering for
    "against these two specific people" must not both be satisfied by the
    same one person. With at most 2 terms and 2 candidates in practice,
    brute-forcing every assignment is cheap."""
    cleaned = [t.strip().lower() for t in (terms or []) if t and t.strip()]
    if not cleaned:
        return True
    if len(cleaned) > len(candidates):
        return False
    lowered = [c.lower() for c in candidates]
    return any(
        all(term in candidate for term, candidate in zip(cleaned, combo, strict=True))
        for combo in permutations(lowered, len(cleaned))
    )


def _compare(value: int, cmp: Literal["gt", "eq", "lt"], target: int) -> bool:
    if cmp == "gt":
        return value > target
    if cmp == "eq":
        return value == target
    return value < target


async def build_member_match_records(
    session: AsyncSession,
    member_id: uuid.UUID,
    page: int = 1,
    *,
    opponents: list[str] | None = None,
    partners: list[str] | None = None,
    result: Literal["win", "loss"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    round_from: int | None = None,
    round_to: int | None = None,
    self_score_cmp: Literal["gt", "eq", "lt"] | None = None,
    self_score: int | None = None,
    opponent_score_cmp: Literal["gt", "eq", "lt"] | None = None,
    opponent_score: int | None = None,
    group_id: uuid.UUID | None = None,
) -> MemberMatchRecordsResponse:
    """005-member-view US5 (FR-017~020), extended with filters/statistics: a
    member's completed matches across every group they've ever joined as a
    Member (never as a Guest — research.md #9, `roster_entries.member_id IS
    NULL` for Guest entries naturally excludes them, no extra guard needed).

    Filters and every aggregate below (win/loss counts, the round-by-round
    win-rate trend, the opponent leaderboard) are all computed over the
    *entire* filtered result set, not just the current page — same
    plan.md Scale/Scope reasoning as before: a single member's total match
    count is small enough that loading it all into Python is cheap, and
    doing it this way avoids duplicating the nickname/score logic in SQL.

    `group_id` (014-member-groups-history, research.md #2): keyword-only,
    defaults to `None` — every pre-existing caller (the cross-group
    `/members/me/match-records` endpoint) omits it and keeps its existing
    behavior unchanged. Only `get_member_group_history()` passes it, to
    narrow this same aggregate logic down to one group's worth of matches
    rather than duplicating the win/loss-counting logic a third time."""
    participant_exists = (
        select(MatchParticipant.id)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(MatchParticipant.match_id == Match.id, RosterEntry.member_id == member_id)
        .exists()
    )
    base_query = _completed_matches_query().where(participant_exists)
    if group_id is not None:
        base_query = base_query.where(Match.group_id == group_id)

    all_matches_result = await session.execute(
        base_query.order_by(Match.ended_at.desc(), Match.round_number.desc())
    )
    all_matches = list(all_matches_result.scalars())

    my_team_by_match: dict[uuid.UUID, str] = {}
    my_entry_by_match: dict[uuid.UUID, uuid.UUID] = {}
    if all_matches:
        match_ids = [match.id for match in all_matches]
        participation_result = await session.execute(
            select(
                MatchParticipant.match_id,
                MatchParticipant.team,
                MatchParticipant.roster_entry_id,
            )
            .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
            .where(MatchParticipant.match_id.in_(match_ids), RosterEntry.member_id == member_id)
        )
        for match_id, team, roster_entry_id in participation_result.all():
            my_team_by_match[match_id] = team
            my_entry_by_match[match_id] = roster_entry_id

    summaries = await _build_member_match_record_summaries(session, all_matches, my_team_by_match)

    filtered: list[tuple[Match, MemberMatchRecordSummary, bool]] = []
    for match, summary in zip(all_matches, summaries, strict=True):
        my_team = my_team_by_match.get(match.id)
        if my_team is None:
            continue
        my_entry_id = str(my_entry_by_match[match.id])
        match_opponents = summary.team_b if my_team == "A" else summary.team_a
        match_partners = [
            p for p in (summary.team_a if my_team == "A" else summary.team_b)
            if p.roster_entry_id != my_entry_id
        ]
        my_score = match.score_a if my_team == "A" else match.score_b
        their_score = match.score_b if my_team == "A" else match.score_a
        won = summary.won

        if not _matches_distinct_terms(opponents, [p.nickname for p in match_opponents]):
            continue
        if not _matches_distinct_terms(partners, [p.nickname for p in match_partners]):
            continue
        if result is not None and won != (result == "win"):
            continue
        if match.ended_at is not None:
            match_date = match.ended_at.date()
            if date_from is not None and match_date < date_from:
                continue
            if date_to is not None and match_date > date_to:
                continue
        if round_from is not None and match.round_number < round_from:
            continue
        if round_to is not None and match.round_number > round_to:
            continue
        if self_score_cmp is not None and self_score is not None and not _compare(
            my_score, self_score_cmp, self_score
        ):
            continue
        if opponent_score_cmp is not None and opponent_score is not None and not _compare(
            their_score, opponent_score_cmp, opponent_score
        ):
            continue

        filtered.append((match, summary, won))

    total_matches = len(filtered)
    total_wins = sum(1 for _, _, won in filtered if won)
    total_losses = total_matches - total_wins
    win_rate = (total_wins / total_matches) if total_matches else 0.0

    round_tallies: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    opponent_tallies: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for match, summary, won in filtered:
        bucket = round_tallies[match.round_number]
        bucket[0 if won else 1] += 1

        my_team = my_team_by_match[match.id]
        match_opponents = summary.team_b if my_team == "A" else summary.team_a
        for opponent in match_opponents:
            tally = opponent_tallies[opponent.nickname]
            tally[0 if won else 1] += 1

    round_win_rates = [
        RoundWinRatePoint(
            round_number=round_number,
            wins=wins,
            losses=losses,
            win_rate=(wins / (wins + losses)) if (wins + losses) else 0.0,
        )
        for round_number, (wins, losses) in sorted(round_tallies.items())
    ]
    opponent_records = sorted(
        (
            OpponentRecord(
                nickname=nickname,
                wins=wins,
                losses=losses,
                matches=wins + losses,
                win_rate=(wins / (wins + losses)) if (wins + losses) else 0.0,
            )
            for nickname, (wins, losses) in opponent_tallies.items()
        ),
        key=lambda record: record.matches,
        reverse=True,
    )

    total_pages = max(
        1, (total_matches + _MEMBER_MATCH_RECORDS_PAGE_SIZE - 1) // _MEMBER_MATCH_RECORDS_PAGE_SIZE
    )
    start = (page - 1) * _MEMBER_MATCH_RECORDS_PAGE_SIZE
    end = start + _MEMBER_MATCH_RECORDS_PAGE_SIZE
    page_matches = [summary for _, summary, _ in filtered[start:end]]

    return MemberMatchRecordsResponse(
        matches=page_matches,
        total_matches=total_matches,
        total_wins=total_wins,
        total_losses=total_losses,
        win_rate=win_rate,
        round_win_rates=round_win_rates,
        opponent_records=opponent_records,
        page=page,
        total_pages=total_pages,
    )


async def get_member_group_history(
    session: AsyncSession,
    member_id: uuid.UUID,
    group_id: uuid.UUID,
    page: int = 1,
    *,
    nickname: str | None = None,
) -> MemberGroupHistoryResponse:
    """014-member-groups-history follow-up: `matches` is the group's own
    shared match history — EVERY completed match, regardless of who played
    in it (reuses `build_group_match_records()`, extended with a generic
    `nickname` search across either team, FR-004/FR-009) — while `my_stats`
    is this member's own performance in the group (reuses
    `build_member_match_records(group_id=...)` unfiltered, FR-005). The two
    intentionally use different queries: a group-wide match list has no
    single "my team" to filter opponent/partner/score against, so the
    nickname search here means "does this match involve this player at
    all," not "was this player my opponent." Errors: `GROUP_NOT_FOUND`,
    `GROUP_MEMBERSHIP_NEVER_HELD`."""
    group = await get_group_by_id(session, group_id)
    await verify_ever_group_member(session, group_id, member_id)

    match_records = await build_group_match_records(session, group_id, page, nickname=nickname)
    member_records = await build_member_match_records(session, member_id, group_id=group_id)

    return MemberGroupHistoryResponse(
        group_id=str(group.id),
        group_name=group.name,
        my_stats=MemberGroupStatsResponse(
            total_matches=member_records.total_matches,
            total_wins=member_records.total_wins,
            total_losses=member_records.total_losses,
            win_rate=member_records.win_rate,
            round_win_rates=member_records.round_win_rates,
            opponent_records=member_records.opponent_records,
        ),
        matches=match_records.matches,
        page=match_records.page,
        total_pages=match_records.total_pages,
    )


async def search_member(
    session: AsyncSession, user_number: str, requester_id: uuid.UUID
) -> SearchMemberResponse:
    """FR-038: case-insensitive user_number lookup. Errors: `MEMBER_NOT_FOUND`
    (also covers an unverified target account, FR-036), `CANNOT_SEARCH_SELF`
    (FR-037, checked after existence so a self-search still surfaces as its
    own distinct code rather than the generic not-found)."""
    result = await session.execute(
        select(Member).where(func.lower(Member.user_number) == user_number.lower())
    )
    target = result.scalar_one_or_none()
    if target is None or target.verification_status != "verified":
        raise ApiError("MEMBER_NOT_FOUND", status_code=404)
    if target.id == requester_id:
        raise ApiError("CANNOT_SEARCH_SELF", status_code=400)

    status = await get_friendship_status(session, requester_id, target.id)
    return SearchMemberResponse(
        member_id=str(target.id),
        nickname=target.nickname,
        user_number=target.user_number,
        friendship_status=status,
    )


async def get_my_groups(session: AsyncSession, member_id: uuid.UUID) -> MyGroupsResponse:
    """014-member-groups-history FR-001~003: every group this member
    created ∪ every group this member has EVER had a `RosterEntry` in
    (any status — active/left/kicked), deduplicated by group. Guest-joined
    participation is naturally excluded (`RosterEntry.member_id IS NULL`
    for Guest entries), no extra guard needed (FR-003).

    `member_status` reflects each group's MOST RECENT `RosterEntry` for
    this member (by `joined_at` DESC) — a member can leave and rejoin the
    same group, producing multiple historical rows (research.md #4)."""
    roster_result = await session.execute(
        select(RosterEntry.group_id, RosterEntry.status)
        .where(RosterEntry.member_id == member_id)
        .order_by(RosterEntry.joined_at.desc())
    )
    member_status_by_group: dict[uuid.UUID, str] = {}
    for group_id, status in roster_result.all():
        member_status_by_group.setdefault(group_id, status)  # first seen (newest) wins

    created_result = await session.execute(
        select(Group.id).where(Group.created_by_member_id == member_id)
    )
    created_group_ids = {row[0] for row in created_result.all()}

    all_group_ids = set(member_status_by_group) | created_group_ids
    if not all_group_ids:
        return MyGroupsResponse(groups=[])

    result = await session.execute(
        select(Group.id, Group.group_number, Group.name, Group.status)
        .where(Group.id.in_(all_group_ids))
        .order_by(Group.created_at.desc())
    )
    groups = [
        MyGroupSummary(
            group_id=str(row.id),
            group_number=row.group_number,
            name=row.name,
            status=row.status,
            is_creator=row.id in created_group_ids,
            member_status=member_status_by_group[row.id],
        )
        for row in result.all()
    ]
    return MyGroupsResponse(groups=groups)
