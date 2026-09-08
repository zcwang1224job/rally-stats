"""Contract test for POST /groups/{group_id}/members per
contracts/manual-add-guest-api.md (015-manual-add-guest)."""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group(
    client: AsyncClient,
    valid_turnstile_token: str,
    *,
    max_members: int = 8,
    match_mode: str = "doubles",
) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Add Guest Contract Group",
            "max_members": max_members,
            "match_mode": match_mode,
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
        },
    )
    return response.json()


async def test_add_guest_succeeds(client: AsyncClient, valid_turnstile_token: str) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小明"}, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["nickname"] == "小明"
    assert body["guest_session_token"]
    assert body["created_new"] is True


async def test_add_guest_requires_admin_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)

    response = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小明"}
    )
    assert response.status_code == 401


async def test_add_guest_rejects_mismatched_group_id(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    other = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{other['group_id']}/members", json={"nickname": "小明"}, headers=headers
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "ADMIN_TOKEN_INVALID"


async def test_add_guest_allows_continuous_adds(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    first = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小明"}, headers=headers
    )
    second = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小華"}, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["roster_entry_id"] != second.json()["roster_entry_id"]


async def test_add_guest_allows_duplicate_nickname(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    first = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小明"}, headers=headers
    )
    second = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小明"}, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 201


async def test_add_guest_rejects_blank_nickname(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "   "}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "NICKNAME_REQUIRED_FOR_GUEST"


async def test_add_guest_full_group_returns_409(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(
        client, valid_turnstile_token, max_members=2, match_mode="singles"
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    first = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小明"}, headers=headers
    )
    assert first.status_code == 201

    response = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小華"}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "GROUP_FULL"


async def test_add_guest_disbanded_group_returns_409(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.post(f"/groups/{created['group_id']}/disband", headers=headers)

    response = await client.post(
        f"/groups/{created['group_id']}/members", json={"nickname": "小明"}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "GROUP_DISBANDED"


async def test_add_guest_unknown_group_returns_401(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    """A random group_id never matches any admin_token's `group.id`, so this
    falls into the same ADMIN_TOKEN_INVALID path as any other mismatch —
    there's no separate GROUP_NOT_FOUND branch here (unlike the public join
    endpoint) because `require_admin` never reaches the point of looking up
    `group_id` from the path; it decodes the group straight from the token."""
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{uuid.uuid4()}/members", json={"nickname": "小明"}, headers=headers
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "ADMIN_TOKEN_INVALID"
