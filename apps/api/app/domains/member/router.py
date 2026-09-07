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
from app.domains.group.schemas import MemberMatchRecordsResponse
from app.domains.member import security, service
from app.domains.member.models import Member
from app.domains.member.schemas import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
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


def _to_public(member: Member) -> MemberPublicResponse:
    return MemberPublicResponse(
        member_id=str(member.id),
        email=member.email,
        nickname=member.nickname,
        user_number=member.user_number,
        verification_status=member.verification_status,
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
    """FR-011: requires login; 60s per-account cooldown. Errors:
    `MEMBER_TOKEN_INVALID`, `ALREADY_VERIFIED`, `RESEND_RATE_LIMITED`."""
    await service.resend_verification(session, member)
    return ResendVerificationResponse(sent=True)


@router.get("/members/me", response_model=MemberPublicResponse)
async def get_me(
    member: Annotated[Member, Depends(security.require_member)],
) -> MemberPublicResponse:
    return _to_public(member)


@router.patch("/members/me/nickname", response_model=MemberPublicResponse)
async def set_nickname(
    payload: SetNicknameRequest,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberPublicResponse:
    """Errors: `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`, `VALIDATION_ERROR`."""
    updated = await service.set_nickname(session, member, payload.nickname)
    return _to_public(updated)


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
    """FR-002a: per-IP rate limit, no account lockout. Errors:
    `INVALID_CREDENTIALS`."""
    member, access_token, refresh_token = await service.login(
        session, payload.email, payload.password
    )
    return LoginResponse(
        access_token=access_token, refresh_token=refresh_token, member=_to_public(member)
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
    """FR-028/029: every group this member created (any status), for the
    "忘記管理 PIN 碼" recovery list."""
    return await service.get_my_groups(session, member.id)


@router.get("/members/me/match-records", response_model=MemberMatchRecordsResponse)
async def get_member_match_records(
    member: Annotated[Member, Depends(security.require_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    q: Annotated[str | None, Query(max_length=20)] = None,
    result: Annotated[Literal["win", "loss"] | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    round_from: Annotated[int | None, Query(ge=1)] = None,
    round_to: Annotated[int | None, Query(ge=1)] = None,
    score_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
) -> MemberMatchRecordsResponse:
    """005-member-view US5 (FR-017~020): 會員跨團對戰紀錄與彙總統計；未鎖定
    於信箱驗證（比照 `GET /members/me` 之既有寬鬆基準）。`q` 篩選對手/隊友暱
    稱（子字串、不分大小寫），`result`/`date_from`/`date_to`/`round_from`/
    `round_to`/`score_cmp` 篩選勝負、日期、輪次、比分區間 —— 所有彙總統計
    （場次/勝敗/勝率/各輪趨勢/對戰對象排行）皆以篩選後的完整結果集計算，
    而非僅本頁。Errors: `MEMBER_TOKEN_INVALID`。"""
    return await service.build_member_match_records(
        session,
        member.id,
        page,
        opponent_or_partner=q,
        result=result,
        date_from=date_from,
        date_to=date_to,
        round_from=round_from,
        round_to=round_to,
        score_cmp=score_cmp,
    )
