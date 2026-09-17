"""Member domain service layer: auth, verification, profile, and search.
Per specs/006-member-friends/plan.md."""

import base64
import hashlib
import re
import secrets
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal, cast
from urllib.parse import urlencode

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import send_email
from app.core.errors import ApiError
from app.core.turnstile import verify_turnstile_token
from app.domains.friend.service import get_friendship_status
from app.domains.group import match_stats
from app.domains.group.models import Group
from app.domains.group.schemas import (
    MatchRecordDetailResponse,
    MemberMatchRecordsResponse,
    MemberMatchRecordSummary,
    OpponentRecord,
    RoundWinRatePoint,
)
from app.domains.group.service import (
    MatchStatInputs,
    _compare,
    _completed_matches_query,
    _matches_distinct_terms,
    bind_roster_entry_to_member,
    build_group_final_standings,
    build_group_match_records,
    build_match_record_detail,
    get_completed_match_or_404,
    get_group_by_id,
    load_match_stat_inputs,
    resolve_guest_binding_target,
    verify_ever_group_member,
)
from app.domains.member import player_dashboard
from app.domains.member.models import (
    EmailVerificationToken,
    Member,
    MemberLoginRecord,
    MemberOAuthIdentity,
    PasswordResetToken,
)
from app.domains.member.oauth_client import OAuthProfile, exchange_code_for_profile
from app.domains.member.oauth_providers import Provider, get_provider_config
from app.domains.member.schemas import (
    SUPPORTED_LANGUAGES,
    LoginRecordsResponse,
    LoginRecordSummary,
    MemberGroupHistoryResponse,
    MemberGroupStatsResponse,
    MemberMatchDashboardResponse,
    MyGroupsResponse,
    MyGroupSummary,
    SearchMemberResponse,
)
from app.domains.member.security import (
    decode_oauth_state,
    generate_unique_user_number,
    hash_password,
    issue_access_token,
    issue_oauth_state,
    issue_refresh_token,
    verify_password,
)
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.schemas import ParticipantSummary
from app.system_config.service import (
    get_default_page_size,
    get_password_reset_token_ttl_hours,
    get_resend_verification_cooldown_minutes,
    get_verification_token_ttl_hours,
)

# 022-member-personal-settings research.md #2: retain at most this many
# login records per member; trimmed synchronously on every insert, no
# background job needed.
_LOGIN_RECORD_RETENTION_LIMIT = 50

# research.md #3: a deliberately coarse, dependency-free heuristic — no
# `user-agents`/`ua-parser` package (constitution IX).
_MOBILE_USER_AGENT_PATTERN = re.compile(r"Mobile|Android|iPhone|iPad", re.IGNORECASE)


def classify_device(user_agent: str | None) -> str:
    """FR-007: "desktop" | "mobile" | "unknown" — never IP/geolocation."""
    if not user_agent:
        return "unknown"
    return "mobile" if _MOBILE_USER_AGENT_PATTERN.search(user_agent) else "desktop"


async def get_linked_oauth_providers(
    session: AsyncSession, member_id: uuid.UUID
) -> list[Literal["google", "line"]]:
    """027-google-line-oauth-login contracts/account-recovery-api.md
    (`GET /members/me`): providers this member currently has a
    `member_oauth_identities` binding for (US3)."""
    result = await session.execute(
        select(MemberOAuthIdentity.provider).where(MemberOAuthIdentity.member_id == member_id)
    )
    return cast(list[Literal["google", "line"]], list(result.scalars().all()))


def _oauth_redirect_uri(provider: Provider) -> str:
    """The `redirect_uri` registered with the provider — the frontend's own
    origin (proxied to the backend via the existing `/api` Nginx rule), not
    a raw backend URL (research.md #1: `code`/`state` never need to be
    directly reachable at a non-frontend origin)."""
    settings = get_settings()
    return f"{settings.frontend_base_url}/api/auth/oauth/{provider}/callback"


def _pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


async def start_oauth_flow(
    provider: Provider,
    intent: Literal["login", "link"],
    member_id: str | None = None,
    bind_guest_token: str | None = None,
) -> str:
    """contracts/oauth-login-api.md `GET /auth/oauth/{provider}/start`.
    `member_id` MUST be provided for `intent == "link"` (the caller's own
    id, from an already-authenticated request) and MUST be `None` for
    `intent == "login"` — the router enforces this via which dependency
    (`optional_member` vs `require_verified_member`) it uses per intent.
    `bind_guest_token` (028-guest-stats-binding research.md #3): only ever
    passed for `intent == "login"`, validated by the router."""
    config = get_provider_config(provider)
    code_verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(16)
    state = issue_oauth_state(
        provider=provider,
        intent=intent,
        code_verifier=code_verifier,
        nonce=nonce,
        member_id=member_id,
        bind_guest_token=bind_guest_token,
    )
    params = {
        "client_id": config.client_id,
        "redirect_uri": _oauth_redirect_uri(provider),
        "response_type": "code",
        "scope": config.scopes,
        "state": state,
        "code_challenge": _pkce_code_challenge(code_verifier),
        "code_challenge_method": "S256",
        "nonce": nonce,
    }
    return f"{config.authorize_url}?{urlencode(params)}"


@dataclass(frozen=True)
class OAuthCallbackResult:
    """What `complete_oauth_callback()` decided — the router translates this
    into the matching redirect from contracts/oauth-login-api.md's table.
    `intent` is always populated (even on failure) so the router knows
    whether to redirect to `/auth/oauth-callback` or back to `/settings`."""

    intent: Literal["login", "link"]
    status: Literal["success", "cancelled", "error"]
    error_code: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    is_new_member: bool = False
    provider: Provider | None = None
    bound_group_id: str | None = None
    # 028-guest-stats-binding research.md #3: set only when this callback
    # also completed a guest roster binding (intent == "login" with a
    # `bind_guest_token` in `state`). A failed bind MUST NOT fail the OAuth
    # login itself — see `complete_oauth_callback()`.


async def _find_oauth_identity(
    session: AsyncSession, provider: Provider, provider_user_id: str
) -> MemberOAuthIdentity | None:
    result = await session.execute(
        select(MemberOAuthIdentity).where(
            MemberOAuthIdentity.provider == provider,
            MemberOAuthIdentity.provider_user_id == provider_user_id,
        )
    )
    return result.scalar_one_or_none()


