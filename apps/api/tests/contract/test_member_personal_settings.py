"""Contract tests for 022-member-personal-settings, per
contracts/member-settings-api.md: `GET /members/me` (new fields),
`GET /members/me/supported-languages`, `PATCH /members/me/language`,
`PATCH /members/me/privacy`, `GET /members/me/login-records`,
`GET /members/search` (privacy gate), and the two friend-viewing endpoints
`GET /members/{member_id}/match-records[/{match_id}]`."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.models import FriendRequest
from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_and_verify(session: AsyncSession, email: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    await session.commit()
    await session.refresh(member)
    return member


async def _login(client: AsyncClient, email: str, password: str = "abc12345") -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- GET /members/me — new fields (Foundational) -----------------------------


async def test_get_me_includes_personal_settings_defaults(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "foundational1@example.com")
    token = await _login(client, "foundational1@example.com")

    response = await client.get("/members/me", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["language_preference"] == "zh-TW"
    assert body["allow_search"] is True
    assert body["share_match_records_with_friends"] is True


# --- Language preference (US1) ------------------------------------------------


async def test_get_supported_languages(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register_and_verify(db_session, "lang-c1@example.com")
    token = await _login(client, "lang-c1@example.com")

    response = await client.get("/members/me/supported-languages", headers=_auth(token))

    assert response.status_code == 200
    assert response.json() == {"languages": ["zh-TW", "en"]}


async def test_get_supported_languages_requires_no_auth(client: AsyncClient) -> None:
    """024-add-english-language FR-003/FR-003a: anonymous visitors and the
    nav-shell-less court/scoreboard/control-panel routes need this list too
    — MUST succeed with no `Authorization` header at all (research.md #1)."""
    response = await client.get("/members/me/supported-languages")

    assert response.status_code == 200
    assert response.json() == {"languages": ["zh-TW", "en"]}


async def test_patch_language_accepts_supported_value(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "lang-c2@example.com")
    token = await _login(client, "lang-c2@example.com")

    response = await client.patch(
        "/members/me/language", json={"language": "zh-TW"}, headers=_auth(token)
    )

    assert response.status_code == 200
    assert response.json()["language_preference"] == "zh-TW"


async def test_patch_language_accepts_english(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """024-add-english-language: "en" is now a supported value too."""
    await _register_and_verify(db_session, "lang-en@example.com")
    token = await _login(client, "lang-en@example.com")

    response = await client.patch(
        "/members/me/language", json={"language": "en"}, headers=_auth(token)
    )

    assert response.status_code == 200
    assert response.json()["language_preference"] == "en"


async def test_patch_language_is_case_insensitive(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "lang-en-case@example.com")
    token = await _login(client, "lang-en-case@example.com")

    response = await client.patch(
        "/members/me/language", json={"language": "EN"}, headers=_auth(token)
    )

    assert response.status_code == 200
    assert response.json()["language_preference"] == "en"


async def test_patch_language_rejects_unsupported_value(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "lang-c3@example.com")
    token = await _login(client, "lang-c3@example.com")

    response = await client.patch(
        "/members/me/language", json={"language": "en-US"}, headers=_auth(token)
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "LANGUAGE_NOT_SUPPORTED"


async def test_patch_language_rejects_unverified_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "lang-c4@example.com", "abc12345")
    token = await _login(client, "lang-c4@example.com")

    response = await client.patch(
        "/members/me/language", json={"language": "zh-TW"}, headers=_auth(token)
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


# --- Login records (US2) ------------------------------------------------------


async def test_login_records_include_this_logins_own_device_and_no_ip_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "loginrec-c1@example.com")
    await _login(client, "loginrec-c1@example.com")
    token = await _login(
        client,
        "loginrec-c1@example.com",
    )

    response = await client.get("/members/me/login-records", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert len(body["records"]) == 2
    record = body["records"][0]
    assert set(record.keys()) == {"created_at", "device_category"}


async def test_login_records_reject_unverified_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "loginrec-c2@example.com", "abc12345")
    token = await _login(client, "loginrec-c2@example.com")

    response = await client.get("/members/me/login-records", headers=_auth(token))

    assert response.status_code == 403
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


# --- Privacy settings (US4) ---------------------------------------------------


async def test_patch_privacy_updates_single_field_and_returns_full_state(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "priv-c1@example.com")
    token = await _login(client, "priv-c1@example.com")

    response = await client.patch(
        "/members/me/privacy", json={"allow_search": False}, headers=_auth(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allow_search"] is False
    assert body["share_match_records_with_friends"] is True


async def test_patch_privacy_rejects_empty_body(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "priv-c2@example.com")
    token = await _login(client, "priv-c2@example.com")

    response = await client.patch("/members/me/privacy", json={}, headers=_auth(token))

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


async def test_patch_privacy_rejects_unverified_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(db_session, "priv-c3@example.com", "abc12345")
    token = await _login(client, "priv-c3@example.com")

    response = await client.patch(
        "/members/me/privacy", json={"allow_search": False}, headers=_auth(token)
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


# --- GET /members/search privacy gate (US4, FR-017) ---------------------------


async def test_search_hides_member_after_disabling_allow_search(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "search-c1@example.com")
    target = await _register_and_verify(db_session, "search-c2@example.com")
    searcher_token = await _login(client, "search-c1@example.com")
    target_token = await _login(client, "search-c2@example.com")

    found = await client.get(
        f"/members/search?user_number={target.user_number}", headers=_auth(searcher_token)
    )
    assert found.status_code == 200

    await client.patch(
        "/members/me/privacy", json={"allow_search": False}, headers=_auth(target_token)
    )

    hidden = await client.get(
        f"/members/search?user_number={target.user_number}", headers=_auth(searcher_token)
    )
    assert hidden.status_code == 404
    assert hidden.json()["error_code"] == "MEMBER_NOT_FOUND"


# --- Friend-viewing endpoints (US4, FR-018/FR-019) -----------------------------


async def _make_friendship(session: AsyncSession, member_a: Member, member_b: Member) -> None:
    session.add(
        FriendRequest(requester_id=member_a.id, addressee_id=member_b.id, status="accepted")
    )
    await session.commit()


async def test_view_match_records_rejects_self_view(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    member = await _register_and_verify(db_session, "friendview-c1@example.com")
    token = await _login(client, "friendview-c1@example.com")

    response = await client.get(f"/members/{member.id}/match-records", headers=_auth(token))

    assert response.status_code == 400
    assert response.json()["error_code"] == "SELF_VIEW_NOT_SUPPORTED"


async def test_view_match_records_rejects_non_friend(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register_and_verify(db_session, "friendview-c2@example.com")
    target = await _register_and_verify(db_session, "friendview-c3@example.com")
    token = await _login(client, "friendview-c2@example.com")

    response = await client.get(f"/members/{target.id}/match-records", headers=_auth(token))

    assert response.status_code == 403
    assert response.json()["error_code"] == "FRIENDSHIP_REQUIRED"


async def test_view_match_records_rejects_friend_when_privacy_disabled(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    viewer = await _register_and_verify(db_session, "friendview-c4@example.com")
    target = await _register_and_verify(db_session, "friendview-c5@example.com")
    await _make_friendship(db_session, viewer, target)
    token = await _login(client, "friendview-c4@example.com")
    target_token = await _login(client, "friendview-c5@example.com")
    await client.patch(
        "/members/me/privacy",
        json={"share_match_records_with_friends": False},
        headers=_auth(target_token),
    )

    response = await client.get(f"/members/{target.id}/match-records", headers=_auth(token))

    assert response.status_code == 403
    assert response.json()["error_code"] == "MATCH_RECORDS_PRIVATE"


async def test_view_match_records_succeeds_for_friend_when_enabled(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    viewer = await _register_and_verify(db_session, "friendview-c6@example.com")
    target = await _register_and_verify(db_session, "friendview-c7@example.com")
    await _make_friendship(db_session, viewer, target)
    token = await _login(client, "friendview-c6@example.com")

    response = await client.get(f"/members/{target.id}/match-records", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert "matches" in body
    assert "total_matches" in body
    assert "win_rate" in body


async def test_view_match_records_requires_verified_viewer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    target = await _register_and_verify(db_session, "friendview-c8@example.com")
    await register(db_session, "friendview-c9@example.com", "abc12345")
    token = await _login(client, "friendview-c9@example.com")

    response = await client.get(f"/members/{target.id}/match-records", headers=_auth(token))

    assert response.status_code == 403
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


async def test_view_match_records_requires_login(client: AsyncClient) -> None:
    response = await client.get(f"/members/{uuid.uuid4()}/match-records")

    assert response.status_code == 401


# --- Quickstart 情境 7: unverified member locked out of every new endpoint ----


async def test_all_new_endpoints_reject_unverified_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    target = await _register_and_verify(db_session, "unverified-target@example.com")
    await register(db_session, "unverified-c1@example.com", "abc12345")
    token = await _login(client, "unverified-c1@example.com")

    checks = [
        client.patch("/members/me/language", json={"language": "zh-TW"}, headers=_auth(token)),
        client.patch("/members/me/privacy", json={"allow_search": False}, headers=_auth(token)),
        client.get("/members/me/login-records", headers=_auth(token)),
        client.get(f"/members/{target.id}/match-records", headers=_auth(token)),
    ]
    for coro in checks:
        response = await coro
        assert response.status_code == 403
        assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"
