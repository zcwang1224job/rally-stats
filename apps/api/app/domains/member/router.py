"""Member domain REST endpoints, per specs/006-member-friends/contracts/
auth-api.md and member-api.md."""

import uuid
from typing import Annotated, Literal, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ApiError
from app.core.rate_limit import limiter
from app.core.turnstile import verify_turnstile_token
from app.domains.group.schemas import MatchRecordDetailResponse, MemberMatchRecordsResponse
from app.domains.member import custom_sports, security, service
from app.domains.member.models import Member
from app.domains.member.oauth_providers import Provider
from app.domains.member.player_identity import parse_player_key
from app.domains.member.schemas import (
    AddEmailRequest,
    AddEmailResponse,
    BenchmarkGroupsResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    DashboardSectionsResponse,
    DeleteAccountRequest,
    DeleteAccountResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GroupBenchmarkResponse,
    LoginRecordsResponse,
    LoginRequest,
    LoginResponse,
    MatchComparisonResponse,
    MemberActivitiesResponse,
    MemberGroupHistoryResponse,
    MemberMatchDashboardResponse,
    MemberPublicResponse,
    MyGroupsResponse,
    OAuthStartResponse,
    PrivacySettingsRequest,
    PrivacySettingsResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SearchMemberResponse,
    SetLanguagePreferenceRequest,
    SetNicknameRequest,
    SupportedLanguagesResponse,
    VerifyEmailResponse,
)
from app.domains.member.sport_filter import parse_sport_filter
from app.sports.router import CustomSportView, custom_sport_view

router = APIRouter(tags=["member"])

_OAUTH_PROVIDERS: tuple[Provider, ...] = ("google", "line")


def _require_valid_provider(provider: str) -> Provider:
    if provider not in _OAUTH_PROVIDERS:
        raise ApiError("OAUTH_PROVIDER_UNKNOWN", status_code=404)
    return cast("Provider", provider)


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
        language_preference=member.language_preference,
        allow_search=member.allow_search,
        share_match_records_with_friends=member.share_match_records_with_friends,
        allow_friend_invite_from_match_pages=member.allow_friend_invite_from_match_pages,
        linked_oauth_providers=await service.get_linked_oauth_providers(session, member.id),
        has_password=member.password_hash is not None,
    )


