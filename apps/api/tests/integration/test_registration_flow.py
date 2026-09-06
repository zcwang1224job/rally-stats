"""Integration test: register -> LoggingEmailSender captures the
verification link -> call verification endpoint -> verification_status
becomes verified -> GET /members/me returns nickname: null (US1)."""

import re

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_full_registration_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="app.core.email"):
        register_response = await client.post(
            "/auth/register",
            json={
                "email": "fullflow@example.com",
                "password": "abc12345",
                "confirm_password": "abc12345",
                "turnstile_token": valid_turnstile_token,
            },
        )
    assert register_response.status_code == 201

    log_text = "\n".join(record.message for record in caplog.records)
    match = re.search(r"/auth/verify-email/([0-9a-f-]{36})", log_text)
    assert match is not None, "verification link not found in LoggingEmailSender output"
    token = match.group(1)

    verify_response = await client.get(f"/auth/verify-email/{token}")
    assert verify_response.status_code == 200
    assert verify_response.json()["verified"] is True

    login_response = await client.post(
        "/auth/login", json={"email": "fullflow@example.com", "password": "abc12345"}
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    me_response = await client.get(
        "/members/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me_response.status_code == 200
    body = me_response.json()
    assert body["verification_status"] == "verified"
    assert body["nickname"] is None
