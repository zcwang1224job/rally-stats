"""Contract test for POST /members/me/delete, per
contracts/delete-account-api.md (025-delete-account)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, email: str, password: str = "abc12345") -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    return str(response.json()["access_token"])


async def test_delete_account_succeeds(client: AsyncClient, db_session: AsyncSession) -> None:
    await register(db_session, "deleteapi1@example.com", "abc12345")
    access_token = await _login(client, "deleteapi1@example.com")

    response = await client.post(
        "/members/me/delete",
        json={"current_password": "abc12345"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": True}


async def test_delete_account_rejects_wrong_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "deleteapi2@example.com", "abc12345")
    access_token = await _login(client, "deleteapi2@example.com")

    response = await client.post(
        "/members/me/delete",
        json={"current_password": "wrong-password"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "CURRENT_PASSWORD_INCORRECT"


async def test_delete_account_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/members/me/delete", json={"current_password": "abc12345"})

    assert response.status_code == 401


async def test_delete_account_succeeds_for_unverified_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """FR: an unverified member can still delete their own account —
    deliberately `require_member`, not `require_verified_member`."""
    await register(db_session, "deleteapi3@example.com", "abc12345")
    access_token = await _login(client, "deleteapi3@example.com")

    response = await client.post(
        "/members/me/delete",
        json={"current_password": "abc12345"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200


async def test_login_fails_after_account_deletion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "deleteapi4@example.com", "abc12345")
    access_token = await _login(client, "deleteapi4@example.com")
    await client.post(
        "/members/me/delete",
        json={"current_password": "abc12345"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response = await client.post(
        "/auth/login", json={"email": "deleteapi4@example.com", "password": "abc12345"}
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


async def test_existing_session_token_invalid_after_account_deletion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "deleteapi5@example.com", "abc12345")
    access_token = await _login(client, "deleteapi5@example.com")
    await client.post(
        "/members/me/delete",
        json={"current_password": "abc12345"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response = await client.get("/members/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 401
    assert response.json()["error_code"] == "MEMBER_TOKEN_INVALID"


async def test_freed_email_can_be_reused_for_new_registration(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    await register(db_session, "deleteapi6@example.com", "abc12345")
    access_token = await _login(client, "deleteapi6@example.com")
    await client.post(
        "/members/me/delete",
        json={"current_password": "abc12345"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response = await client.post(
        "/auth/register",
        json={
            "email": "deleteapi6@example.com",
            "password": "abc12345",
            "confirm_password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )

    assert response.status_code == 201
    result = await db_session.execute(
        select(Member).where(Member.email == "deleteapi6@example.com")
    )
    matches = result.scalars().all()
    assert len(matches) == 1
    assert matches[0].verification_status == "unverified"
