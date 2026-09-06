"""Integration test: enter via join link (skipping list search) -> verify
password -> join succeeds; also check disbanded/full-group link entry
behavior (US2)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_join_via_link_full_flow(client: AsyncClient, valid_turnstile_token: str) -> None:
    create_response = await client.post(
        "/groups",
        json={
            "name": "Join Link Flow Group",
            "password": "letmein1",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = create_response.json()
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    admin_view = (
        await client.get(f"/groups/{created['group_id']}/admin", headers=admin_headers)
    ).json()
    join_link_token = admin_view["join_link_token"]

    preview_response = await client.get(f"/join/{join_link_token}")
    assert preview_response.status_code == 200
    assert preview_response.json()["has_password"] is True

    verify_response = await client.post(
        f"/groups/{created['group_id']}/verify-password", json={"password": "letmein1"}
    )
    assert verify_response.json()["correct"] is True

    join_response = await client.post(
        f"/groups/{created['group_id']}/join",
        json={"password": "letmein1", "nickname": "小美"},
    )
    assert join_response.status_code == 201


async def test_join_link_disbanded_group_shows_status(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    create_response = await client.post(
        "/groups",
        json={
            "name": "Disbanded Link Group",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = create_response.json()
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    admin_view = (
        await client.get(f"/groups/{created['group_id']}/admin", headers=admin_headers)
    ).json()
    await client.post(f"/groups/{created['group_id']}/disband", headers=admin_headers)

    preview_response = await client.get(f"/join/{admin_view['join_link_token']}")
    assert preview_response.status_code == 200
    assert preview_response.json()["status"] == "disbanded"

    join_response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    assert join_response.status_code == 409
    assert join_response.json()["error_code"] == "GROUP_DISBANDED"


async def test_join_link_full_group_shows_counts(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    create_response = await client.post(
        "/groups",
        json={
            "name": "Full Link Group",
            "max_members": 2,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = create_response.json()
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}
    admin_view = (
        await client.get(f"/groups/{created['group_id']}/admin", headers=admin_headers)
    ).json()

    fill_response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    assert fill_response.status_code == 201

    preview_response = await client.get(f"/join/{admin_view['join_link_token']}")
    body = preview_response.json()
    assert body["current_member_count"] == body["max_members"] == 2

    join_response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小華"}
    )
    assert join_response.status_code == 409
    assert join_response.json()["error_code"] == "GROUP_FULL"