async def _complete_oauth_login(
    session: AsyncSession,
    provider: Provider,
    profile: OAuthProfile,
    bind_guest_token: str | None = None,
    *,
    user_agent: str | None = None,
) -> OAuthCallbackResult:
    """028-guest-stats-binding research.md #3: `bind_guest_token`, when
    given, is attempted after a successful login/registration below — same
    optional-extra-step pattern in both success branches.

    bugfix/oauth-login-record: every successful branch below is a genuine
    login (returning member, or a brand-new member's first-ever session —
    OAuth has no separate register-then-verify-then-login sequence the way
    Email/password does) and MUST record one login record, same as
    Email/password's `login()` — this was missing entirely before, so an
    OAuth-only member's "最近登入" list stayed empty no matter how many times
    they signed in."""
    existing = await _find_oauth_identity(session, provider, profile.sub)
    if existing is not None:
        member = await session.get(Member, existing.member_id)
        if member is None or member.deleted_at is not None:
            # FR-011: a deleted account's binding row is deliberately left
            # in place (delete_account() never touches it) — the rejection
            # happens here, at login time, every time.
            return OAuthCallbackResult(
                intent="login", status="error", error_code="ACCOUNT_DELETED"
            )
        bound_group_id = (
            await _attempt_guest_bind(session, bind_guest_token, member.id)
            if bind_guest_token
            else None
        )
        await record_login(session, member.id, classify_device(user_agent))
        return OAuthCallbackResult(
            intent="login",
            status="success",
            access_token=issue_access_token(str(member.id), member.token_version),
            refresh_token=issue_refresh_token(str(member.id), member.token_version),
            is_new_member=False,
            bound_group_id=bound_group_id,
        )

    normalized_email = profile.email.lower() if profile.email else None
    if normalized_email is not None:
        # FR-005: collides with ANY existing member's email, regardless of
        # that member's own auth method — not just Email/password members.
        collision = await session.execute(
            select(Member.id).where(Member.email == normalized_email)
        )
        if collision.scalar_one_or_none() is not None:
            return OAuthCallbackResult(
                intent="login", status="error", error_code="OAUTH_EMAIL_ALREADY_REGISTERED"
            )

    user_number = await generate_unique_user_number(session)
    member = Member(
        email=normalized_email,
        password_hash=None,
        user_number=user_number,
        # Clarifications 2026-09-14 / research.md #6: immediately verified —
        # the OAuth provider's own authentication is the trust signal, no
        # separate verification-email step is triggered.
        verification_status="verified",
    )
    try:
        session.add(member)
        await session.flush()
        session.add(
            MemberOAuthIdentity(
                member_id=member.id,
                provider=provider,
                provider_user_id=profile.sub,
                email_at_link=profile.email,
            )
        )
        await session.commit()
    except IntegrityError:
        # E3: two concurrent requests both passed the collision check above
        # before either committed. The email-uniqueness index and the
        # identity-uniqueness index are the only two ways this can fire —
        # translate whichever one it was into the matching error code
        # rather than letting the raw IntegrityError propagate as a 500.
        await session.rollback()
        error_code = (
            "OAUTH_EMAIL_ALREADY_REGISTERED"
            if normalized_email is not None
            else "OAUTH_IDENTITY_ALREADY_LINKED"
        )
        return OAuthCallbackResult(intent="login", status="error", error_code=error_code)
    await session.refresh(member)

    bound_group_id = (
        await _attempt_guest_bind(session, bind_guest_token, member.id)
        if bind_guest_token
        else None
    )
    await record_login(session, member.id, classify_device(user_agent))
    return OAuthCallbackResult(
        intent="login",
        status="success",
        access_token=issue_access_token(str(member.id), member.token_version),
        refresh_token=issue_refresh_token(str(member.id), member.token_version),
        is_new_member=True,
        bound_group_id=bound_group_id,
    )


async def _complete_oauth_link(
    session: AsyncSession, provider: Provider, profile: OAuthProfile, member_id: str | None
) -> OAuthCallbackResult:
    if member_id is None:
        return OAuthCallbackResult(
            intent="link", status="error", error_code="OAUTH_STATE_INVALID", provider=provider
        )
    caller_id = uuid.UUID(member_id)

    existing = await _find_oauth_identity(session, provider, profile.sub)
    if existing is not None:
        if existing.member_id == caller_id:
            return OAuthCallbackResult(intent="link", status="success", provider=provider)
        return OAuthCallbackResult(
            intent="link",
            status="error",
            error_code="OAUTH_IDENTITY_ALREADY_LINKED",
            provider=provider,
        )

    # C1 (/speckit-analyze 2026-09-14 remediation): the caller already has a
    # DIFFERENT external account bound for this same provider. Rejected —
    # MUST NOT delete-then-replace the existing binding.
    caller_existing = await session.execute(
        select(MemberOAuthIdentity.id).where(
            MemberOAuthIdentity.member_id == caller_id,
            MemberOAuthIdentity.provider == provider,
        )
    )
    if caller_existing.scalar_one_or_none() is not None:
        return OAuthCallbackResult(
            intent="link",
            status="error",
            error_code="OAUTH_PROVIDER_ALREADY_LINKED",
            provider=provider,
        )

    try:
        session.add(
            MemberOAuthIdentity(
                member_id=caller_id,
                provider=provider,
                provider_user_id=profile.sub,
                email_at_link=profile.email,
            )
        )
        await session.commit()
    except IntegrityError:
        # E3: concurrent race on either unique constraint.
        await session.rollback()
        return OAuthCallbackResult(
            intent="link",
            status="error",
            error_code="OAUTH_IDENTITY_ALREADY_LINKED",
            provider=provider,
        )

    return OAuthCallbackResult(intent="link", status="success", provider=provider)


