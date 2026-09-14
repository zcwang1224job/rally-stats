"""024-add-english-language FR-010/SC-001a: transactional emails (account
verification, password reset) MUST follow the recipient member's
`language_preference` — English text when it's `"en"`, the existing Chinese
text when `"zh-TW"`, and the existing Chinese text as a safe fallback for
any unrecognized/legacy value."""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member import service
from app.domains.member.service import forgot_password, register, set_language_preference

pytestmark = pytest.mark.asyncio


def _capture_sent_emails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def _fake_send_email(to: str, subject: str, body: str) -> None:
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(service, "send_email", _fake_send_email)
    return sent


async def test_verification_email_is_english_when_preference_is_en(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = await register(db_session, "verify-en@example.com", "abc12345")
    member.language_preference = "en"
    await db_session.commit()
    sent = _capture_sent_emails(monkeypatch)

    await service._issue_verification_token_and_email(db_session, member)

    assert len(sent) == 1
    assert sent[0]["subject"] == "Verify your email"
    assert "verify your email" in sent[0]["body"].lower()
    assert "請驗證" not in sent[0]["body"]


async def test_verification_email_is_chinese_when_preference_is_zh_tw(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _capture_sent_emails(monkeypatch)

    await register(db_session, "verify-zh@example.com", "abc12345")

    assert len(sent) == 1
    assert sent[0]["subject"] == "請驗證你的信箱"
    assert "請點擊以下連結完成信箱驗證" in sent[0]["body"]


async def test_password_reset_email_is_english_when_preference_is_en(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = await register(db_session, "reset-en@example.com", "abc12345")
    member.verification_status = "verified"
    await db_session.commit()
    await set_language_preference(db_session, member, "en")
    sent = _capture_sent_emails(monkeypatch)

    await forgot_password(db_session, "reset-en@example.com")

    assert len(sent) == 1
    assert sent[0]["subject"] == "Reset your password"
    assert "reset your password" in sent[0]["body"].lower()
    assert "重設密碼" not in sent[0]["body"]


async def test_password_reset_email_is_chinese_when_preference_is_zh_tw(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register(db_session, "reset-zh@example.com", "abc12345")
    sent = _capture_sent_emails(monkeypatch)

    await forgot_password(db_session, "reset-zh@example.com")

    assert len(sent) == 1
    assert sent[0]["subject"] == "重設密碼"
    assert "請點擊以下連結重設密碼" in sent[0]["body"]


async def test_verification_email_falls_back_to_chinese_for_unrecognized_preference(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy/unexpected `language_preference` value MUST NOT raise or
    silently fall back to English — the safe default is the existing
    Chinese text (research.md #4)."""
    sent = _capture_sent_emails(monkeypatch)

    member = await register(db_session, "verify-legacy@example.com", "abc12345")
    member.language_preference = "fr"  # unsupported/legacy value
    await db_session.commit()
    sent.clear()

    await service._issue_verification_token_and_email(db_session, member)

    assert len(sent) == 1
    assert sent[0]["subject"] == "請驗證你的信箱"
