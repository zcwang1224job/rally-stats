"""Contract test for PATCH /groups/{id} and PATCH /groups/{id}/scoring-settings."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group(client: AsyncClient, token: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": "Edit Contract",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿凱",
            "turnstile_token": token,
        },
    )
    return response.json()


async def test_edit_group_name(client: AsyncClient, valid_turnstile_token: str) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "name": "New Name"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["group"]["name"] == "New Name"
    assert body["base_settings_version"] == 1


async def test_edit_scoring_settings_custom(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.patch(
        f"/groups/{created['group_id']}/scoring-settings",
        headers=headers,
        json={
            "expected_version": 0,
            "scoring_mode": "custom",
            "target_score": 11,
            "deuce_threshold": 10,
            "cap_score": 15,
        },
    )
    assert response.status_code == 200


async def test_edit_with_conflicting_version_returns_409(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    first = await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "name": "First"},
    )
    assert first.status_code == 200

    second = await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "name": "Second (stale)"},
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "VERSION_CONFLICT"


async def test_admin_view_exposes_current_scoring_settings(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    """管理頁要能顯示團真正的分數制度，而不是前端表單寫死的 21pt 預設。"""
    created = await client.post(
        "/groups",
        json={
            "name": "Scoring View",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "scoring_mode": "15pt",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
        },
    )
    body = created.json()
    headers = {"Authorization": f"Bearer {body['admin_token']}"}

    response = await client.get(f"/groups/{body['group_id']}/admin", headers=headers)

    assert response.status_code == 200
    view = response.json()
    assert view["scoring_mode"] == "15pt"
    assert (view["target_score"], view["deuce_threshold"], view["cap_score"]) == (15, 14, 21)


async def test_admin_view_reflects_edited_custom_scoring(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.patch(
        f"/groups/{created['group_id']}/scoring-settings",
        headers=headers,
        json={
            "expected_version": 0,
            "scoring_mode": "custom",
            "target_score": 7,
            "deuce_threshold": 6,
            "cap_score": 9,
        },
    )

    response = await client.get(f"/groups/{created['group_id']}/admin", headers=headers)

    view = response.json()
    assert view["scoring_mode"] == "custom"
    assert (view["target_score"], view["deuce_threshold"], view["cap_score"]) == (7, 6, 9)
