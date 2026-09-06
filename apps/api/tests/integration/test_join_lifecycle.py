"""Mandatory full-lifecycle integration test (constitution principle II):
瀏覽列表 -> 驗證密碼 -> 輸入暱稱 -> 加入成功 -> 取得 Guest Session Token ->
重新整理還原 (004's complete Guest join loop, chaining US1+US3+US4)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_full_join_lifecycle(client: AsyncClient, valid_turnstile_token: str) -> None:
    # 開團（帶密碼、人數上限剛好夠一位 Guest 加入）
    create_response = await client.post(
        "/groups",
        json={
            "name": "Full Lifecycle Group",
            "password": "letmein1",
            "max_members": 2,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = create_response.json()
    group_id = created["group_id"]

    # 瀏覽列表：確認新團出現、密碼狀態正確
    list_response = await client.get("/groups")
    assert list_response.status_code == 200
    listed = next(g for g in list_response.json()["groups"] if g["group_id"] == group_id)
    assert listed["has_password"] is True
    assert listed["current_member_count"] == 1

    # 驗證密碼：先錯一次，確認可無限重試，再輸入正確密碼
    wrong = await client.post(f"/groups/{group_id}/verify-password", json={"password": "x"})
    assert wrong.json()["correct"] is False
    correct = await client.post(
        f"/groups/{group_id}/verify-password", json={"password": "letmein1"}
    )
    assert correct.json()["correct"] is True

    # 輸入暱稱、送出加入
    join_response = await client.post(
        f"/groups/{group_id}/join", json={"password": "letmein1", "nickname": "小美"}
    )
    assert join_response.status_code == 201
    join_body = join_response.json()
    assert join_body["nickname"] == "小美"
    guest_token = join_body["guest_session_token"]
    assert guest_token
    roster_entry_id = join_body["roster_entry_id"]

    # 人數立即 +1，團現在已滿
    post_join_list = await client.get("/groups")
    updated_listing = next(
        g for g in post_join_list.json()["groups"] if g["group_id"] == group_id
    )
    assert updated_listing["current_member_count"] == 2
    assert updated_listing["current_member_count"] == updated_listing["max_members"]

    # 重新整理頁面（模擬）：憑 Guest Session Token 還原狀態，不建立新記錄
    restore_response = await client.get(f"/groups/by-guest-token/{guest_token}")
    assert restore_response.status_code == 200
    restore_body = restore_response.json()
    assert restore_body["roster_entry_id"] == roster_entry_id
    assert restore_body["nickname"] == "小美"
    assert restore_body["group_id"] == group_id
