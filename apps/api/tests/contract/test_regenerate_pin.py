"""Contract test for POST /groups/{id}/regenerate-admin-pin."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_regenerate_pin_invalidates_old_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Regen Contract",
                "max_members": 4,
                "match_mode": "doubles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "小李",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    old_headers = {"Authorization": f"Bearer {created['admin_token']}"}

    regen_response = await client.post(
        f"/groups/{created['group_id']}/regenerate-admin-pin", headers=old_headers
    )
    assert regen_response.status_code == 200
    new_pin_data = regen_response.json()
    assert new_pin_data["admin_pin"] != created["admin_pin"]
    assert new_pin_data["admin_token"] != created["admin_token"]

    # Old token, same request that used to succeed, now rejected.
    stale_edit = await client.patch(
        f"/groups/{created['group_id']}",
        headers=old_headers,
        json={"expected_version": 0, "name": "should fail"},
    )
    assert stale_edit.status_code == 401

    # New token works.
    new_headers = {"Authorization": f"Bearer {new_pin_data['admin_token']}"}
    fresh_edit = await client.patch(
        f"/groups/{created['group_id']}",
        headers=new_headers,
        json={"expected_version": 0, "name": "should succeed"},
    )
    assert fresh_edit.status_code == 200
