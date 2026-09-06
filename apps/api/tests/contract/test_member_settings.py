"""Contract test for PATCH /members/me/nickname, PATCH /members/me/password
per contracts/member-api.md."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_and_verify(session: AsyncSession, email: str) -> Member:
    """Personal settings are locked until verified (constitution IV, FR-009)."""
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    await session.commit()
    return member


async def _login(client: AsyncClient, email: str, password: str = "abc12345") -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    return str(response.json()["access_token"])


async def test_set_nickname_succeeds(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register_and_verify(db_session, "settingsc1@example.com")
    access_token = await _login(client, "settingsc1@example.com")

    response = await client.patch(
        "/members/me/nickname",
        json={"nickname": "新暱稱"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["nickname"] == "新暱稱"


async def test_set_nickname_rejects_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register_and_verify(db_session, "settingsc2@example.com")
    access_token = await _login(client, "settingsc2@example.com")

    response = await client.patch(
        "/members/me/nickname",
        json={"nickname": "   "},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 422


async def test_set_nickname_rejects_unverified_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "settingsc5@example.com", "abc12345")
    access_token = await _login(client, "settingsc5@example.com")

    response = await client.patch(
        "/members/me/nickname",
        json={"nickname": "新暱稱"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


async def test_change_password_succeeds(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register_and_verify(db_session, "settingsc3@example.com")
    access_token = await _login(client, "settingsc3@example.com")

    response = await client.patch(
        "/members/me/password",
        json={
            "current_password": "abc12345",
            "new_password": "newpass123",
            "confirm_new_password": "newpass123",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["changed"] is True
    assert response.json()["access_token"]


async def test_change_password_rejects_wrong_current_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "settingsc4@example.com")
    access_token = await _login(client, "settingsc4@example.com")

    response = await client.patch(
        "/members/me/password",
        json={
            "current_password": "totally-wrong",
            "new_password": "newpass123",
            "confirm_new_password": "newpass123",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CURRENT_PASSWORD_INCORRECT"


async def test_settings_endpoints_require_login(client: AsyncClient) -> None:
    nickname_response = await client.patch("/members/me/nickname", json={"nickname": "x"})
    assert nickname_response.status_code == 401

    password_response = await client.patch(
        "/members/me/password",
        json={
            "current_password": "a",
            "new_password": "b1234567",
            "confirm_new_password": "b1234567",
        },
    )
    assert password_response.status_code == 401
