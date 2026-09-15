"""Contract tests for 028-guest-stats-binding per
contracts/guest-binding-api.md: `GET /groups/guest-token/{token}/
binding-status` and `POST /groups/guest-token/{token}/bind` (all three
non-OAuth paths — `current_member` present, `mode="register"`,
`mode="login"`)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group(client: AsyncClient, valid_turnstile_token: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Guest Binding Contract Group",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _join_as_guest(client: AsyncClient, group_id: str, nickname: str = "小美") -> dict:
    response = await client.post(f"/groups/{group_id}/join", json={"nickname": nickname})
    assert response.status_code == 201, response.text
    return response.json()


async def _register_and_login(
    client: AsyncClient, email: str, password: str, valid_turnstile_token: str
) -> str:
    register_response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "confirm_password": password,
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert register_response.status_code == 201, register_response.text
    login_response = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert login_response.status_code == 200, login_response.text
    return str(login_response.json()["access_token"])


# --- GET .../binding-status ------------------------------------------------


async def test_binding_status_not_yet_bound(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])

    token = guest["guest_session_token"]
    response = await client.get(f"/groups/guest-token/{token}/binding-status")

    assert response.status_code == 200
    body = response.json()
    assert body["already_bound"] is False
    assert body["group_id"] == created["group_id"]
    assert body["nickname"] == "小美"
    assert body["group_status"] == "active"
    assert body["roster_status"] == "active"


async def test_binding_status_already_bound(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])
    token = guest["guest_session_token"]

    bind_response = await client.post(
        f"/groups/guest-token/{token}/bind",
        json={
            "mode": "register",
            "email": "status-bound@example.com",
            "password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert bind_response.status_code == 200, bind_response.text

    status_response = await client.get(f"/groups/guest-token/{token}/binding-status")
    assert status_response.status_code == 200
    assert status_response.json()["already_bound"] is True


async def test_binding_status_unknown_token(client: AsyncClient) -> None:
    response = await client.get("/groups/guest-token/not-a-real-token/binding-status")
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


# --- POST .../bind: mode="register" ----------------------------------------


async def test_bind_mode_register_success(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])

    response = await client.post(
        f"/groups/guest-token/{guest['guest_session_token']}/bind",
        json={
            "mode": "register",
            "email": "contract-register@example.com",
            "password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bound"] is True
    assert body["group_id"] == created["group_id"]
    assert body["access_token"]
    assert body["refresh_token"]


async def test_bind_mode_register_missing_fields_is_invalid_request(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])

    response = await client.post(
        f"/groups/guest-token/{guest['guest_session_token']}/bind",
        json={"mode": "register", "email": "incomplete@example.com"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_REQUEST"


async def test_bind_mode_register_turnstile_failure(
    client: AsyncClient, valid_turnstile_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fail_verify(*_args: object, **_kwargs: object) -> None:
        from app.core.errors import ApiError

        raise ApiError("CAPTCHA_INVALID", status_code=400)

    monkeypatch.setattr("app.domains.member.service.verify_turnstile_token", _fail_verify)
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])

    response = await client.post(
        f"/groups/guest-token/{guest['guest_session_token']}/bind",
        json={
            "mode": "register",
            "email": "turnstile-fail@example.com",
            "password": "abc12345",
            "turnstile_token": "bad",
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "CAPTCHA_INVALID"


async def test_bind_mode_register_email_already_registered(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    await _register_and_login(
        client, "already-taken@example.com", "abc12345", valid_turnstile_token
    )
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])

    response = await client.post(
        f"/groups/guest-token/{guest['guest_session_token']}/bind",
        json={
            "mode": "register",
            "email": "already-taken@example.com",
            "password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "EMAIL_ALREADY_REGISTERED"


async def test_bind_roster_entry_already_bound(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])
    token = guest["guest_session_token"]

    first = await client.post(
        f"/groups/guest-token/{token}/bind",
        json={
            "mode": "register",
            "email": "first-binder@example.com",
            "password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert first.status_code == 200

    second = await client.post(
        f"/groups/guest-token/{token}/bind",
        json={
            "mode": "register",
            "email": "second-binder@example.com",
            "password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "ROSTER_ENTRY_ALREADY_BOUND"


async def test_bind_unknown_token(client: AsyncClient, valid_turnstile_token: str) -> None:
    response = await client.post(
        "/groups/guest-token/not-a-real-token/bind",
        json={
            "mode": "register",
            "email": "unknown-token@example.com",
            "password": "abc12345",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


# --- POST .../bind: mode="login" (US2) --------------------------------------


async def test_bind_mode_login_success(client: AsyncClient, valid_turnstile_token: str) -> None:
    await _register_and_login(
        client, "existing-login@example.com", "s3cret123", valid_turnstile_token
    )
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])

    response = await client.post(
        f"/groups/guest-token/{guest['guest_session_token']}/bind",
        json={"mode": "login", "email": "existing-login@example.com", "password": "s3cret123"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bound"] is True
    assert body["access_token"]


async def test_bind_mode_login_invalid_credentials(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    await _register_and_login(
        client, "wrong-pw@example.com", "correct-password1", valid_turnstile_token
    )
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])

    response = await client.post(
        f"/groups/guest-token/{guest['guest_session_token']}/bind",
        json={"mode": "login", "email": "wrong-pw@example.com", "password": "nope"},
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


# --- POST .../bind: already logged in (Clarifications 2026-09-15/FR-012) --


async def test_bind_already_logged_in_one_click(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    access_token = await _register_and_login(
        client, "one-click@example.com", "abc12345", valid_turnstile_token
    )
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])

    response = await client.post(
        f"/groups/guest-token/{guest['guest_session_token']}/bind",
        json={},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bound"] is True
    assert body["access_token"] is None
    assert body["refresh_token"] is None


async def test_bind_not_logged_in_empty_body_is_invalid_request(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    guest = await _join_as_guest(client, created["group_id"])

    response = await client.post(
        f"/groups/guest-token/{guest['guest_session_token']}/bind", json={}
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_REQUEST"