@router.post("/auth/register", response_model=RegisterResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegisterResponse:
    """FR-001: Turnstile MUST be verified before the account is created.
    Errors: `CAPTCHA_INVALID`, `CAPTCHA_EXPIRED`, `EMAIL_ALREADY_REGISTERED`."""
    await verify_turnstile_token(payload.turnstile_token)
    member = await service.register(session, payload.email, payload.password, payload.language)
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


@router.post("/members/me/delete", response_model=DeleteAccountResponse)
async def delete_account(
    payload: DeleteAccountRequest,
    member: Annotated[Member, Depends(security.require_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeleteAccountResponse:
    """025-delete-account FR-008: deliberately `require_member`, not
    `require_verified_member` — an unverified member can still delete their
    own account (Edge Cases). No target-member-id parameter exists on this
    endpoint at all, so there is no code path for deleting anyone else's
    account. Errors: `MEMBER_TOKEN_INVALID`, `CURRENT_PASSWORD_INCORRECT`."""
    await service.delete_account(session, member, payload.current_password)
    return DeleteAccountResponse(deleted=True)


@router.post("/auth/login", response_model=LoginResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    """FR-002a: per-IP rate limit, no account lockout. `member` in the
    response shares `MemberPublicResponse` with `GET /members/me`, so it
    also carries `resend_verification_available_at`
    (020-resend-verification-email FR-009). 022-member-personal-settings
    FR-007: `request`'s User-Agent header backs the new login record's
    device category — no longer unused, so its `noqa: ARG001` is dropped.
    Errors: `INVALID_CREDENTIALS`."""
    member, access_token, refresh_token = await service.login(
        session,
        payload.email,
        payload.password,
        user_agent=request.headers.get("user-agent"),
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


def _oauth_callback_redirect_url(result: service.OAuthCallbackResult) -> str:
    """contracts/oauth-login-api.md's callback redirect-target table."""
    settings = get_settings()
    if result.intent == "login":
        base = f"{settings.frontend_base_url}/auth/oauth-callback"
        if result.status == "success":
            params = {
                "status": "success",
                "access_token": result.access_token or "",
                "refresh_token": result.refresh_token or "",
                "is_new_member": "true" if result.is_new_member else "false",
            }
            if result.bound_group_id:
                # 028-guest-stats-binding research.md #3: lets the frontend
                # land back on the guest's live/summary screen instead of
                # the default post-login destination.
                params["bound_group_id"] = result.bound_group_id
        elif result.status == "cancelled":
            params = {"status": "cancelled"}
        else:
            params = {"status": "error", "code": result.error_code or ""}
        return f"{base}#{urlencode(params)}"

    base = f"{settings.frontend_base_url}/settings"
    if result.status == "success":
        return f"{base}?{urlencode({'oauth_link': 'success', 'provider': result.provider or ''})}"
    if result.status == "cancelled":
        return f"{base}?oauth_link=cancelled"
    return f"{base}?{urlencode({'oauth_link': 'error', 'code': result.error_code or ''})}"


@router.get("/auth/oauth/{provider}/start", response_model=OAuthStartResponse)
@limiter.limit("20/minute")
async def start_oauth(
    request: Request,  # noqa: ARG001 - required by slowapi
    provider: str,
    member: Annotated[Member | None, Depends(security.optional_member)],
    intent: Literal["login", "link"] = "login",
    bind_guest_token: str | None = None,
) -> OAuthStartResponse:
    """contracts/oauth-login-api.md `GET /auth/oauth/{provider}/start`.
    `intent=login` (US1/US2) is public; `intent=link` (US3) requires a
    verified member session. `bind_guest_token`
    (028-guest-stats-binding research.md #3) is only valid with
    `intent=login` — a guest binding their roster entry via a new/existing
    OAuth-authenticated account. Errors: `OAUTH_PROVIDER_UNKNOWN`,
    `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`, `INVALID_REQUEST`."""
    valid_provider = _require_valid_provider(provider)
    member_id: str | None = None
    if intent == "link":
        if bind_guest_token is not None:
            raise ApiError("INVALID_REQUEST", status_code=400)
        if member is None:
            raise ApiError("MEMBER_TOKEN_INVALID", status_code=401)
        if member.verification_status != "verified":
            raise ApiError("EMAIL_NOT_VERIFIED", status_code=403)
        member_id = str(member.id)
    authorize_url = await service.start_oauth_flow(
        valid_provider, intent, member_id, bind_guest_token
    )
    return OAuthStartResponse(authorize_url=authorize_url)


@router.get("/auth/oauth/{provider}/callback")
@limiter.limit("20/minute")
async def oauth_callback(
    request: Request,
    provider: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """contracts/oauth-login-api.md `GET /auth/oauth/{provider}/callback`.
    Public — the browser lands here fresh from Google/LINE's own redirect,
    with no `Authorization` header. Always a 302, never a JSON body (the
    browser is mid-navigation, not an API caller). bugfix/oauth-login-record:
    `request`'s User-Agent header backs the new login record's device
    category, same as `/auth/login` — no longer unused, so its
    `noqa: ARG001` is dropped."""
    valid_provider = _require_valid_provider(provider)
    result = await service.complete_oauth_callback(
        session,
        valid_provider,
        code=code,
        state=state,
        error=error,
        user_agent=request.headers.get("user-agent"),
    )
    return RedirectResponse(_oauth_callback_redirect_url(result), status_code=302)


@router.delete("/members/me/oauth-identities/{provider}", status_code=204)
async def unlink_oauth_identity(
    provider: str,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """contracts/account-recovery-api.md. Errors: `MEMBER_TOKEN_INVALID`,
    `EMAIL_NOT_VERIFIED`, `OAUTH_PROVIDER_UNKNOWN`,
    `OAUTH_IDENTITY_NOT_LINKED`, `LAST_LOGIN_METHOD`."""
    valid_provider = _require_valid_provider(provider)
    await service.unlink_oauth_identity(session, member, valid_provider)


@router.post("/members/me/email", response_model=AddEmailResponse, status_code=202)
async def add_email(
    payload: AddEmailRequest,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AddEmailResponse:
    """contracts/account-recovery-api.md (FR-013). Errors:
    `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`, `EMAIL_ALREADY_SET`,
    `EMAIL_ALREADY_REGISTERED`."""
    await service.add_email(session, member, payload.email)
    return AddEmailResponse(verification_email_sent=True)


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


@router.get("/members/me/benchmark-groups", response_model=BenchmarkGroupsResponse)
async def get_benchmark_groups(
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BenchmarkGroupsResponse:
    """036-match-insights-benchmarks US3 (FR-027): the groups this member
    can compare within — every group they ever held a roster row in, whatever
    its or their status — with their completed-match count in each, most
    first. Errors: `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`."""
    return await service.list_benchmark_groups(session, member.id)


@router.get("/members/me/group-benchmark", response_model=GroupBenchmarkResponse)
async def get_group_benchmark(
    group_id: Annotated[uuid.UUID, Query()],
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GroupBenchmarkResponse:
    """036-match-insights-benchmarks US3: per dashboard metric, the group's
    average, the number of players behind it, and this member's rank — always
    over ALL of the group's completed matches; this endpoint takes no filter
    (FR-028, FR-032), and any other query parameter is ignored.

    The response carries nothing about any other player (FR-032): see
    `GroupBenchmarkMetric`. Authorization is 014's "ever a formal member",
    checked on every request (FR-038). Errors: `MEMBER_TOKEN_INVALID`,
    `EMAIL_NOT_VERIFIED`, `GROUP_MEMBERSHIP_NEVER_HELD` (403 — also for a
    group that does not exist)."""
    return await service.build_group_benchmark(session, member.id, group_id)


@router.get("/members/me/groups", response_model=MyGroupsResponse)
async def get_my_groups(
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    name: Annotated[str | None, Query(max_length=30)] = None,
    group_number: Annotated[str | None, Query(max_length=20)] = None,
    role: Annotated[Literal["creator", "member"] | None, Query()] = None,
    created_from: Annotated[AwareDatetime | None, Query()] = None,
    created_before: Annotated[AwareDatetime | None, Query()] = None,
    disbanded_from: Annotated[AwareDatetime | None, Query()] = None,
    disbanded_before: Annotated[AwareDatetime | None, Query()] = None,
    match_count_min: Annotated[int | None, Query(ge=0)] = None,
    match_count_max: Annotated[int | None, Query(ge=0)] = None,
    group_id: Annotated[uuid.UUID | None, Query()] = None,
    sport: Annotated[str | None, Query(max_length=60)] = None,
) -> MyGroupsResponse:
    """014-member-groups-history FR-001~003: every group this member
    created ∪ every group this member has ever had a roster entry in (any
    status). Still backs the "忘記管理 PIN 碼" recovery list for the
    `is_creator=true` rows.

    Paginated (`page`, system default page size) and filterable: `name`/
    `group_number` are case-insensitive substring matches, `role` is
    whether this member created the group, `group_id` pins one exact group
    (used by the group-history page, which needs that one row whatever
    page it would land on).

    `created_from`/`created_before` and `disbanded_from`/`disbanded_before`
    are half-open ranges of INSTANTS (`from` <= t < `before`), and must
    carry a UTC offset (a naive value is a 422): the client converts the
    viewer's local calendar day into instants, so the filter agrees with
    the local times the list displays — unlike a bare `date`, which would
    be compared against the UTC date. A `disbanded_*` bound also drops
    every group that has no `disbanded_at`.

    `match_count_min`/`match_count_max` filter (both ends inclusive) on each
    row's `match_count`: the completed matches this member played there."""
    return await service.get_my_groups(
        session,
        member.id,
        page=page,
        name=name,
        group_number=group_number,
        role=role,
        created_from=created_from,
        created_before=created_before,
        disbanded_from=disbanded_from,
        disbanded_before=disbanded_before,
        match_count_min=match_count_min,
        match_count_max=match_count_max,
        group_id=group_id,
        sport=sport,
    )


@router.get(
    "/members/me/groups/{group_id}/history", response_model=MemberGroupHistoryResponse
)
async def get_member_group_history(
    group_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    nickname: Annotated[str | None, Query(max_length=20)] = None,
    round_from: Annotated[int | None, Query(ge=1)] = None,
    round_to: Annotated[int | None, Query(ge=1)] = None,
    group1_player1: Annotated[str | None, Query(max_length=20)] = None,
    group1_player2: Annotated[str | None, Query(max_length=20)] = None,
    group2_player1: Annotated[str | None, Query(max_length=20)] = None,
    group2_player2: Annotated[str | None, Query(max_length=20)] = None,
    score_a_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    score_a: Annotated[int | None, Query(ge=0)] = None,
    score_b_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    score_b: Annotated[int | None, Query(ge=0)] = None,
) -> MemberGroupHistoryResponse:
    """`matches` is the group's own shared match history — every completed
    match, regardless of who played in it, optionally narrowed by whether
    any participant (either team) has a nickname containing `nickname`,
    and/or by `round_from`/`round_to` (round number) — same "does this
    match involve/fall in this range at all" scope as `nickname`.

    `group1_player1`/`group1_player2` and `group2_player1`/
    `group2_player2` (advanced filters, third round) search for a "this
    group of people vs. that group of people" matchup — NOT which literal
    on-court team (A or B) anyone ended up on, which the viewer has no way
    to know and no reason to care about. Filling both fields for one group
    requires TWO DISTINCT players who were together on the SAME side to
    match, one per field (same distinct-matching as `opponent1`/
    `opponent2` on the sibling `/members/me/match-records` endpoint) —
    but unlike that endpoint, either literal side (A or B) satisfies
    "group1", so long as the other group is on the other side. Leaving one
    group's fields empty degenerates to "these people were on the same
    side together," unconstrained by who else was on the opposing side.
    `score_a_cmp`+`score_a`/`score_b_cmp`+`score_b`, by contrast, DO stay
    tied to each match's literal A/B sides — there is no "self"/
    "opponent" concept for a plain numeric score comparison.

    `my_stats` is this member's own performance in the group, always
    unfiltered by any of the above. `require_verified_member`, like the
    sibling `/members/me/match-records` endpoint: constitution IV locks
    match records until the e-mail is verified. (Both used the looser
    `require_member` until this was corrected — see that endpoint.)

    019-group-final-standings (FR-001~FR-012) adds `final_standings`: the
    group's whole final team ranking, covering every ever-participant
    (active/left/kicked, member or guest, multi-stint members merged),
    also unaffected by any filter above. Access is the same `verify_ever_
    group_member` check used for `matches`/`my_stats` above — unlike the
    live `GET /groups/{group_id}/standings` tab, this endpoint does NOT
    require the caller to currently hold an active roster entry (FR-010).

    Errors: `MEMBER_TOKEN_INVALID`, `GROUP_NOT_FOUND`,
    `GROUP_MEMBERSHIP_NEVER_HELD`."""
    return await service.get_member_group_history(
        session,
        member.id,
        group_id,
        page,
        nickname=nickname,
        round_from=round_from,
        round_to=round_to,
        group1_names=[name for name in (group1_player1, group1_player2) if name],
        group2_names=[name for name in (group2_player1, group2_player2) if name],
        score_a_cmp=score_a_cmp,
        score_a=score_a,
        score_b_cmp=score_b_cmp,
        score_b=score_b,
    )


@router.get("/members/me/match-records", response_model=MemberMatchRecordsResponse)
async def get_member_match_records(
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    opponent1: Annotated[str | None, Query(max_length=20)] = None,
    opponent2: Annotated[str | None, Query(max_length=20)] = None,
    partner: Annotated[str | None, Query(max_length=20)] = None,
    result: Annotated[Literal["win", "loss"] | None, Query()] = None,
    ended_from: Annotated[AwareDatetime | None, Query()] = None,
    ended_before: Annotated[AwareDatetime | None, Query()] = None,
    round_from: Annotated[int | None, Query(ge=1)] = None,
    round_to: Annotated[int | None, Query(ge=1)] = None,
    self_score_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    self_score: Annotated[int | None, Query(ge=0)] = None,
    opponent_score_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    opponent_score: Annotated[int | None, Query(ge=0)] = None,
    match_mode: Annotated[Literal["singles", "doubles"] | None, Query()] = None,
    partner_key: Annotated[str | None, Query(max_length=40)] = None,
    opponent_key: Annotated[str | None, Query(max_length=40)] = None,
    sport: Annotated[str | None, Query(max_length=40)] = None,
) -> MemberMatchRecordsResponse:
    """005-member-view US5 (FR-017~020): 會員跨團對戰紀錄與彙總統計。
    `require_verified_member`：憲章原則 IV 明定對戰紀錄在信箱驗證前 MUST
    鎖定。（005 原本比照 `GET /members/me` 用了較寬鬆的 `require_member`，
    那是與憲章不符的偏離，已更正；`GET /members/me`、重寄驗證信與刪除帳號
    仍維持寬鬆——未驗證的會員必須能用到它們。Google／LINE 登入的帳號建立時
    即為 verified，即使沒有信箱也不受影響。）`opponent1`/
    `opponent2` 分開篩選兩位對手暱稱（子字串、不分大小寫）——雙打時兩個
    欄位須各自對應到不同的對手，不能同一人滿足兩欄。`partner` 篩選隊友
    暱稱，僅一個欄位——雙打隊伍除自己外只有一位隊友，不像對手一次面對兩
    人。`self_score_cmp`+`self_score`、`opponent_score_cmp`+
    `opponent_score` 各自篩選自己/對手的比分（與指定數值比較，而非兩者互
    比）。`result`/`round_from`/`round_to` 篩選勝負、輪次區間；
    `ended_from`/`ended_before` 篩選比賽結束時間，是「時間點」的半開區間
    （`ended_from` ≤ `ended_at` < `ended_before`）且必須帶 UTC offset（否則
    422）——由前端把瀏覽者當地的某一天換成時間點送來，篩選才會與畫面上以
    當地時區顯示的時間一致（原本的 `date_from`/`date_to` 比的是 UTC 日期，
    台北早上 8 點前結束的比賽會被算到前一天）；
    `match_mode` 篩選單打/雙打（比賽所屬團的賽制）——
    所有彙總統計（場次/勝敗/勝率/各輪趨勢/對戰對象排行）
    皆以篩選後的完整結果集計算，而非僅本頁。Errors: `MEMBER_TOKEN_INVALID`、
    `EMAIL_NOT_VERIFIED`。
    """
    return await service.build_member_match_records(
        session,
        member.id,
        page,
        opponents=[name for name in (opponent1, opponent2) if name],
        partners=[partner] if partner else [],
        result=result,
        ended_from=ended_from,
        ended_before=ended_before,
        round_from=round_from,
        round_to=round_to,
        self_score_cmp=self_score_cmp,
        self_score=self_score,
        opponent_score_cmp=opponent_score_cmp,
        opponent_score=opponent_score,
        match_mode=match_mode,
        partner_key=_checked_player_key(partner_key),
        opponent_key=_checked_player_key(opponent_key),
        sport=parse_sport_filter(sport),
    )


@router.get("/members/me/match-records/{match_id}", response_model=MatchRecordDetailResponse)
async def get_member_match_record_detail(
    match_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MatchRecordDetailResponse:
    """016-match-score-timeline US1/US2/US3 (FR-001~008): 會員跨團對戰紀錄、
    以及「我的團→歷史」這兩個清單點進單場比賽的詳情——兩者皆已登入會員
    視角，共用同一支端點（research.md #1）。`require_verified_member`，
    與 `/members/me/match-records` 相同（憲章原則 IV）。Errors:
    `MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`、`MATCH_NOT_FOUND`、
    `GROUP_MEMBERSHIP_NEVER_HELD`。"""
    return await service.get_member_match_record_detail(session, member.id, match_id)


def _checked_player_key(value: str | None) -> str | None:
    """036 US2: `partner_key` / `opponent_key` are `m:<uuid>` / `r:<uuid>`.
    Anything else is a client bug, not an empty result. Errors:
    `INVALID_PLAYER_KEY` (422)."""
    if value is None:
        return None
    try:
        parse_player_key(value)
    except ValueError as error:
        raise ApiError("INVALID_PLAYER_KEY", status_code=422) from error
    return value


def match_filters_query(
    opponent1: Annotated[str | None, Query(max_length=20)] = None,
    opponent2: Annotated[str | None, Query(max_length=20)] = None,
    partner: Annotated[str | None, Query(max_length=20)] = None,
    result: Annotated[Literal["win", "loss"] | None, Query()] = None,
    ended_from: Annotated[AwareDatetime | None, Query()] = None,
    ended_before: Annotated[AwareDatetime | None, Query()] = None,
    round_from: Annotated[int | None, Query(ge=1)] = None,
    round_to: Annotated[int | None, Query(ge=1)] = None,
    self_score_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    self_score: Annotated[int | None, Query(ge=0)] = None,
    opponent_score_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    opponent_score: Annotated[int | None, Query(ge=0)] = None,
    match_mode: Annotated[Literal["singles", "doubles"] | None, Query()] = None,
    partner_key: Annotated[str | None, Query(max_length=40)] = None,
    opponent_key: Annotated[str | None, Query(max_length=40)] = None,
    sport: Annotated[str | None, Query(max_length=40)] = None,
) -> service.MemberMatchFilters:
    """034-clutch-points-player-dashboard: the 13 filter query parameters of
    `/members/me/match-records` — same names, same validation, no `page` —
    as one dependency. (`opponent1`/`opponent2` fold into `opponents`, hence
    12 fields on `MemberMatchFilters`.) The two dashboard endpoints take
    this instead of spelling the list out a fifth and sixth time."""
    return service.MemberMatchFilters(
        opponents=tuple(name for name in (opponent1, opponent2) if name),
        partners=(partner,) if partner else (),
        result=result,
        ended_from=ended_from,
        ended_before=ended_before,
        round_from=round_from,
        round_to=round_to,
        self_score_cmp=self_score_cmp,
        self_score=self_score,
        opponent_score_cmp=opponent_score_cmp,
        opponent_score=opponent_score,
        match_mode=match_mode,
        partner_key=_checked_player_key(partner_key),
        opponent_key=_checked_player_key(opponent_key),
        sport=parse_sport_filter(sport),
    )


@router.get("/members/me/match-dashboard", response_model=MemberMatchDashboardResponse)
async def get_member_match_dashboard(
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    filters: Annotated[service.MemberMatchFilters, Depends(match_filters_query)],
) -> MemberMatchDashboardResponse:
    """034-clutch-points-player-dashboard US2-US4: 會員跨場個人技術儀表板，
    對「整個篩選結果」計算（沒有 `page`）——與同一組篩選條件下
    `/members/me/match-records` 的 `total_matches` 恆相同。
    `require_verified_member`，與 `/members/me/match-records` 相同（憲章
    原則 IV：對戰紀錄在信箱驗證前 MUST 鎖定）。Errors:
    `MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`。"""
    return await service.build_member_match_dashboard(session, member.id, filters)


@router.get("/members/me/dashboard-sections", response_model=DashboardSectionsResponse)
async def get_member_dashboard_sections(
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    filters: Annotated[service.MemberMatchFilters, Depends(match_filters_query)],
) -> DashboardSectionsResponse:
    """043 contracts/sections-manifest.md §4: one activity's dashboard, laid
    out by its sport type. `sport` is required. Errors:
    `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`, `SPORT_REQUIRED`,
    `INVALID_SPORT_FILTER`."""
    return await service.build_dashboard_sections(session, member.id, filters)


@router.get("/members/me/activities", response_model=MemberActivitiesResponse)
async def get_member_activities(
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberActivitiesResponse:
    """043 contracts/sports-api.md §5: the activities the member has played,
    most matches first. Errors: `MEMBER_TOKEN_INVALID`,
    `EMAIL_NOT_VERIFIED`."""
    return await service.build_member_activities(session, member.id)


@router.post("/members/me/sports", response_model=CustomSportView, status_code=201)
async def create_member_sport(
    payload: custom_sports.CustomSportCreate,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CustomSportView:
    """043 contracts/sports-api.md §2: a new custom activity. Errors:
    `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`, `VALIDATION_ERROR`,
    `CUSTOM_SPORT_NAME_TAKEN`, `CUSTOM_SPORT_LIMIT`."""
    sport = await custom_sports.create_custom_sport(session, member.id, payload)
    return custom_sport_view(sport)


@router.delete("/members/me/sports/{sport_id}", status_code=204)
async def delete_member_sport(
    sport_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """043: delete one of my custom activities; groups keep their snapshot.
    Errors: `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`,
    `CUSTOM_SPORT_NOT_FOUND`."""
    await custom_sports.delete_custom_sport(session, member.id, sport_id)


@router.get("/members/me/supported-languages", response_model=SupportedLanguagesResponse)
async def get_supported_languages() -> SupportedLanguagesResponse:
    """022-member-personal-settings FR-004: backs the「基本設定」language
    dropdown's options. 024-add-english-language: auth requirement removed
    (was `require_member`) — the content is static, non-member-specific
    config, and anonymous visitors plus the nav-shell-less court/scoreboard/
    control-panel routes now need this list too (FR-003/FR-003a,
    research.md #1)."""
    return SupportedLanguagesResponse()


@router.patch("/members/me/language", response_model=MemberPublicResponse)
async def set_language_preference(
    payload: SetLanguagePreferenceRequest,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberPublicResponse:
    """FR-004/FR-005. Errors: `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`,
    `LANGUAGE_NOT_SUPPORTED`."""
    updated = await service.set_language_preference(session, member, payload.language)
    return await _to_public(session, updated)


@router.patch("/members/me/privacy", response_model=PrivacySettingsResponse)
async def set_privacy_settings(
    payload: PrivacySettingsRequest,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PrivacySettingsResponse:
    """FR-016/FR-020~023. Errors: `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`,
    `VALIDATION_ERROR` (both fields omitted — `PrivacySettingsRequest`'s own
    validator)."""
    updated = await service.update_privacy_settings(
        session,
        member,
        allow_search=payload.allow_search,
        share_match_records_with_friends=payload.share_match_records_with_friends,
        allow_friend_invite_from_match_pages=payload.allow_friend_invite_from_match_pages,
    )
    return PrivacySettingsResponse(
        allow_search=updated.allow_search,
        share_match_records_with_friends=updated.share_match_records_with_friends,
        allow_friend_invite_from_match_pages=updated.allow_friend_invite_from_match_pages,
    )


@router.get("/members/me/login-records", response_model=LoginRecordsResponse)
async def get_login_records(
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
) -> LoginRecordsResponse:
    """FR-006~010. Errors: `MEMBER_TOKEN_INVALID`, `EMAIL_NOT_VERIFIED`."""
    return await service.list_login_records(session, member.id, page)


# MUST stay below `/members/me/match-dashboard`: routes match in declaration
# order, and "me" is not a UUID — declared first, this one would answer that
# request with a 422.
@router.get("/members/{member_id}/match-dashboard", response_model=MemberMatchDashboardResponse)
async def get_viewed_member_match_dashboard(
    member_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    filters: Annotated[service.MemberMatchFilters, Depends(match_filters_query)],
) -> MemberMatchDashboardResponse:
    """034-clutch-points-player-dashboard US5 (好友檢視技術儀表板): 授權與
    `GET /members/{member_id}/match-records` 完全相同——同一個
    `_resolve_viewable_member()`、同樣的檢查順序
    `SELF_VIEW_NOT_SUPPORTED` → `MEMBER_NOT_FOUND` → `FRIENDSHIP_REQUIRED`
    → `MATCH_RECORDS_PRIVATE`，每次請求重新檢查、不通知被檢視方。Errors:
    `MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`、上述四者。"""
    return await service.view_member_match_dashboard(session, member.id, member_id, filters)


@router.get(
    "/members/{member_id}/dashboard-sections", response_model=DashboardSectionsResponse
)
async def get_viewed_member_dashboard_sections(
    member_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    filters: Annotated[service.MemberMatchFilters, Depends(match_filters_query)],
) -> DashboardSectionsResponse:
    """043: a friend's per-activity dashboard; same gate as
    `/members/{member_id}/match-dashboard`."""
    return await service.view_dashboard_sections(session, member.id, member_id, filters)


@router.get("/members/{member_id}/activities", response_model=MemberActivitiesResponse)
async def get_viewed_member_activities(
    member_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberActivitiesResponse:
    """043: a friend's activities; same gate as their match records."""
    return await service.view_member_activities(session, member.id, member_id)


@router.get("/members/{member_id}/match-comparison", response_model=MatchComparisonResponse)
async def get_viewed_member_match_comparison(
    member_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MatchComparisonResponse:
    """036-match-insights-benchmarks US4: the friend's 23 unfiltered metrics
    next to the viewer's own, which side is better where that can be said, and
    the two players' head-to-head record. Read-only; nobody is notified
    (FR-039). Declared after every `/members/me/...` route, like the other
    `/{member_id}/...` ones. Errors: `MEMBER_TOKEN_INVALID`,
    `EMAIL_NOT_VERIFIED`, `SELF_VIEW_NOT_SUPPORTED`, `MEMBER_NOT_FOUND`,
    `FRIENDSHIP_REQUIRED`, `MATCH_RECORDS_PRIVATE`."""
    return await service.view_member_match_comparison(session, member.id, member_id)


@router.get(
    "/members/{member_id}/match-records", response_model=MemberMatchRecordsResponse
)
async def get_viewed_member_match_records(
    member_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    opponent1: Annotated[str | None, Query(max_length=20)] = None,
    opponent2: Annotated[str | None, Query(max_length=20)] = None,
    partner: Annotated[str | None, Query(max_length=20)] = None,
    result: Annotated[Literal["win", "loss"] | None, Query()] = None,
    ended_from: Annotated[AwareDatetime | None, Query()] = None,
    ended_before: Annotated[AwareDatetime | None, Query()] = None,
    round_from: Annotated[int | None, Query(ge=1)] = None,
    round_to: Annotated[int | None, Query(ge=1)] = None,
    self_score_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    self_score: Annotated[int | None, Query(ge=0)] = None,
    opponent_score_cmp: Annotated[Literal["gt", "eq", "lt"] | None, Query()] = None,
    opponent_score: Annotated[int | None, Query(ge=0)] = None,
    match_mode: Annotated[Literal["singles", "doubles"] | None, Query()] = None,
    partner_key: Annotated[str | None, Query(max_length=40)] = None,
    opponent_key: Annotated[str | None, Query(max_length=40)] = None,
    sport: Annotated[str | None, Query(max_length=40)] = None,
) -> MemberMatchRecordsResponse:
    """022-member-personal-settings FR-018/FR-019 (好友檢視他人戰績):
    query 參數與既有 `/members/me/match-records` 完全相同、直接透傳
    （research.md #1）。授權檢查順序見
    contracts/member-settings-api.md：`SELF_VIEW_NOT_SUPPORTED` →
    `MEMBER_NOT_FOUND` → `FRIENDSHIP_REQUIRED` → `MATCH_RECORDS_PRIVATE`。
    Errors: `MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`、上述四者。"""
    return await service.view_member_match_records(
        session,
        member.id,
        member_id,
        page,
        opponents=[name for name in (opponent1, opponent2) if name],
        partners=[partner] if partner else [],
        result=result,
        ended_from=ended_from,
        ended_before=ended_before,
        round_from=round_from,
        round_to=round_to,
        self_score_cmp=self_score_cmp,
        self_score=self_score,
        opponent_score_cmp=opponent_score_cmp,
        opponent_score=opponent_score,
        match_mode=match_mode,
        partner_key=_checked_player_key(partner_key),
        opponent_key=_checked_player_key(opponent_key),
        sport=parse_sport_filter(sport),
    )


@router.get(
    "/members/{member_id}/match-records/{match_id}",
    response_model=MatchRecordDetailResponse,
)
async def get_viewed_member_match_record_detail(
    member_id: uuid.UUID,
    match_id: uuid.UUID,
    member: Annotated[Member, Depends(security.require_verified_member)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MatchRecordDetailResponse:
    """022-member-personal-settings FR-018/FR-019, see
    `get_viewed_member_match_records()` above. Errors:
    `MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`、`SELF_VIEW_NOT_SUPPORTED`、
    `MEMBER_NOT_FOUND`、`FRIENDSHIP_REQUIRED`、`MATCH_RECORDS_PRIVATE`、
    `MATCH_NOT_FOUND`、`GROUP_MEMBERSHIP_NEVER_HELD`。"""
    return await service.view_member_match_record_detail(session, member.id, member_id, match_id)
