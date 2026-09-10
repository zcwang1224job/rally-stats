"""Integration test: full lifecycle "新增場地 → 重新產生連結 → 刪除場地"
(constitution principle II — mandatory end-to-end test for this feature)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_court_full_lifecycle(client: AsyncClient, valid_turnstile_token: str) -> None:
    # 建立團
    group_response = await client.post(
        "/groups",
        json={
            "name": "Court Full Lifecycle",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿全",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    # 新增場地
    create_response = await client.post(
        f"/groups/{group_id}/courts", headers=headers, json={"name": "中山場"}
    )
    assert create_response.status_code == 201
    court = create_response.json()
    old_scoreboard_token = court["scoreboard_token"]

    list_response = await client.get(f"/groups/{group_id}/courts", headers=headers)
    # 021-group-creation-defaults FR-006: the group's auto-created "球場一"
    # court is also active, alongside the manually-created one above.
    assert list_response.json()["active_court_count"] == 2

    # 重新產生連結
    regen_response = await client.post(
        f"/courts/{court['court_id']}/regenerate-scoreboard-link",
        headers=headers,
        json={"expected_version": 0},
    )
    assert regen_response.status_code == 200
    new_token = regen_response.json()["scoreboard_token"]
    assert new_token != old_scoreboard_token

    old_token_lookup = await client.get(f"/courts/by-token/{old_scoreboard_token}")
    assert old_token_lookup.status_code == 404

    new_token_lookup = await client.get(f"/courts/by-token/{new_token}")
    assert new_token_lookup.status_code == 200
    assert new_token_lookup.json()["deleted"] is False

    # 刪除場地
    delete_response = await client.delete(f"/courts/{court['court_id']}", headers=headers)
    assert delete_response.status_code == 200

    final_lookup = await client.get(f"/courts/by-token/{new_token}")
    assert final_lookup.status_code == 200
    assert final_lookup.json()["deleted"] is True

    final_list = await client.get(f"/groups/{group_id}/courts", headers=headers)
    # The auto-created "球場一" court remains; only 中山場 was deleted.
    assert final_list.json()["active_court_count"] == 1
