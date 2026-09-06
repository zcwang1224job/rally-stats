"""Admin PIN hashing/generation, reversible group-password encryption (AES-256-GCM),
and admin JWT issuance/verification. Per specs/001-create-manage-group/research.md #2, #3."""

import base64
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, Header
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ApiError
from app.domains.group.models import Group

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_ALGORITHM = "HS256"


def generate_admin_pin() -> str:
    """6-digit numeric PIN, digits only (spec FR-008 clarification)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_admin_pin(pin: str) -> str:
    return str(_pwd_context.hash(pin))


def verify_admin_pin(pin: str, pin_hash: str) -> bool:
    return bool(_pwd_context.verify(pin, pin_hash))


def _get_aesgcm() -> AESGCM:
    key = base64.b64decode(get_settings().password_encryption_key)
    return AESGCM(key)


def encrypt_group_password(plaintext: str) -> tuple[bytes, bytes]:
    """Returns (ciphertext, nonce). Reversible — group passwords must be viewable
    by the admin, unlike admin PINs which are one-way hashed."""
    aesgcm = _get_aesgcm()
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_group_password(ciphertext: bytes, nonce: bytes) -> str:
    aesgcm = _get_aesgcm()
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def issue_admin_token(group_id: str, admin_token_version: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "group_id": group_id,
        "admin_token_version": admin_token_version,
        "iat": now,
        "exp": now + timedelta(hours=settings.admin_token_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_admin_token(token: str) -> dict[str, object]:
    settings = get_settings()
    try:
        return dict(jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM]))
    except jwt.PyJWTError as exc:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401) from exc


async def require_admin(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> Group:
    """FastAPI dependency: validates the Bearer admin token, including the
    admin_token_version comparison that makes PIN regeneration immediately
    invalidate old tokens (spec FR-026/FR-027)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    token = authorization.removeprefix("Bearer ")
    payload = decode_admin_token(token)

    result = await session.execute(select(Group).where(Group.id == payload["group_id"]))
    group = result.scalar_one_or_none()
    if group is None:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    if group.admin_token_version != payload["admin_token_version"]:
        raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)
    return group
