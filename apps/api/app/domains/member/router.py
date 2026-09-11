"""Member domain REST endpoints, per specs/006-member-friends/contracts/
auth-api.md and member-api.md."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.rate_limit import limiter
from app.core.turnstile import verify_turnstile_token
from app.domains.group.schemas import MatchRecordDetailResponse, MemberMatchRecordsResponse
from app.domains.member import security, service
from app.domains.member.models import Member
from app.domains.member.schemas import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    MemberGroupHistoryResponse,
    MemberPublicResponse,
    MyGroupsResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SearchMemberResponse,
    SetNicknameRequest,
    VerifyEmailResponse,
)

router = APIRouter(tags=["member"])


async def _to_public(session: AsyncSession, member: Member) -> MemberPublicResponse:
    """020-resend-verification-email: needs `session` (unlike the pre-020
    sync version) to compute `resend_verification_available_at` — verified
    members short-circuit to `None` without a query inside
    `get_resend_verification_available_at()`."""
    return MemberPublicResponse(
        member_id=str(member.id),
        email=member.email,
        nickname=member.nickname,
        user_number=member.user_number,
        verification_status=member.verification_status,
        resend_verification_available_at=(
            await service.get_resend_verification_available_at(session, member)
        ),
    )


@router.post("/auth/register", response_model=RegisterResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegisterResponse:
    """FR-001: Turnstile MUST be verified before the account is created.
    Errors: `CAPTCHA_INVALID`, `CAPTCHA_EXPIRED`, `EMAIL_ALREADY_REGISTERED`."""
    await verify_turnstile_token(payload.turnstile_token)
    member = await service.register(session, payload.email, payload.password)
    return RegisterResponse(
        member_id=str(member.id), email=member.email, user_number=member.user_number
    )


@router.get("/auth/verify-email/{token}", response_model=VerifyEmailResponse)
async def verify_email(
    token: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VerifyEmailResponse:
    """Errors: `VERIFICATION_TOKEN_INVALID`, `VERIFICATION_TOKEN_EXPIRED`,
    `VERIFICATION_TOKEN_ALREADY_USED`."""
    await service.verify_email(session, token)
    return VerifyEmailResponse(verified=True)


@router.post("/auth/resend-verification", response_model=ResendVerificationResponse)
async def resend_verification(
    member: Annotated[Member, Depends(security.require_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResendVerificationResponse:
    """020-resend-verification-email (FR-004/FR-009): requires login;
    5-minute per-account cooldown between manual resends — MUST NOT count
    the verification email sent automatically at registration, so a
    member's first-ever manual resend always succeeds regardless of how
    recently they registered (research.md #5). Errors:
    `MEMBER_TOKEN_INVALID`, `ALREADY_VERIFIED`, `RESEND_RATE_LIMITED`."""
    available_at = await service.resend_verification(session, member)
    return ResendVerificationResponse(sent=True, available_at=available_at)


@router.get("/members/me", response_model=MemberPublicResponse)
async def get_me(
    member: Annotated[Member, Depends(security.require_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberPublicResponse:
    """020-resend-verification-email (FR-009): response includes
    `resend_verification_available_at`, letting the member home page show
    the correct "重新寄送驗證信" cooldown state even after a page reload."""
    return await _to_public(session, member)


@router.patch("/members/me/nickname", response_model=MemberPublicResponse)
async def set_nickname(
    payload: SetNicknameRequest,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberPublicResponse:
    """Errors: `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`, `VALIDATION_ERROR`.
    `require_verified_member` means the caller is always verified here, so
    `resend_verification_available_at` in the response is always `null`
    (020-resend-verification-email)."""
    updated = await service.set_nickname(session, member, payload.nickname)
    return await _to_public(session, updated)


@router.patch("/members/me/password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChangePasswordResponse:
    """Errors: `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`,
    `CURRENT_PASSWORD_INCORRECT`."""
    _updated, access_token, refresh_token = await service.change_password(
        session, member, payload.current_password, payload.new_password
    )
    return ChangePasswordResponse(
        changed=True, access_token=access_token, refresh_token=refresh_token
    )


@router.post("/auth/login", response_model=LoginResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,  # noqa: ARG001 - required by slowapi
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    """FR-002a: per-IP rate limit, no account lockout. `member` in the
    response shares `MemberPublicResponse` with `GET /members/me`, so it
    also carries `resend_verification_available_at`
    (020-resend-verification-email FR-009). Errors: `INVALID_CREDENTIALS`."""
    member, access_token, refresh_token = await service.login(
        session, payload.email, payload.password
    )
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        member=await _to_public(session, member),
    )


@router.post("/auth/refresh", response_model=RefreshResponse)
async def refresh(
    payload: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RefreshResponse:
    """Errors: `REFRESH_TOKEN_INVALID`."""
    access_token = await security.refresh_access_token(session, payload.refresh_token)
    return RefreshResponse(access_token=access_token)


@router.post("/auth/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("20/minute")
async def forgot_password(
    request: Request,  # noqa: ARG001 - required by slowapi
    payload: ForgotPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ForgotPasswordResponse:
    """Always returns the same response regardless of whether the Email is
    registered (2026-09-01 clarification — avoids account enumeration)."""
    await service.forgot_password(session, payload.email)
    return ForgotPasswordResponse(sent=True)


@router.post("/auth/reset-password/{token}", response_model=ResetPasswordResponse)
async def reset_password(
    token: uuid.UUID,
    payload: ResetPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResetPasswordResponse:
    """Errors: `RESET_TOKEN_INVALID`, `RESET_TOKEN_EXPIRED`,
    `RESET_TOKEN_ALREADY_USED`."""
    await service.reset_password(session, token, payload.new_password)
    return ResetPasswordResponse(reset=True)


@router.get("/members/search", response_model=SearchMemberResponse)
@limiter.limit("20/minute")
async def search_member(
    request: Request,  # noqa: ARG001 - required by slowapi
    user_number: str,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SearchMemberResponse:
    """FR-020: per-IP rate limit, mirroring `/groups/reauth`. Errors:
    `MEMBER_NOT_FOUND`, `CANNOT_SEARCH_SELF`."""
    return await service.search_member(session, user_number, member.id)


@router.get("/members/me/groups", response_model=MyGroupsResponse)
async def get_my_groups(
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MyGroupsResponse:
    """014-member-groups-history FR-001~003: every group this member
    created ∪ every group this member has ever had a roster entry in (any
    status). Still backs the "忘記管理 PIN 碼" recovery list for the
    `is_creator=true` rows."""
    return await service.get_my_groups(session, member.id)


@router.get(
    "/members/me/groups/{group_id}/history", response_model=MemberGroupHistoryResponse
)
async def get_member_group_history(
    group_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    nickname: Annotated[str | None, Query(max_length=20)] = None,
) -> MemberGroupHistoryResponse:
    """`matches` is the group's own shared match history — every completed
    match, regardless of who played in it, optionally searched by whether
    any participant (either team) has a nickname containing `nickname`.
    `my_stats` is this member's own performance in the group, always
    unfiltered by that search. `require_member` (not
    `require_verified_member`) matches the sibling
    `/members/me/match-records` endpoint's existing looser tier, since
    email-verification status is unrelated to viewing match history.

    019-group-final-standings (FR-001~FR-012) adds `final_standings`: the
    group's whole final team ranking, covering every ever-participant
    (active/left/kicked, member or guest, multi-stint members merged),
    also unaffected by `nickname`. Access is the same `verify_ever_group_
    member` check used for `matches`/`my_stats` above — unlike the live
    `GET /groups/{group_id}/standings` tab, this endpoint does NOT require
    the caller to currently hold an active roster entry (FR-010).

    Errors: `MEMBER_TOKEN_INVALID`, `GROUP_NOT_FOUND`,
    `GROUP_MEMBERSHIP_NEVER_HELD`."""
    return await service.get_member_group_history(
        session, member.id, group_id, page, nickname=nickname
    )


@router.get("/members/me/match-records", response_model=MemberMatchRecordsResponse)
async def get_member_match_records(
    member: Annotated[Member, Depends(security.require_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    opponent1: Annotated[str | None, Query(max_length=20)] = None,
    opponent2: Annotated[str | None, Query(max_length=20)] = None,
    partner: Annotated[str | None, Query(max_length=20)] = None,
    result: Annotated[Literal["win", "loss"] | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    round_from: Annotated[int | None, Query(ge=1)] = None,
    round_to: Annotated[int | None, Query(ge=1)] = None,
    self_score_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    self_score: Annotated[int | None, Query(ge=0)] = None,
    opponent_score_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    opponent_score: Annotated[int | None, Query(ge=0)] = None,
    match_mode: Annotated[Literal["singles", "doubles"] | None, Query()] = None,
) -> MemberMatchRecordsResponse:
    """005-member-view US5 (FR-017~020): 會員跨團對戰紀錄與彙總統計；未鎖定
    於信箱驗證（比照 `GET /members/me` 之既有寬鬆基準）。`opponent1`/
    `opponent2` 分開篩選兩位對手暱稱（子字串、不分大小寫）——雙打時兩個
    欄位須各自對應到不同的對手，不能同一人滿足兩欄。`partner` 篩選隊友
    暱稱，僅一個欄位——雙打隊伍除自己外只有一位隊友，不像對手一次面對兩
    人。`self_score_cmp`+`self_score`、`opponent_score_cmp`+
    `opponent_score` 各自篩選自己/對手的比分（與指定數值比較，而非兩者互
    比）。`result`/`date_from`/`date_to`/`round_from`/`round_to` 篩選勝負、
    日期、輪次區間；`match_mode` 篩選單打/雙打（比賽所屬團的賽制）——
    所有彙總統計（場次/勝敗/勝率/各輪趨勢/對戰對象排行）
    皆以篩選後的完整結果集計算，而非僅本頁。Errors: `MEMBER_TOKEN_INVALID`。
    """
    return await service.build_member_match_records(
        session,
        member.id,
        page,
        opponents=[name for name in (opponent1, opponent2) if name],
        partners=[partner] if partner else [],
        result=result,
        date_from=date_from,
        date_to=date_to,
        round_from=round_from,
        round_to=round_to,
        self_score_cmp=self_score_cmp,
        self_score=self_score,
        opponent_score_cmp=opponent_score_cmp,
        opponent_score=opponent_score,
        match_mode=match_mode,
    )


@router.get("/members/me/match-records/{match_id}", response_model=MatchRecordDetailResponse)
async def get_member_match_record_detail(
    match_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MatchRecordDetailResponse:
    """016-match-score-timeline US1/US2/US3 (FR-001~008): 會員跨團對戰紀錄、
    以及「我的團→歷史」這兩個清單點進單場比賽的詳情——兩者皆已登入會員
    視角，共用同一支端點（research.md #1）。`require_member`（不要求信箱
    已驗證，比照既有 `/members/me/match-records`）。Errors:
    `MEMBER_TOKEN_INVALID`、`MATCH_NOT_FOUND`、`GROUP_MEMBERSHIP_NEVER_HELD`。"""
    return await service.get_member_match_record_detail(session, member.id, match_id)
