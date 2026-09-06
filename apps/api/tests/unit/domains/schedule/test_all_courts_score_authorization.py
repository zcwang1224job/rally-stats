"""Unit test: _all_courts_court() 授權邊界——court_id 若屬於 all-courts
token 解析出之群組以外的另一個團，MUST 拒絕（research.md #4 之延伸，
比照公開單一場地 token 的授權邊界）。"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_all_courts_score_rejects_court_from_different_group(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_a = (
        await client.post(
            "/groups",
            json={
                "name": "All Courts Auth A",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿甲",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    group_b = (
        await client.post(
            "/groups",
            json={
                "name": "All Courts Auth B",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿乙",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    headers_b = {"Authorization": f"Bearer {group_b['admin_token']}"}
    court_b = (
        await client.post(
            f"/groups/{group_b['group_id']}/courts", headers=headers_b, json={"name": "B場"}
        )
    ).json()

    admin_view_a = (
        await client.get(
            f"/groups/{group_a['group_id']}/admin",
            headers={"Authorization": f"Bearer {group_a['admin_token']}"},
        )
    ).json()
    all_courts_token_a = admin_view_a["all_courts_control_panel_token"]

    response = await client.post(
        f"/groups/by-all-courts-token/{all_courts_token_a}/courts/{court_b['court_id']}/"
        f"matches/{uuid.uuid4()}/score",
        json={"side": "A", "delta": 1},
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


async def test_all_courts_end_match_rejects_court_from_different_group(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_a = (
        await client.post(
            "/groups",
            json={
                "name": "All Courts Auth End A",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿丙",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    group_b = (
        await client.post(
            "/groups",
            json={
                "name": "All Courts Auth End B",
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "阿丁",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    headers_b = {"Authorization": f"Bearer {group_b['admin_token']}"}
    court_b = (
        await client.post(
            f"/groups/{group_b['group_id']}/courts", headers=headers_b, json={"name": "B場"}
        )
    ).json()

    admin_view_a = (
        await client.get(
            f"/groups/{group_a['group_id']}/admin",
            headers={"Authorization": f"Bearer {group_a['admin_token']}"},
        )
    ).json()
    all_courts_token_a = admin_view_a["all_courts_control_panel_token"]

    response = await client.post(
        f"/groups/by-all-courts-token/{all_courts_token_a}/courts/{court_b['court_id']}/"
        f"matches/{uuid.uuid4()}/end"
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"
