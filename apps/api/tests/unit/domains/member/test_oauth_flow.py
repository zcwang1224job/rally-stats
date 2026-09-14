"""Unit tests for `start_oauth_flow()`/`complete_oauth_callback()` —
specs/027-google-line-oauth-login. `exchange_code_for_profile()` (the only
thing that actually talks to Google/LINE) is monkeypatched throughout, so
every test here exercises real business logic against a real test DB
without any live network calls."""

import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domains.member import service
from app.domains.member.models import EmailVerificationToken, Member, MemberOAuthIdentity
from app.domains.member.oauth_client import OAuthProfile
from app.domains.member.oauth_providers import get_provider_config
from app.domains.member.security import decode_oauth_state, hash_password, issue_oauth_state
from app.domains.member.service import complete_oauth_callback, start_oauth_flow

pytestmark = pytest.mark.asyncio

_FakeExchange = Callable[..., Awaitable[OAuthProfile]]


def _make_fake_exchange(profile: OAuthProfile) -> _FakeExchange:
    async def _fake(config: object, **_kwargs: object) -> OAuthProfile:
        return profile

    return _fake


async def _make_member(session: AsyncSession, email: str) -> Member:
    member = Member(
        email=email, password_hash=hash_password("abc12345"), user_number=secrets.token_hex(4)
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


def _login_state(provider: str = "google") -> str:
    return issue_oauth_state(provider=provider, intent="login", code_verifier="v", nonce="n")


# --- T011: start_oauth_flow() -----------------------------------------


async def test_start_oauth_flow_builds_authorize_url_with_pkce_and_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-google-client-id")
    get_settings.cache_clear()
    try:
        url = await start_oauth_flow("google", "login")
    finally:
        get_settings.cache_clear()

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["test-google-client-id"]
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge_method"] == ["S256"]
    assert "code_challenge" in qs
    assert "redirect_uri" in qs
    assert "state" in qs

    decoded = decode_oauth_state(qs["state"][0])
    assert decoded.provider == "google"
    assert decoded.intent == "login"
    assert decoded.member_id is None


async def test_start_oauth_flow_link_intent_carries_member_id() -> None:
    url = await start_oauth_flow("line", "link", member_id="11111111-1111-1111-1111-111111111111")
    qs = parse_qs(urlparse(url).query)
    decoded = decode_oauth_state(qs["state"][0])
    assert decoded.intent == "link"
    assert decoded.member_id == "11111111-1111-1111-1111-111111111111"


# --- T012: new-member success path -------------------------------------


async def test_new_member_created_verified_no_verification_email(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = OAuthProfile(sub="google-sub-1", email="newmember@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "google", code="auth-code", state=_login_state(), error=None
    )

    assert result.status == "success"
    assert result.is_new_member is True
    assert result.access_token
    assert result.refresh_token

    member = (
        await db_session.execute(select(Member).where(Member.email == "newmember@example.com"))
    ).scalar_one()
    assert member.verification_status == "verified"
    assert member.password_hash is None

    identity = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.member_id == member.id)
        )
    ).scalar_one()
    assert identity.provider == "google"
    assert identity.provider_user_id == "google-sub-1"

    # research.md #6: no verification email — the OAuth authorization
    # itself is the trust signal, no EmailVerificationToken is ever issued.
    token = (
        await db_session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
        )
    ).scalar_one_or_none()
    assert token is None


# --- T013: returning-member path (FR-003) -------------------------------


async def test_returning_member_logs_in_without_creating_duplicate(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = await _make_member(db_session, "returning@example.com")
    db_session.add(
        MemberOAuthIdentity(
            member_id=existing.id, provider="google", provider_user_id="google-sub-2"
        )
    )
    await db_session.commit()

    profile = OAuthProfile(sub="google-sub-2", email="returning@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "google", code="c", state=_login_state(), error=None
    )

    assert result.status == "success"
    assert result.is_new_member is False

    members = (
        await db_session.execute(select(Member).where(Member.email == "returning@example.com"))
    ).scalars().all()
    assert len(members) == 1

    identities = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.member_id == existing.id)
        )
    ).scalars().all()
    assert len(identities) == 1


# --- T014: cancel/deny + state-invalid -----------------------------------