async def complete_oauth_callback(
    session: AsyncSession,
    provider: Provider,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
    user_agent: str | None = None,
) -> OAuthCallbackResult:
    """contracts/oauth-login-api.md `GET /auth/oauth/{provider}/callback`.
    Every branch below matches one row of that contract's table."""
    if not state:
        return OAuthCallbackResult(intent="login", status="error", error_code="OAUTH_STATE_INVALID")
    try:
        oauth_state = decode_oauth_state(state)
    except ApiError:
        return OAuthCallbackResult(intent="login", status="error", error_code="OAUTH_STATE_INVALID")
    if oauth_state.provider != provider:
        return OAuthCallbackResult(
            intent=oauth_state.intent, status="error", error_code="OAUTH_STATE_INVALID"
        )

    intent = oauth_state.intent

    if error is not None:
        # FR-010: user cancelled/denied on the provider's own screen.
        return OAuthCallbackResult(intent=intent, status="cancelled", provider=provider)
    if not code:
        return OAuthCallbackResult(
            intent=intent, status="error", error_code="OAUTH_PROVIDER_ERROR", provider=provider
        )

    config = get_provider_config(provider)
    try:
        profile = await exchange_code_for_profile(
            config,
            code=code,
            code_verifier=oauth_state.code_verifier,
            redirect_uri=_oauth_redirect_uri(provider),
            nonce=oauth_state.nonce,
        )
    except ApiError:
        return OAuthCallbackResult(
            intent=intent, status="error", error_code="OAUTH_PROVIDER_ERROR", provider=provider
        )

    if intent == "link":
        return await _complete_oauth_link(session, provider, profile, oauth_state.member_id)
    return await _complete_oauth_login(
        session, provider, profile, oauth_state.bind_guest_token, user_agent=user_agent
    )


async def _attempt_guest_bind(
    session: AsyncSession, bind_guest_token: str, member_id: uuid.UUID
) -> str | None:
    """028-guest-stats-binding research.md #3/contracts/guest-binding-api.md:
    a binding failure (unknown/invalidated token, already bound) MUST NOT
    fail the OAuth login itself — called only after login/registration
    already succeeded. Returns the bound `group_id`, or `None` if the bind
    didn't happen."""
    try:
        roster_entry = await resolve_guest_binding_target(session, bind_guest_token)
        await bind_roster_entry_to_member(session, roster_entry.id, member_id)
    except ApiError:
        return None
    return str(roster_entry.group_id)


@dataclass(frozen=True)
class GuestBindResult:
    group_id: uuid.UUID
    access_token: str | None
    refresh_token: str | None


async def complete_guest_bind(
    session: AsyncSession,
    guest_session_token: str,
    *,
    current_member: Member | None,
    mode: Literal["register", "login"] | None,
    email: str | None,
    password: str | None,
    turnstile_token: str | None,
) -> GuestBindResult:
    """028-guest-stats-binding contracts/guest-binding-api.md `POST
    /groups/guest-token/{token}/bind` — kept in the `member` domain (which
    already legitimately imports from `group.service`, e.g.
    `verify_ever_group_member`) rather than `group/service.py`, since the
    reverse import would be circular (research.md #2). `group/router.py`'s
    endpoint is a thin wrapper around this function; unit tests call it
    directly, same as `complete_oauth_callback()`.

    Three of the four binding paths from research.md #2 are handled here:
    `current_member` present (Clarifications 2026-09-15/FR-012, one-click,
    body ignored), `mode="register"` (US1), `mode="login"` (US2). The
    fourth (OAuth) is `complete_oauth_callback()`'s `bind_guest_token`
    extension above. Errors: `LINK_NOT_FOUND`, `ROSTER_ENTRY_ALREADY_BOUND`,
    `INVALID_REQUEST`, `CAPTCHA_INVALID`,
    `EMAIL_ALREADY_REGISTERED`, `INVALID_CREDENTIALS`."""
    roster_entry = await resolve_guest_binding_target(session, guest_session_token)

    access_token: str | None = None
    refresh_token: str | None = None

    if current_member is not None:
        member_id = current_member.id
    elif mode == "register":
        if email is None or password is None or turnstile_token is None:
            raise ApiError("INVALID_REQUEST", status_code=400)
        await verify_turnstile_token(turnstile_token)
        member = await register(session, email, password)
        member_id = member.id
        access_token = issue_access_token(str(member.id), member.token_version)
        refresh_token = issue_refresh_token(str(member.id), member.token_version)
    elif mode == "login":
        if email is None or password is None:
            raise ApiError("INVALID_REQUEST", status_code=400)
        member, access_token, refresh_token = await login(session, email, password)
        member_id = member.id
    else:
        raise ApiError("INVALID_REQUEST", status_code=400)

    await bind_roster_entry_to_member(session, roster_entry.id, member_id)
    return GuestBindResult(
        group_id=roster_entry.group_id, access_token=access_token, refresh_token=refresh_token
    )


async def unlink_oauth_identity(session: AsyncSession, member: Member, provider: Provider) -> None:
    """contracts/account-recovery-api.md `DELETE
    /members/me/oauth-identities/{provider}`. Errors:
    `OAUTH_IDENTITY_NOT_LINKED`, `LAST_LOGIN_METHOD` (FR-008 — refuses to
    leave the member with zero remaining ways to sign in)."""
    result = await session.execute(
        select(MemberOAuthIdentity).where(
            MemberOAuthIdentity.member_id == member.id,
            MemberOAuthIdentity.provider == provider,
        )
    )
    identity = result.scalar_one_or_none()
    if identity is None:
        raise ApiError("OAUTH_IDENTITY_NOT_LINKED", status_code=404)

    other_bindings = await session.execute(
        select(func.count(MemberOAuthIdentity.id)).where(
            MemberOAuthIdentity.member_id == member.id,
            MemberOAuthIdentity.provider != provider,
        )
    )
    if member.password_hash is None and other_bindings.scalar_one() == 0:
        raise ApiError("LAST_LOGIN_METHOD", status_code=409)

    await session.delete(identity)
    await session.commit()


async def add_email(session: AsyncSession, member: Member, email: str) -> None:
    """contracts/account-recovery-api.md `POST /members/me/email` (FR-013):
    only for a member whose `email` is currently `None` — "changing" an
    existing email is out of scope. Errors: `EMAIL_ALREADY_SET`,
    `EMAIL_ALREADY_REGISTERED`."""
    if member.email is not None:
        raise ApiError("EMAIL_ALREADY_SET", status_code=409)

    normalized_email = email.lower()
    collision = await session.execute(
        select(Member.id).where(Member.email == normalized_email)
    )
    if collision.scalar_one_or_none() is not None:
        raise ApiError("EMAIL_ALREADY_REGISTERED", status_code=409)

    member.email = normalized_email
    await session.commit()
    await session.refresh(member)
    await _issue_verification_token_and_email(session, member)


