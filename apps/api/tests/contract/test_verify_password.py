"""Contract test for POST /groups/{group_id}/verify-password per
contracts/join-api.md."""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group_with_password(client: AsyncClient, valid_turnstile_token: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Password Group",
            "password": "secret123",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    return response.json()


async def test_verify_password_correct(client: AsyncClient, valid_turnstile_token: str) -> None:
    created = await _create_group_with_password(client, valid_turnstile_token)
    response = await client.post(
        f"/groups/{created['group_id']}/verify-password", json={"password": "secret123"}
    )
    assert response.status_code == 200
    assert response.json() == {"correct": True}


async def test_verify_password_incorrect_no_lockout(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group_with_password(client, valid_turnstile_token)
    for _ in range(15):
        response = await client.post(
            f"/groups/{created['group_id']}/verify-password", json={"password": "wrong"}
        )
        assert response.status_code == 200
        assert response.json() == {"correct": False}


async def test_verify_password_unknown_group(client: AsyncClient) -> None:
    response = await client.post(
        f"/groups/{uuid.uuid4()}/verify-password", json={"password": "anything"}
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "GROUP_NOT_FOUND"
