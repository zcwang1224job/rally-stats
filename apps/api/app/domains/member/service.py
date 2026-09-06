"""Member domain service layer: auth, verification, profile, and search.
Per specs/006-member-friends/plan.md."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import send_email
from app.core.errors import ApiError
from app.domains.friend.service import get_friendship_status
from app.domains.group.models import Group
from app.domains.group.schemas import MemberMatchRecordsResponse, MemberMatchRecordSummary
from app.domains.group.service import _completed_matches_query
from app.domains.member.models import EmailVerificationToken, Member, PasswordResetToken
from app.domains.member.schemas import MyGroupsResponse, MyGroupSummary, SearchMemberResponse
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
    session: AsyncSession, matches: list[Match]
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
                group_id=str(match.group_id),
                group_name=group_name_by_id.get(match.group_id, ""),
            )
        )
    return summaries


async def build_member_match_records(
    session: AsyncSession, member_id: uuid.UUID, page: int = 1
) -> MemberMatchRecordsResponse:
    """005-member-view US5 (FR-017~020): a member's completed matches across
    every group they've ever joined as a Member (never as a Guest —
    research.md #9, `roster_entries.member_id IS NULL` for Guest entries
    naturally excludes them, no extra guard needed), plus aggregate
    win/loss/win-rate stats over the *entire* result set (not just the
    current page — plan.md Scale/Scope: a single member's group count is
    small enough that this is cheap)."""
    participant_exists = (
        select(MatchParticipant.id)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(MatchParticipant.match_id == Match.id, RosterEntry.member_id == member_id)
        .exists()
    )
    base_query = _completed_matches_query().where(participant_exists)

    all_matches_result = await session.execute(
        base_query.order_by(Match.round_number.desc(), Match.ended_at.desc())
    )
    all_matches = list(all_matches_result.scalars())
    total_matches = len(all_matches)
    total_pages = max(
        1, (total_matches + _MEMBER_MATCH_RECORDS_PAGE_SIZE - 1) // _MEMBER_MATCH_RECORDS_PAGE_SIZE
    )

    my_team_by_match: dict[uuid.UUID, str] = {}
    if all_matches:
        match_ids = [match.id for match in all_matches]
        participation_result = await session.execute(
            select(MatchParticipant.match_id, MatchParticipant.team)
            .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
            .where(MatchParticipant.match_id.in_(match_ids), RosterEntry.member_id == member_id)
        )
        my_team_by_match = {row[0]: row[1] for row in participation_result.all()}

    total_wins = sum(
        1 for match in all_matches if my_team_by_match.get(match.id) == match.winner_team
    )
    total_losses = total_matches - total_wins
    win_rate = (total_wins / total_matches) if total_matches else 0.0

    start = (page - 1) * _MEMBER_MATCH_RECORDS_PAGE_SIZE
    page_matches = all_matches[start : start + _MEMBER_MATCH_RECORDS_PAGE_SIZE]
    summaries = await _build_member_match_record_summaries(session, page_matches)

    return MemberMatchRecordsResponse(
        matches=summaries,
        total_matches=total_matches,
        total_wins=total_wins,
        total_losses=total_losses,
        win_rate=win_rate,
        page=page,
        total_pages=total_pages,
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
    """FR-028/029: every group this member created, regardless of status —
    anonymously-created groups (`created_by_member_id IS NULL`) are excluded
    by the `WHERE` clause itself, no extra guard needed."""
    result = await session.execute(
        select(Group.id, Group.group_number, Group.name, Group.status)
        .where(Group.created_by_member_id == member_id)
        .order_by(Group.created_at.desc())
    )
    groups = [
        MyGroupSummary(
            group_id=str(row.id), group_number=row.group_number, name=row.name, status=row.status
        )
        for row in result.all()
    ]
    return MyGroupsResponse(groups=groups)
