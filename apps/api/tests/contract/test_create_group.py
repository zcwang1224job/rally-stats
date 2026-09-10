"""Contract test for POST /groups per contracts/groups-api.md."""

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch

from app.core.errors import ApiError

pytestmark = pytest.mark.asyncio


async def test_create_group_anonymous_returns_201_with_credentials(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await client.post(
        "/groups",
        json={
            "name": "週三夜羽球團",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "fair_rotation",
            "scoring_mode": "21pt",
            "creator_nickname": "小明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["group_number"] >= 100000
    assert len(body["admin_pin"]) == 6
    assert body["admin_pin"].isdigit()
    assert body["current_member_count"] == 1
    assert body["guest_session_token"] is not None
    assert body["admin_token"]


async def test_create_group_blank_name_defaults_and_creates_default_court(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    """021-group-creation-defaults (FR-001/FR-006, contracts/
    group-and-court-api.md): omitting `name` entirely defaults the group
    name to "{建立者暱稱}的羽球團", and a default court "球場一" already
    exists right after creation."""
    response = await client.post(
        "/groups",
        json={
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "小華",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 201
    body = response.json()

    group_response = await client.get(f"/groups/{body['group_id']}")
    assert group_response.status_code == 200
    assert group_response.json()["name"] == "小華的羽球團"

    courts_response = await client.get(
        f"/groups/{body['group_id']}/courts",
        headers={"Authorization": f"Bearer {body['admin_token']}"},
    )
    assert courts_response.status_code == 200
    courts = courts_response.json()["courts"]
    assert len(courts) == 1
    assert courts[0]["name"] == "球場一"


async def test_create_group_null_and_whitespace_name_also_default(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    for name_value in (None, "   "):
        response = await client.post(
            "/groups",
            json={
                "name": name_value,
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "fair_rotation",
                "creator_nickname": "阿宏",
                "turnstile_token": valid_turnstile_token,
            },
        )
        assert response.status_code == 201


async def test_create_group_missing_nickname_for_guest_rejected(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await client.post(
        "/groups",
        json={
            "name": "No Nickname",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "NICKNAME_REQUIRED_FOR_GUEST"


async def test_create_group_exceeding_member_cap_rejected(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await client.post(
        "/groups",
        json={
            "name": "Too Big",
            "max_members": 201,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "小明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "GROUP_MEMBER_CAP_EXCEEDED"


async def test_create_group_invalid_turnstile_rejected(
    client: AsyncClient, monkeypatch: MonkeyPatch
) -> None:
    # Cloudflare's "always-pass" test secret key (used by the rest of this suite)
    # accepts any token content, so a real network call can't exercise the
    # failure path deterministically here. Simulate a Turnstile rejection
    # directly instead — this is exactly what real invalid/expired tokens do.
    async def _fail_verify(token: str, remote_ip: str | None = None) -> None:
        raise ApiError("CAPTCHA_INVALID", status_code=400)

    monkeypatch.setattr("app.domains.group.router.verify_turnstile_token", _fail_verify)

    response = await client.post(
        "/groups",
        json={
            "name": "Bad Captcha",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "小明",
            "turnstile_token": "definitely-invalid",
        },
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CAPTCHA_INVALID"