async def test_cancel_on_provider_screen_creates_nothing(db_session: AsyncSession) -> None:
    result = await complete_oauth_callback(
        db_session, "google", code=None, state=_login_state(), error="access_denied"
    )
    assert result.status == "cancelled"

    count = (await db_session.execute(select(Member))).scalars().all()
    assert count == []


async def test_missing_state_is_rejected(db_session: AsyncSession) -> None:
    result = await complete_oauth_callback(db_session, "google", code="c", state=None, error=None)
    assert result.status == "error"
    assert result.error_code == "OAUTH_STATE_INVALID"


async def test_tampered_state_is_rejected(db_session: AsyncSession) -> None:
    result = await complete_oauth_callback(
        db_session, "google", code="c", state="not-a-real-jwt", error=None
    )
    assert result.status == "error"
    assert result.error_code == "OAUTH_STATE_INVALID"


async def test_state_provider_mismatch_is_rejected(db_session: AsyncSession) -> None:
    """A `state` minted for google presented on the line callback route."""
    result = await complete_oauth_callback(
        db_session, "line", code="c", state=_login_state(provider="google"), error=None
    )
    assert result.status == "error"
    assert result.error_code == "OAUTH_STATE_INVALID"


# --- T015: FR-005 email-collision path (/speckit-analyze E1) -------------


async def test_email_collision_with_existing_password_member_is_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _make_member(db_session, "collide@example.com")
    profile = OAuthProfile(sub="google-sub-3", email="collide@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "google", code="c", state=_login_state(), error=None
    )

    assert result.status == "error"
    assert result.error_code == "OAUTH_EMAIL_ALREADY_REGISTERED"
    identity = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(
                MemberOAuthIdentity.provider_user_id == "google-sub-3"
            )
        )
    ).scalar_one_or_none()
    assert identity is None


async def test_email_collision_with_existing_oauth_only_member_is_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_profile = OAuthProfile(sub="line-sub-1", email="oauthonly@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(first_profile))
    first = await complete_oauth_callback(
        db_session, "line", code="c", state=_login_state(provider="line"), error=None
    )
    assert first.status == "success"

    second_profile = OAuthProfile(sub="google-sub-4", email="oauthonly@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(second_profile))
    result = await complete_oauth_callback(
        db_session, "google", code="c", state=_login_state(), error=None
    )

    assert result.status == "error"
    assert result.error_code == "OAUTH_EMAIL_ALREADY_REGISTERED"


async def test_line_profile_without_email_skips_collision_check(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = OAuthProfile(sub="line-sub-2", email=None)
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "line", code="c", state=_login_state(provider="line"), error=None
    )

    assert result.status == "success"
    assert result.is_new_member is True


# --- T027/T028 (US2): LINE with email behaves the same as Google ---------


async def test_line_profile_with_email_creates_verified_member(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = OAuthProfile(sub="line-sub-3", email="lineemail@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "line", code="c", state=_login_state(provider="line"), error=None
    )

    assert result.status == "success"
    assert result.is_new_member is True
    member = (
        await db_session.execute(select(Member).where(Member.email == "lineemail@example.com"))
    ).scalar_one()
    assert member.verification_status == "verified"


# --- T016: FR-011 deleted-account path (/speckit-analyze E2) -------------


async def test_deleted_account_login_is_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = await _make_member(db_session, "deleted@example.com")
    db_session.add(
        MemberOAuthIdentity(member_id=member.id, provider="google", provider_user_id="google-sub-5")
    )
    member.deleted_at = datetime.now(UTC)
    await db_session.commit()

    profile = OAuthProfile(sub="google-sub-5", email="deleted@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "google", code="c", state=_login_state(), error=None
    )

    assert result.status == "error"
    assert result.error_code == "ACCOUNT_DELETED"
    assert result.access_token is None


# --- T017: concurrent-duplicate race condition (/speckit-analyze E3) -----


async def test_concurrent_identity_creation_is_translated_to_clean_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates a race: another request already committed the binding for
    this exact (provider, sub) between our own `_find_oauth_identity()`
    check and our write — forced here by monkeypatching that check to
    report "not found" despite a real conflicting row already existing, so
    the write itself MUST hit the DB's unique constraint."""
    winner = await _make_member(db_session, "race-winner@example.com")
    db_session.add(
        MemberOAuthIdentity(member_id=winner.id, provider="google", provider_user_id="race-sub")
    )
    await db_session.commit()

    monkeypatch.setattr(service, "_find_oauth_identity", AsyncMock(return_value=None))
    profile = OAuthProfile(sub="race-sub", email=None)
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "google", code="c", state=_login_state(), error=None
    )

    assert result.status == "error"
    assert result.error_code == "OAUTH_IDENTITY_ALREADY_LINKED"


# --- T024/T027 (US2): provider config sanity ------------------------------


async def test_google_provider_config_shape() -> None:
    config = get_provider_config("google")
    assert config.authorize_url == "https://accounts.google.com/o/oauth2/v2/auth"
    assert config.token_url == "https://oauth2.googleapis.com/token"
    assert "openid" in config.scopes
    assert "email" in config.scopes


async def test_line_provider_config_shape() -> None:
    config = get_provider_config("line")
    assert config.authorize_url == "https://access.line.me/oauth2/v2.1/authorize"
    assert config.jwks_url.startswith("https://api.line.me/")
    assert "openid" in config.scopes


# --- T032 (US3): complete_oauth_callback() intent=link -------------------


def _link_state(member_id: str, provider: str = "google") -> str:
    return issue_oauth_state(
        provider=provider, intent="link", code_verifier="v", nonce="n", member_id=member_id
    )


async def test_link_success_creates_binding(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    caller = await _make_member(db_session, "linkcaller1@example.com")
    profile = OAuthProfile(sub="link-sub-1", email="external1@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "google", code="c", state=_link_state(str(caller.id)), error=None
    )

    assert result.status == "success"
    assert result.intent == "link"
    identity = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.member_id == caller.id)
        )
    ).scalar_one()
    assert identity.provider == "google"
    assert identity.provider_user_id == "link-sub-1"