async def login(
    session: AsyncSession, email: str, password: str, *, user_agent: str | None = None
) -> tuple[Member, str, str]:
    """FR-009: unverified members MUST still be able to log in successfully
    — verification-gating happens per-endpoint (`require_verified_member`),
    not at login itself. 022-member-personal-settings FR-007: every
    successful call here is an "active login" and MUST record one login
    record (token refresh, a separate function, MUST NOT)."""
    result = await session.execute(select(Member).where(Member.email == email.lower()))
    member = result.scalar_one_or_none()
    # 027-google-line-oauth-login: an OAuth-only member (password_hash is
    # None) can never match an Email/password login attempt — there is no
    # password to verify against, not even a wrong one.
    if member is None or member.password_hash is None:
        raise ApiError("INVALID_CREDENTIALS", status_code=401)
    if not verify_password(password, member.password_hash):
        raise ApiError("INVALID_CREDENTIALS", status_code=401)

    await record_login(session, member.id, classify_device(user_agent))

    access_token = issue_access_token(str(member.id), member.token_version)
    refresh_token = issue_refresh_token(str(member.id), member.token_version)
    return member, access_token, refresh_token


async def record_login(session: AsyncSession, member_id: uuid.UUID, device_category: str) -> None:
    """022-member-personal-settings research.md #2: inserts one row, then
    trims this member's records down to the most recent
    `_LOGIN_RECORD_RETENTION_LIMIT`, all in the caller's transaction (no
    background job)."""
    session.add(MemberLoginRecord(member_id=member_id, device_category=device_category))
    await session.flush()

    keep_ids_subquery = (
        select(MemberLoginRecord.id)
        .where(MemberLoginRecord.member_id == member_id)
        .order_by(MemberLoginRecord.created_at.desc())
        .limit(_LOGIN_RECORD_RETENTION_LIMIT)
    )
    await session.execute(
        delete(MemberLoginRecord).where(
            MemberLoginRecord.member_id == member_id,
            MemberLoginRecord.id.not_in(keep_ids_subquery),
        )
    )
    await session.commit()


