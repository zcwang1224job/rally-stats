"""Integration test: full 建立 → 重新驗證 → 編輯 → 解散 lifecycle, required by
constitution principle II ("關鍵使用者流程...MUST 具備至少一條端到端或整合測試")."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_create_reauth_edit_disband_lifecycle(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    # 建立
    create_response = await client.post(
        "/groups",
        json={
            "name": "Full Lifecycle Test",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "scoring_mode": "21pt",
            "creator_nickname": "小王",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    group_id = created["group_id"]
    group_number = created["group_number"]
    admin_pin = created["admin_pin"]

    # 重新驗證
    reauth_response = await client.post(
        "/groups/reauth", json={"group_number": group_number, "admin_pin": admin_pin}
    )
    assert reauth_response.status_code == 200
    admin_token = reauth_response.json()["admin_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 編輯
    edit_response = await client.patch(
        f"/groups/{group_id}",
        headers=headers,
        json={"expected_version": 0, "name": "週三夜羽球團（已改期）", "max_members": 8},
    )
    assert edit_response.status_code == 200
    edited = edit_response.json()["group"]
    assert edited["name"] == "週三夜羽球團（已改期）"
    assert edited["max_members"] == 8

    # 解散
    disband_response = await client.post(f"/groups/{group_id}/disband", headers=headers)
    assert disband_response.status_code == 200
    assert disband_response.json()["status"] == "disbanded"

    # 解散後：唯讀管理頁仍可查閱，寫入被拒絕
    admin_view = await client.get(f"/groups/{group_id}/admin", headers=headers)
    assert admin_view.status_code == 200
    assert admin_view.json()["read_only"] is True

    write_after_disband = await client.patch(
        f"/groups/{group_id}",
        headers=headers,
        json={"expected_version": 1, "name": "should not apply"},
    )
    assert write_after_disband.status_code == 409
    assert write_after_disband.json()["error_code"] == "GROUP_DISBANDED"