async def test_link_repeat_by_same_caller_is_idempotent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    caller = await _make_member(db_session, "linkcaller2@example.com")
    db_session.add(
        MemberOAuthIdentity(member_id=caller.id, provider="google", provider_user_id="link-sub-2")
    )
    await db_session.commit()

    profile = OAuthProfile(sub="link-sub-2", email="external2@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "google", code="c", state=_link_state(str(caller.id)), error=None
    )

    assert result.status == "success"
    identities = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.member_id == caller.id)
        )
    ).scalars().all()
    assert len(identities) == 1


async def test_link_already_bound_to_another_member_is_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_member(db_session, "linkowner@example.com")
    caller = await _make_member(db_session, "linkcaller3@example.com")
    db_session.add(
        MemberOAuthIdentity(member_id=owner.id, provider="google", provider_user_id="link-sub-3")
    )
    await db_session.commit()

    profile = OAuthProfile(sub="link-sub-3", email="external3@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "google", code="c", state=_link_state(str(caller.id)), error=None
    )

    assert result.status == "error"
    assert result.error_code == "OAUTH_IDENTITY_ALREADY_LINKED"
    # existing binding to the original owner is untouched
    identity = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.provider_user_id == "link-sub-3")
        )
    ).scalar_one()
    assert identity.member_id == owner.id


async def test_link_second_different_account_same_provider_is_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/speckit-analyze 2026-09-14 remediation, finding C1: FR-006's
    "second different account for an already-linked provider" branch."""
    caller = await _make_member(db_session, "linkcaller4@example.com")
    db_session.add(
        MemberOAuthIdentity(member_id=caller.id, provider="google", provider_user_id="link-sub-4a")
    )
    await db_session.commit()

    profile = OAuthProfile(sub="link-sub-4b", email="external4b@example.com")
    monkeypatch.setattr(service, "exchange_code_for_profile", _make_fake_exchange(profile))

    result = await complete_oauth_callback(
        db_session, "google", code="c", state=_link_state(str(caller.id)), error=None
    )

    assert result.status == "error"
    assert result.error_code == "OAUTH_PROVIDER_ALREADY_LINKED"
    identities = (
        await db_session.execute(
            select(MemberOAuthIdentity).where(MemberOAuthIdentity.member_id == caller.id)
        )
    ).scalars().all()
    assert len(identities) == 1
    assert identities[0].provider_user_id == "link-sub-4a"
