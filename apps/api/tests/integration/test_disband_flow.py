"""Integration test: create → disband → admin view is read_only, further
writes rejected (spec US2 acceptance scenarios 1, 3)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_disband_flow_makes_group_read_only(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Disband Flow Test",
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "小強",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    disband_response = await client.post(
        f"/groups/{created['group_id']}/disband", headers=headers
    )
    assert disband_response.status_code == 200

    admin_view = await client.get(f"/groups/{created['group_id']}/admin", headers=headers)
    assert admin_view.status_code == 200
    assert admin_view.json()["read_only"] is True

    edit_response = await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "name": "should not work"},
    )
    assert edit_response.status_code == 409
    assert edit_response.json()["error_code"] == "GROUP_DISBANDED"