async def list_login_records(
    session: AsyncSession, member_id: uuid.UUID, page: int
) -> LoginRecordsResponse:
    """FR-008/FR-009: newest-first, paginated (default_page_size, same
    convention as `build_member_match_records()`)."""
    count_result = await session.execute(
        select(func.count(MemberLoginRecord.id)).where(MemberLoginRecord.member_id == member_id)
    )
    total = count_result.scalar_one()
    page_size = await get_default_page_size(session)
    total_pages = max(1, (total + page_size - 1) // page_size)

    result = await session.execute(
        select(MemberLoginRecord)
        .where(MemberLoginRecord.member_id == member_id)
        .order_by(MemberLoginRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = [
        LoginRecordSummary(created_at=row.created_at, device_category=row.device_category)
        for row in result.scalars()
    ]
    return LoginRecordsResponse(records=records, page=page, total_pages=total_pages)


def _normalize_language(language: str | None) -> str | None:
    """Case-insensitively matches `language` against `SUPPORTED_LANGUAGES`
    and returns the canonical stored form (e.g. `"EN"`/`"en"` → `"en"`), or
    `None` if it isn't a supported language at all. Shared by both
    `register()` and `set_language_preference()` so their membership test
    can't silently drift apart — each still decides independently what to
    do with a `None` result (register() falls back to the column default;
    set_language_preference() raises `LANGUAGE_NOT_SUPPORTED`)."""
    if language is None:
        return None
    for supported in SUPPORTED_LANGUAGES:
        if supported.lower() == language.lower():
            return supported
    return None


async def set_language_preference(session: AsyncSession, member: Member, language: str) -> Member:
    """FR-004/FR-005. Errors: `LANGUAGE_NOT_SUPPORTED` — deliberately raised
    here (not a Pydantic validator) so it surfaces as this specific
    semantic error code rather than the generic `VALIDATION_ERROR`
    (contracts/member-settings-api.md)."""
    normalized = _normalize_language(language)
    if normalized is None:
        raise ApiError("LANGUAGE_NOT_SUPPORTED", status_code=400)
    member.language_preference = normalized
    await session.commit()
    await session.refresh(member)
    return member


async def update_privacy_settings(
    session: AsyncSession,
    member: Member,
    *,
    allow_search: bool | None,
    share_match_records_with_friends: bool | None,
    allow_friend_invite_from_match_pages: bool | None = None,
) -> Member:
    """FR-016/FR-020~023, plus 026-match-record-friend-invite FR-006.
    `PrivacySettingsRequest`'s own validator already guarantees at least one
    field is provided — this only applies whichever field(s) were actually
    given, leaving the others untouched (independently of one another)."""
    if allow_search is not None:
        member.allow_search = allow_search
    if share_match_records_with_friends is not None:
        member.share_match_records_with_friends = share_match_records_with_friends
    if allow_friend_invite_from_match_pages is not None:
        member.allow_friend_invite_from_match_pages = allow_friend_invite_from_match_pages
    await session.commit()
    await session.refresh(member)
    return member


async def _resolve_viewable_member(
    session: AsyncSession, viewer_id: uuid.UUID, member_id: uuid.UUID
) -> None:
    """022-member-personal-settings research.md #1/#6, contracts/
    member-settings-api.md 授權檢查順序: shared by `view_member_match_records()`
    and `view_member_match_record_detail()`. Errors, in order:
    `SELF_VIEW_NOT_SUPPORTED` (checked first — a member viewing their own
    id would otherwise fall through to `FRIENDSHIP_REQUIRED`, since nobody
    ever has a `FriendRequest` with themselves), `MEMBER_NOT_FOUND` (target
    missing/unverified — mirrors `search_member()`'s non-disclosure),
    `FRIENDSHIP_REQUIRED`, `MATCH_RECORDS_PRIVATE`."""
    if viewer_id == member_id:
        raise ApiError("SELF_VIEW_NOT_SUPPORTED", status_code=400)

    result = await session.execute(select(Member).where(Member.id == member_id))
    target = result.scalar_one_or_none()
    if target is None or target.verification_status != "verified":
        raise ApiError("MEMBER_NOT_FOUND", status_code=404)

    status = await get_friendship_status(session, viewer_id, member_id)
    if status != "friends":
        raise ApiError("FRIENDSHIP_REQUIRED", status_code=403)
    if not target.share_match_records_with_friends:
        raise ApiError("MATCH_RECORDS_PRIVATE", status_code=403)


async def view_member_match_records(
    session: AsyncSession,
    viewer_id: uuid.UUID,
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
    match_mode: Literal["singles", "doubles"] | None = None,
) -> MemberMatchRecordsResponse:
    """FR-018/FR-019: once authorized, delegates to the SAME
    `build_member_match_records()` the self-viewing `/members/me/
    match-records` endpoint uses — no parallel logic (research.md #1).
    Mirrors that function's full filter surface (minus `group_id`, which is
    only ever used internally by `get_member_group_history()`)."""
    await _resolve_viewable_member(session, viewer_id, member_id)
    return await build_member_match_records(
        session,
        member_id,
        page,
        opponents=opponents,
        partners=partners,
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


async def view_member_match_dashboard(
    session: AsyncSession,
    viewer_id: uuid.UUID,
    member_id: uuid.UUID,
    filters: "MemberMatchFilters",
) -> MemberMatchDashboardResponse:
    """034-clutch-points-player-dashboard US5: a friend's dashboard, behind
    the SAME gate as their match records — 023 settled that the record list
    and the aggregate stats share one privacy switch, and the dashboard is
    aggregate stats. Eligibility is re-checked on every call, never cached,
    and the viewed member is not notified (023 FR-008/FR-011). See
    `view_member_match_records()`."""
    await _resolve_viewable_member(session, viewer_id, member_id)
    return await build_member_match_dashboard(session, member_id, filters)


async def view_member_match_record_detail(
    session: AsyncSession, viewer_id: uuid.UUID, member_id: uuid.UUID, match_id: uuid.UUID
) -> MatchRecordDetailResponse:
    """FR-018/FR-019, see `view_member_match_records()`."""
    await _resolve_viewable_member(session, viewer_id, member_id)
    return await get_member_match_record_detail(session, member_id, match_id)


def _verification_link(token: str) -> str:
    return f"{get_settings().frontend_base_url}/auth/verify-email/{token}"


# 024-add-english-language FR-010/research.md #4: subject/body per language,
# keyed by `member.language_preference`. An unrecognized/legacy value falls
# back to "zh-TW" (`_email_for_language()`) — never raises, since a bad
# stored value must not block sending the email at all.
_VERIFICATION_EMAIL = {
    "zh-TW": ("請驗證你的信箱", "請點擊以下連結完成信箱驗證：{link}"),
    "en": ("Verify your email", "Please click the following link to verify your email: {link}"),
}

_PASSWORD_RESET_EMAIL = {
    "zh-TW": ("重設密碼", "請點擊以下連結重設密碼：{link}"),
    "en": ("Reset your password", "Please click the following link to reset your password: {link}"),
}


def _email_for_language(
    templates: dict[str, tuple[str, str]], language: str, link: str
) -> tuple[str, str]:
    subject, body_template = templates.get(language, templates["zh-TW"])
    return subject, body_template.format(link=link)


async def _issue_verification_token_and_email(
    session: AsyncSession, member: Member
) -> EmailVerificationToken:
    # 027-google-line-oauth-login: only ever called by register() (always
    # has an email — RegisterRequest.email is required) and add_email()
    # (writes member.email immediately before calling this) — never for an
    # OAuth-created member (research.md #6 — those skip this entirely).
    assert member.email is not None
    ttl_hours = await get_verification_token_ttl_hours(session)
    verification_token = EmailVerificationToken(
        member_id=member.id, expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours)
    )
    session.add(verification_token)
    await session.flush()
    await session.commit()
    await session.refresh(verification_token)
    subject, body = _email_for_language(
        _VERIFICATION_EMAIL,
        member.language_preference,
        _verification_link(str(verification_token.token)),
    )
    await send_email(member.email, subject, body)
    return verification_token


async def register(
    session: AsyncSession, email: str, password: str, language: str | None = None
) -> Member:
    """Turnstile verification happens at the router layer (matches
    group/router.py's create_group precedent) — this function has no
    knowledge of it. FR-004: Email uniqueness is case-insensitive
    (normalized to lowercase, per FR-006).

    024-add-english-language FR-009: `language`, when a valid member of
    `SUPPORTED_LANGUAGES`, seeds the new member's `language_preference`
    instead of relying on the column default. An absent or unsupported
    value falls back to that default silently — never blocks registration
    (research.md #5)."""
    normalized_email = email.lower()
    existing = await session.execute(select(Member.id).where(Member.email == normalized_email))
    if existing.scalar_one_or_none() is not None:
        raise ApiError("EMAIL_ALREADY_REGISTERED", status_code=409)

    user_number = await generate_unique_user_number(session)
    member = Member(
        email=normalized_email, password_hash=hash_password(password), user_number=user_number
    )
    normalized_language = _normalize_language(language)
    if normalized_language is not None:
        member.language_preference = normalized_language
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


async def _verification_token_count_and_last_created_at(
    session: AsyncSession, member_id: uuid.UUID
) -> tuple[int, datetime | None]:
    """020-resend-verification-email research.md #2/#5: single query shared
    by `resend_verification()` (write path) and
    `get_resend_verification_available_at()` (read path). The *count*
    matters, not just the latest timestamp: `register()` always issues one
    token immediately, and the only two paths that ever create a token are
    registration and a manual resend — so count <= 1 means this member has
    never manually triggered a resend yet, and MUST NOT be cooled down by
    the registration-time send (fixes `/speckit-analyze` finding I1: the
    original design would reject a member's very first resend click if
    attempted within the cooldown window of their own registration)."""
    result = await session.execute(
        select(func.count(EmailVerificationToken.id), func.max(EmailVerificationToken.created_at))
        .where(EmailVerificationToken.member_id == member_id)
    )
    count, last_created_at = result.one()
    return count, last_created_at


async def resend_verification(session: AsyncSession, member: Member) -> datetime:
    """Returns `available_at` — the earliest time the *next* resend will be
    allowed (research.md #3), even when this call is the member's first-ever
    manual resend (which always succeeds regardless of cooldown, per
    `_verification_token_count_and_last_created_at()`)."""
    if member.verification_status == "verified":
        raise ApiError("ALREADY_VERIFIED", status_code=409)

    cooldown = timedelta(minutes=await get_resend_verification_cooldown_minutes(session))
    count, last_created_at = await _verification_token_count_and_last_created_at(
        session, member.id
    )
    if count > 1 and last_created_at is not None and datetime.now(UTC) - last_created_at < cooldown:
        raise ApiError("RESEND_RATE_LIMITED", status_code=429)

    new_token = await _issue_verification_token_and_email(session, member)
    return new_token.created_at + cooldown


async def get_resend_verification_available_at(
    session: AsyncSession, member: Member
) -> datetime | None:
    """Read-only counterpart to `resend_verification()`'s cooldown check —
    backs `MemberPublicResponse.resend_verification_available_at`
    (`GET /members/me`, `POST /auth/login`). `None` means resend is
    available right now (verified members always get `None` without a
    query, and unverified members with <= 1 token — i.e. never manually
    resent — always get `None` too, research.md #5)."""
    if member.verification_status == "verified":
        return None

    count, last_created_at = await _verification_token_count_and_last_created_at(
        session, member.id
    )
    if count <= 1 or last_created_at is None:
        return None
    cooldown = timedelta(minutes=await get_resend_verification_cooldown_minutes(session))
    available_at = last_created_at + cooldown
    if available_at <= datetime.now(UTC):
        return None
    return available_at


def _reset_link(token: str) -> str:
    return f"{get_settings().frontend_base_url}/auth/reset-password/{token}"


async def forgot_password(session: AsyncSession, email: str) -> None:
    """FR-013 (2026-09-01 clarification): silent no-op for an unregistered
    Email — never raises, never reveals whether the account exists."""
    result = await session.execute(select(Member).where(Member.email == email.lower()))
    member = result.scalar_one_or_none()
    if member is None:
        return
    # 027-google-line-oauth-login: found via Member.email == email.lower(),
    # so it's non-None by construction — mypy just can't see that through
    # the query.
    assert member.email is not None

    ttl_hours = await get_password_reset_token_ttl_hours(session)
    reset_token = PasswordResetToken(
        member_id=member.id, expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours)
    )
    session.add(reset_token)
    await session.flush()
    await session.commit()
    await session.refresh(reset_token)
    subject, body = _email_for_language(
        _PASSWORD_RESET_EMAIL,
        member.language_preference,
        _reset_link(str(reset_token.token)),
    )
    await send_email(member.email, subject, body)


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
    session: AsyncSession, member: Member, current_password: str | None, new_password: str
) -> tuple[Member, str, str]:
    """FR-025/026: bumps `token_version` (invalidating every other device)
    but immediately issues a fresh token pair for the requesting device.

    027-google-line-oauth-login research.md #7: when `member.password_hash`
    is `None` (a pure OAuth member who has never set a password), this
    call is "set my first password" rather than "change it" —
    `current_password` is ignored even if provided, since there is nothing
    to re-confirm; the caller's authenticated session is itself sufficient
    proof of identity, the same trust level `require_verified_member`
    already grants for every other self-service action."""
    if member.password_hash is not None and (
        current_password is None or not verify_password(current_password, member.password_hash)
    ):
        raise ApiError("CURRENT_PASSWORD_INCORRECT", status_code=400)

    member.password_hash = hash_password(new_password)
    member.token_version += 1
    await session.commit()
    await session.refresh(member)

    access_token = issue_access_token(str(member.id), member.token_version)
    refresh_token = issue_refresh_token(str(member.id), member.token_version)
    return member, access_token, refresh_token


# 025-delete-account research.md #5: a fixed, language-neutral literal —
# nicknames are user-generated data, not UI chrome, and were never routed
# through the i18n translation-file system (a nickname doesn't change when
# the viewer switches display language). Used for both `Member.nickname`
# and the `roster_entries.nickname` cascade below.
DELETED_MEMBER_PLACEHOLDER_NICKNAME = "Deleted User"


async def delete_account(
    session: AsyncSession, member: Member, current_password: str | None
) -> Member:
    """FR-001~008: anonymizes the account in place rather than deleting the
    row (research.md #1) — every FK pointing at `member.id` (match
    participants, roster entries, friend requests, group creators) stays
    valid. Errors: `CURRENT_PASSWORD_INCORRECT`.

    FR-003a (Clarifications 2026-09-14): also cascades the placeholder
    nickname to every `roster_entries` row for this member, regardless of
    match/round status — a deliberate, deletion-only exception to the
    otherwise-permanent nickname-snapshot isolation from `set_nickname()`
    (see `test_nickname_snapshot_isolation.py`, 006). No other code path is
    allowed to write to `roster_entries.nickname` for a reason other than
    joining a new roster.

    027-google-line-oauth-login research.md #7: a pure OAuth member
    (`password_hash is None`) has nothing to re-confirm — the frontend's
    existing two-step confirm dialog (constitution V) is the only
    safeguard for them, matching `change_password()`'s same relaxation."""
    if member.password_hash is not None and (
        current_password is None or not verify_password(current_password, member.password_hash)
    ):
        raise ApiError("CURRENT_PASSWORD_INCORRECT", status_code=400)

    now = datetime.now(UTC)
    member.email = f"deleted-{member.id}@rally-stats.invalid"
    member.password_hash = hash_password(secrets.token_urlsafe(32))
    member.nickname = DELETED_MEMBER_PLACEHOLDER_NICKNAME
    member.deleted_at = now
    member.token_version += 1

    await session.execute(
        update(RosterEntry)
        .where(RosterEntry.member_id == member.id)
        .values(nickname=DELETED_MEMBER_PLACEHOLDER_NICKNAME)
    )
    await session.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.member_id == member.id,
            EmailVerificationToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    await session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.member_id == member.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    await session.commit()
    await session.refresh(member)
    return member


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
                roster_entry_id=str(entry.id),
                nickname=entry.nickname,
                team=participant.team,
                # 026-match-record-friend-invite research.md #1: this
                # builder is one of the three authenticated paths allowed
                # to populate member_id.
                member_id=str(entry.member_id) if entry.member_id else None,
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


@dataclass(frozen=True)
class MemberMatchFilters:
    """Every filter `build_member_match_records()` accepts, as one value —
    034's dashboard applies exactly the same set, and a seventh copy of
    twelve keyword arguments was one too many. `group_id` is only ever set
    internally by `get_member_group_history()`."""

    opponents: tuple[str, ...] = ()
    partners: tuple[str, ...] = ()
    result: Literal["win", "loss"] | None = None
    date_from: date | None = None
    date_to: date | None = None
    round_from: int | None = None
    round_to: int | None = None
    self_score_cmp: Literal["gt", "eq", "lt"] | None = None
    self_score: int | None = None
    opponent_score_cmp: Literal["gt", "eq", "lt"] | None = None
    opponent_score: int | None = None
    group_id: uuid.UUID | None = None
    match_mode: Literal["singles", "doubles"] | None = None


@dataclass(frozen=True)
class FilteredMatch:
    match: Match
    summary: MemberMatchRecordSummary
    won: bool
    my_team: Literal["A", "B"]
    my_entry_id: uuid.UUID


async def _filtered_member_matches(
    session: AsyncSession, member_id: uuid.UUID, filters: MemberMatchFilters
) -> list[FilteredMatch]:
    """The member's completed matches that pass `filters`, newest first —
    the ONE definition of "the filtered result set" that both the match
    list's aggregates and 034's dashboard are computed over (FR-019). See
    `build_member_match_records()` for what each filter means."""
    participant_exists = (
        select(MatchParticipant.id)
        .join(RosterEntry, RosterEntry.id == MatchParticipant.roster_entry_id)
        .where(MatchParticipant.match_id == Match.id, RosterEntry.member_id == member_id)
        .exists()
    )
    base_query = _completed_matches_query().where(participant_exists)
    if filters.group_id is not None:
        base_query = base_query.where(Match.group_id == filters.group_id)
    if filters.match_mode is not None:
        base_query = base_query.join(Group, Group.id == Match.group_id).where(
            Group.match_mode == filters.match_mode
        )

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

    filtered: list[FilteredMatch] = []
    for match, summary in zip(all_matches, summaries, strict=True):
        my_team = my_team_by_match.get(match.id)
        if my_team is None:
            continue
        my_entry_id = my_entry_by_match[match.id]
        match_opponents = summary.team_b if my_team == "A" else summary.team_a
        match_partners = [
            p for p in (summary.team_a if my_team == "A" else summary.team_b)
            if p.roster_entry_id != str(my_entry_id)
        ]
        my_score = match.score_a if my_team == "A" else match.score_b
        their_score = match.score_b if my_team == "A" else match.score_a
        won = summary.won

        if not _matches_distinct_terms(
            list(filters.opponents), [p.nickname for p in match_opponents]
        ):
            continue
        if not _matches_distinct_terms(
            list(filters.partners), [p.nickname for p in match_partners]
        ):
            continue
        if filters.result is not None and won != (filters.result == "win"):
            continue
        if match.ended_at is not None:
            match_date = match.ended_at.date()
            if filters.date_from is not None and match_date < filters.date_from:
                continue
            if filters.date_to is not None and match_date > filters.date_to:
                continue
        if filters.round_from is not None and match.round_number < filters.round_from:
            continue
        if filters.round_to is not None and match.round_number > filters.round_to:
            continue
        if (
            filters.self_score_cmp is not None
            and filters.self_score is not None
            and not _compare(my_score, filters.self_score_cmp, filters.self_score)
        ):
            continue
        if (
            filters.opponent_score_cmp is not None
            and filters.opponent_score is not None
            and not _compare(their_score, filters.opponent_score_cmp, filters.opponent_score)
        ):
            continue

        filtered.append(
            FilteredMatch(
                match=match,
                summary=summary,
                won=won,
                my_team=my_team,  # type: ignore[arg-type]
                my_entry_id=my_entry_id,
            )
        )
    return filtered


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
    match_mode: Literal["singles", "doubles"] | None = None,
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
    rather than duplicating the win/loss-counting logic a third time.

    `match_mode`: keyword-only, defaults to `None`. `Match` itself has no
    match_mode column (a match's singles/doubles-ness is a property of the
    group it happened in), so this filters via a join to `Group` rather
    than the Python post-filter loop below — unlike the nickname/score
    filters, it can be pushed down to SQL directly."""
    filtered = await _filtered_member_matches(
        session,
        member_id,
        MemberMatchFilters(
            opponents=tuple(opponents or ()),
            partners=tuple(partners or ()),
            result=result,
            date_from=date_from,
            date_to=date_to,
            round_from=round_from,
            round_to=round_to,
            self_score_cmp=self_score_cmp,
            self_score=self_score,
            opponent_score_cmp=opponent_score_cmp,
            opponent_score=opponent_score,
            group_id=group_id,
            match_mode=match_mode,
        ),
    )

    total_matches = len(filtered)
    total_wins = sum(1 for item in filtered if item.won)
    total_losses = total_matches - total_wins
    win_rate = (total_wins / total_matches) if total_matches else 0.0

    round_tallies: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    opponent_tallies: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item in filtered:
        bucket = round_tallies[item.match.round_number]
        bucket[0 if item.won else 1] += 1

        match_opponents = item.summary.team_b if item.my_team == "A" else item.summary.team_a
        for opponent in match_opponents:
            tally = opponent_tallies[opponent.nickname]
            tally[0 if item.won else 1] += 1

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

    page_size = await get_default_page_size(session)
    total_pages = max(1, (total_matches + page_size - 1) // page_size)
    start = (page - 1) * page_size
    end = start + page_size
    page_matches = [item.summary for item in filtered[start:end]]

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


def _dashboard_sample(item: FilteredMatch, inputs: MatchStatInputs) -> player_dashboard.MatchSample:
    """One match's contribution, derived by the SAME pure functions — under
    the same "complete record, consistent with the final score" rule — that
    `build_match_record_detail()` uses, so the dashboard can never show a
    number the match's own detail dialog would disagree with (FR-003). A
    match that fails the rule still counts for the final-score metrics."""
    match = item.match
    participants = [
        match_stats.Participant(uuid.UUID(p.roster_entry_id), p.team)
        for p in item.summary.team_a + item.summary.team_b
    ]
    points = (
        match_stats.effective_points(inputs.raw_events, match.score_a, match.score_b)
        if inputs.completeness == "complete"
        else None
    )
    mine_is_a = item.my_team == "A"
    return player_dashboard.build_sample(
        ended_at=cast(datetime, match.ended_at),  # always set for completed matches
        won=item.won,
        points_for=match.score_a if mine_is_a else match.score_b,
        points_against=match.score_b if mine_is_a else match.score_a,
        my_team=item.my_team,
        my_entry_id=item.my_entry_id,
        is_doubles=len(participants) > 2,
        clutch=(
            match_stats.clutch_stats(points, match.target_score, match.cap_score)
            if points is not None
            else None
        ),
        serve=(
            match_stats.serve_stats(points, inputs.snapshots, participants)
            if points is not None
            else None
        ),
        landings=(
            match_stats.player_landings(points, inputs.placements, participants)
            if points is not None
            else None
        ),
    )


async def build_member_match_dashboard(
    session: AsyncSession, member_id: uuid.UUID, filters: MemberMatchFilters
) -> MemberMatchDashboardResponse:
    """034-clutch-points-player-dashboard US2-US4: the member's cross-match
    technique dashboard over exactly the matches `build_member_match_records()`
    would list under the same `filters` — the whole filtered set, never a
    page (FR-019). A separate endpoint rather than more fields on that
    response because this one reads every match's point log: it is fetched
    once per filter change, not once per page flip (research.md Decision 5).
    Query count is constant in the number of matches (Decision 7)."""
    filtered = await _filtered_member_matches(session, member_id, filters)
    inputs = await load_match_stat_inputs(session, [item.match for item in filtered])
    result = player_dashboard.aggregate(
        [_dashboard_sample(item, inputs[item.match.id]) for item in filtered]
    )
    return MemberMatchDashboardResponse.model_validate(asdict(result))


async def get_member_group_history(
    session: AsyncSession,
    member_id: uuid.UUID,
    group_id: uuid.UUID,
    page: int = 1,
    *,
    nickname: str | None = None,
    round_from: int | None = None,
    round_to: int | None = None,
    group1_names: list[str] | None = None,
    group2_names: list[str] | None = None,
    score_a_cmp: Literal["gt", "eq", "lt"] | None = None,
    score_a: int | None = None,
    score_b_cmp: Literal["gt", "eq", "lt"] | None = None,
    score_b: int | None = None,
) -> MemberGroupHistoryResponse:
    """014-member-groups-history follow-up: `matches` is the group's own
    shared match history — EVERY completed match, regardless of who played
    in it (reuses `build_group_match_records()`, extended with a generic
    `nickname` search across either team, FR-004/FR-009) — while `my_stats`
    is this member's own performance in the group (reuses
    `build_member_match_records(group_id=...)` unfiltered, FR-005). The two
    intentionally use different queries: a group-wide match list has no
    single "my team" — `group1_names`/`group2_names` search for a "this
    group of people vs. that group of people" matchup regardless of which
    literal on-court side (A or B) either group landed on (see
    `build_group_match_records()`'s docstring), and `score_a_cmp`+
    `score_a`/`score_b_cmp`+`score_b` compare each literal side's own
    score. None of this is a "my team vs. opponent" perspective, so the
    nickname search and all of these mean "does this match involve/look
    like this at all," never "was this player my opponent."

    All advanced filters above are passed straight through to
    `build_group_match_records()` and never applied to `my_stats`, which
    stays this member's full unfiltered history. Errors: `GROUP_NOT_FOUND`,
    `GROUP_MEMBERSHIP_NEVER_HELD`."""
    group = await get_group_by_id(session, group_id)
    await verify_ever_group_member(session, group_id, member_id)

    match_records = await build_group_match_records(
        session,
        group_id,
        page,
        nickname=nickname,
        round_from=round_from,
        round_to=round_to,
        group1_names=group1_names,
        group2_names=group2_names,
        score_a_cmp=score_a_cmp,
        score_a=score_a,
        score_b_cmp=score_b_cmp,
        score_b=score_b,
    )
    member_records = await build_member_match_records(session, member_id, group_id=group_id)
    final_standings = await build_group_final_standings(
        session, group_id, viewer_member_id=member_id
    )

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
        final_standings=final_standings,
        matches=match_records.matches,
        page=match_records.page,
        total_pages=match_records.total_pages,
        player_records=match_records.player_records,
    )


async def get_member_match_record_detail(
    session: AsyncSession, member_id: uuid.UUID, match_id: uuid.UUID
) -> MatchRecordDetailResponse:
    """016-match-score-timeline US1/US2/US3 (FR-001~008): serves both the
    member's cross-group `/members/me/match-records` list and the
    `/members/me/groups/{group_id}/history` list — both are a logged-in
    member viewing a match they already have "ever member" access to, so
    both share this one function/endpoint (research.md #1). Deliberately
    reuses `verify_ever_group_member()` (the SAME check
    `get_member_group_history()` above already uses), not the stricter
    active-membership `resolve_active_roster_membership()` used by the
    group-scoped `/groups/{group_id}/match-records/{match_id}` sibling
    endpoint — a member who left/was kicked from the group MUST still be
    able to view this. Errors: `MATCH_NOT_FOUND`, `GROUP_MEMBERSHIP_NEVER_HELD`."""
    match = await get_completed_match_or_404(session, match_id)
    await verify_ever_group_member(session, match.group_id, member_id)
    return await build_match_record_detail(session, match)


async def search_member(
    session: AsyncSession, user_number: str, requester_id: uuid.UUID
) -> SearchMemberResponse:
    """FR-038: case-insensitive user_number lookup. Errors: `MEMBER_NOT_FOUND`
    (also covers an unverified target account, FR-036; a deleted account,
    025-delete-account; and — 022-member-personal-settings FR-017 — a
    verified target who has closed `allow_search`, deliberately
    indistinguishable from "doesn't exist" so a hidden/deleted account's
    existence is never leaked), `CANNOT_SEARCH_SELF` (FR-037, checked after
    existence so a self-search still surfaces as its own distinct code
    rather than the generic not-found, regardless of the searcher's own
    `allow_search` value)."""
    result = await session.execute(
        select(Member).where(func.lower(Member.user_number) == user_number.lower())
    )
    target = result.scalar_one_or_none()
    if target is None or target.verification_status != "verified" or target.deleted_at is not None:
        raise ApiError("MEMBER_NOT_FOUND", status_code=404)
    if target.id == requester_id:
        raise ApiError("CANNOT_SEARCH_SELF", status_code=400)
    if not target.allow_search:
        raise ApiError("MEMBER_NOT_FOUND", status_code=404)

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
        select(
            Group.id,
            Group.group_number,
            Group.name,
            Group.status,
            Group.created_at,
            Group.disbanded_at,
        )
        .where(Group.id.in_(all_group_ids))
        .order_by(Group.created_at.desc())
    )
    groups = [
        MyGroupSummary(
            group_id=str(row.id),
            group_number=row.group_number,
            name=row.name,
            status=row.status,
            created_at=row.created_at,
            disbanded_at=row.disbanded_at,
            is_creator=row.id in created_group_ids,
            member_status=member_status_by_group[row.id],
        )
        for row in result.all()
    ]
    return MyGroupsResponse(groups=groups)
