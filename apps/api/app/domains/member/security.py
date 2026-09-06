"""Password hashing, access/refresh JWT issuance & verification, and
user_number generation. Per specs/006-member-friends/research.md #2, #3, #8.

A deliberately independent `CryptContext` from group/security.py's (module
boundary — constitution VI): the bcrypt scheme matching is coincidental, not
a shared "password rule" the two domains should stay coupled on.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import jwt
from fastapi import Depends, Header
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ApiError
from app.domains.member.models import Member

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_ALGORITHM = "HS256"

# 8-char user_number alphabet, excluding visually confusable characters
# (0/O, 1/I/l) per FR-018.
_USER_NUMBER_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"
_USER_NUMBER_LENGTH = 8
_USER_NUMBER_MAX_ATTEMPTS = 10


def hash_password(password: str) -> str:
    return str(_pwd_context.hash(password))


def verify_password(password: str, password_hash: str) -> bool:
    return bool(_pwd_context.verify(password, password_hash))


def _generate_user_number_candidate() -> str:
    return "".join(secrets.choice(_USER_NUMBER_ALPHABET) for _ in range(_USER_NUMBER_LENGTH))


async def generate_unique_user_number(session: AsyncSession) -> str:
    """FR-019: retry on collision (checked case-insensitively, matching the
    `ux_members_user_number_ci` index); the DB unique index is the final
    guarantee, this is a pre-check to avoid a near-certain wasted INSERT."""
    for _ in range(_USER_NUMBER_MAX_ATTEMPTS):
        candidate = _generate_user_number_candidate()
        result = await session.execute(
            select(Member.id).where(Member.user_number.ilike(candidate))
        )
        if result.scalar_one_or_none() is None:
            return candidate
    raise RuntimeError("Failed to generate a unique user_number after max attempts")


def _issue_token(
    member_id: str, token_version: int, *, token_type: Literal["access", "refresh"]
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.member_access_token_ttl_minutes)
        if token_type == "access"
        else timedelta(days=settings.member_refresh_token_ttl_days)
    )
    payload = {
        "member_id": member_id,
        "token_version": token_version,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def issue_access_token(member_id: str, token_version: int) -> str:
    return _issue_token(member_id, token_version, token_type="access")


def issue_refresh_token(member_id: str, token_version: int) -> str:
    return _issue_token(member_id, token_version, token_type="refresh")


def _decode_token(token: str, *, expected_type: Literal["access", "refresh"]) -> dict[str, object]:
    settings = get_settings()
    error_code = "MEMBER_TOKEN_INVALID" if expected_type == "access" else "REFRESH_TOKEN_INVALID"
    try:
        payload = dict(jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM]))
    except jwt.PyJWTError as exc:
        raise ApiError(error_code, status_code=401) from exc
    if payload.get("type") != expected_type:
        raise ApiError(error_code, status_code=401)
    return payload


async def _load_member_for_token(
    session: AsyncSession, payload: dict[str, object], *, error_code: str
) -> Member:
    result = await session.execute(select(Member).where(Member.id == payload["member_id"]))
    member = result.scalar_one_or_none()
    if member is None or member.token_version != payload["token_version"]:
        raise ApiError(error_code, status_code=401)
    return member


async def refresh_access_token(session: AsyncSession, refresh_token: str) -> str:
    payload = _decode_token(refresh_token, expected_type="refresh")
    member = await _load_member_for_token(session, payload, error_code="REFRESH_TOKEN_INVALID")
    return issue_access_token(str(member.id), member.token_version)


async def require_member(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> Member:
    """FastAPI dependency: validates the Bearer access token. Does NOT
    require `verification_status == 'verified'` — unverified members may
    still hit endpoints that only need identity (e.g. resend-verification,
    GET /members/me) per FR-009's "登入僅顯示驗證提示" behavior."""
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError("MEMBER_TOKEN_INVALID", status_code=401)
    token = authorization.removeprefix("Bearer ")
    payload = _decode_token(token, expected_type="access")
    return await _load_member_for_token(session, payload, error_code="MEMBER_TOKEN_INVALID")


async def require_verified_member(
    member: Annotated[Member, Depends(require_member)],
) -> Member:
    """FR-009: full functionality is locked until `verification_status ==
    'verified'`. Layered on top of `require_member` rather than duplicating
    the token-validation logic."""
    if member.verification_status != "verified":
        raise ApiError("EMAIL_NOT_VERIFIED", status_code=403)
    return member


async def optional_member(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> Member | None:
    """FastAPI dependency for endpoints where login is a bonus, not a
    requirement (public group browsing/join per 004 research.md #2; also
    closes 001's `create_group` gap — a missing, malformed, or expired token
    is treated as "anonymous", not an error, unlike `require_member`."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        payload = _decode_token(token, expected_type="access")
        return await _load_member_for_token(session, payload, error_code="MEMBER_TOKEN_INVALID")
    except ApiError:
        return None
