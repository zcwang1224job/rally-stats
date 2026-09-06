"""Integration test: the full member lifecycle end-to-end through the real
HTTP layer — 註冊 → 驗證信 → 完成驗證 → 設定暱稱 → 登入 → 修改密碼 →
其他裝置 session 失效 (specs/006-member-friends, Constitution Principle II
requires at least one end-to-end test for this critical flow, not just
per-endpoint contract tests)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import EmailVerificationToken, Member

pytestmark = pytest.mark.asyncio


async def test_full_member_lifecycle(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    email = "lifecycle@example.com"
    password = "abc12345"

    # 註冊
    register_response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "confirm_password": password,
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == email

    member_result = await db_session.execute(select(Member).where(Member.email == email))
    member = member_result.scalar_one()
    assert member.verification_status == "unverified"

    # 驗證信 → 完成驗證
    token_result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    verification_token = token_result.scalar_one()
    verify_response = await client.get(f"/auth/verify-email/{verification_token.token}")
    assert verify_response.status_code == 200
    assert verify_response.json()["verified"] is True

    # 登入（device A）→ 設定暱稱
    login_a = await client.post("/auth/login", json={"email": email, "password": password})
    assert login_a.status_code == 200
    access_token_a = login_a.json()["access_token"]

    nickname_response = await client.patch(
        "/members/me/nickname",
        json={"nickname": "生命週期測試"},
        headers={"Authorization": f"Bearer {access_token_a}"},
    )
    assert nickname_response.status_code == 200
    assert nickname_response.json()["nickname"] == "生命週期測試"

    # 登入（device B，另一台裝置）
    login_b = await client.post("/auth/login", json={"email": email, "password": password})
    assert login_b.status_code == 200
    access_token_b = login_b.json()["access_token"]

    # 修改密碼（在 device A 上操作）
    change_password_response = await client.patch(
        "/members/me/password",
        json={
            "current_password": password,
            "new_password": "newpass456",
            "confirm_new_password": "newpass456",
        },
        headers={"Authorization": f"Bearer {access_token_a}"},
    )
    assert change_password_response.status_code == 200
    new_access_token_a = change_password_response.json()["access_token"]

    # device A 的新 token 仍然有效
    me_a = await client.get(
        "/members/me", headers={"Authorization": f"Bearer {new_access_token_a}"}
    )
    assert me_a.status_code == 200
    assert me_a.json()["nickname"] == "生命週期測試"

    # device B 的舊 token 已失效
    me_b = await client.get("/members/me", headers={"Authorization": f"Bearer {access_token_b}"})
    assert me_b.status_code == 401
    assert me_b.json()["error_code"] == "MEMBER_TOKEN_INVALID"

    # 用新密碼可以重新登入；舊密碼不再有效
    relogin = await client.post(
        "/auth/login", json={"email": email, "password": "newpass456"}
    )
    assert relogin.status_code == 200

    old_password_login = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert old_password_login.status_code == 401
