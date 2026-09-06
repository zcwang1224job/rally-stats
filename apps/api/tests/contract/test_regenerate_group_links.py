"""Contract test for POST /groups/{group_id}/regenerate-join-link and
regenerate-all-courts-link per contracts/courts-api.md."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group(client: AsyncClient, token: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Regen Group Links Contract",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿珊",
            "turnstile_token": token,
        },
    )
    return response.json()


async def test_regenerate_join_link_succeeds(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/regenerate-join-link",
        headers=headers,
        json={"expected_version": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["join_link_version"] == 1


async def test_regenerate_all_courts_link_succeeds(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/regenerate-all-courts-link",
        headers=headers,
        json={"expected_version": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["all_courts_link_version"] == 1


async def test_regenerate_join_link_stale_version_returns_409(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.post(
        f"/groups/{created['group_id']}/regenerate-join-link",
        headers=headers,
        json={"expected_version": 99},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "VERSION_CONFLICT"


async def test_regenerate_links_require_admin_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)

    join_response = await client.post(
        f"/groups/{created['group_id']}/regenerate-join-link", json={"expected_version": 0}
    )
    assert join_response.status_code == 401

    all_courts_response = await client.post(
        f"/groups/{created['group_id']}/regenerate-all-courts-link", json={"expected_version": 0}
    )
    assert all_courts_response.status_code == 401
