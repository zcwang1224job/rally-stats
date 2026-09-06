"""Integration test: two devices logged in -> forgot-password reset -> both
devices' old tokens invalidated -> must log in again with the new
password (US2 acceptance scenario 1)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import PasswordResetToken
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def test_forgot_password_invalidates_all_devices(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "twodevices@example.com", "abc12345")

    device_a = (
        await client.post(
            "/auth/login", json={"email": "twodevices@example.com", "password": "abc12345"}
        )
    ).json()
    device_b = (
        await client.post(
            "/auth/login", json={"email": "twodevices@example.com", "password": "abc12345"}
        )
    ).json()

    await client.post("/auth/forgot-password", json={"email": "twodevices@example.com"})
    result = await db_session.execute(select(PasswordResetToken))
    token = result.scalars().first()
    reset_response = await client.post(
        f"/auth/reset-password/{token.token}",
        json={"new_password": "brandnew123", "confirm_new_password": "brandnew123"},
    )
    assert reset_response.status_code == 200

    for device in (device_a, device_b):
        me_response = await client.get(
            "/members/me", headers={"Authorization": f"Bearer {device['access_token']}"}
        )
        assert me_response.status_code == 401
        assert me_response.json()["error_code"] == "MEMBER_TOKEN_INVALID"

    relogin_response = await client.post(
        "/auth/login", json={"email": "twodevices@example.com", "password": "brandnew123"}
    )
    assert relogin_response.status_code == 200

    old_password_response = await client.post(
        "/auth/login", json={"email": "twodevices@example.com", "password": "abc12345"}
    )
    assert old_password_response.status_code == 401
