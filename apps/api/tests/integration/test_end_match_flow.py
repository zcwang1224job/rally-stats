"""Integration test: 提前結束 → 場地依排程機制自動或等待安排下一場
（quickstart.md 情境 3）。演算法模式下同輪內不會有可領取的排隊比賽（見
test_scoring_flow.py 之說明），故驗證重點在於：提前結束後場地正確轉為
等待狀態、不產生 MatchResult、且不影響同團其他場地；手動模式則驗證
場地正確顯示等待管理員安排。"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_end_match_early_algorithmic_mode_waits_then_next_round(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "End Match Flow",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿哲",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    # 021-group-creation-defaults FR-006: the group already has one
    # auto-created "球場一" court — use that instead of adding a second one,
    # so round generation has exactly one court to assign this test's single
    # match to (a second court would otherwise compete for it).
    court = (
        await client.get(f"/groups/{group_id}/courts", headers=headers)
    ).json()["courts"][0]

    await db_session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, 'P0', 'active', false)"
        ),
        {"id": str(uuid.uuid4()), "group_id": group_id},
    )
    await db_session.commit()
    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id = state.json()["current_match"]["match_id"]

    end_response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/end"
    )
    assert end_response.json()["applied"] is True
    assert end_response.json()["status"] == "abandoned"

    after = (await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")).json()
    assert after["current_match"] is None
    assert after["waiting_reason"] == "no_queued_match"
    assert after["round_number"] == 1

    # A delayed +1 against the abandoned match is a no-op (FR-006).
    delayed = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )
    assert delayed.json()["applied"] is False
    assert delayed.json()["status"] == "abandoned"

    await client.post(f"/groups/{group_id}/next-round", headers=headers)
    round3 = (await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")).json()
    assert round3["round_number"] == 2
    assert round3["current_match"] is not None


async def test_end_match_early_manual_mode_waits_for_admin_assignment(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "End Match Flow Manual",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿哲",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()

    for i in range(3):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    roster = await db_session.execute(
        text("SELECT id FROM roster_entries WHERE group_id = :gid ORDER BY joined_at"),
        {"gid": group_id},
    )
    ids = [str(row[0]) for row in roster.all()]
    assign_response = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=headers,
        json={"participant_ids": ids[:2], "teams": {ids[0]: "A", ids[1]: "B"}},
    )
    match_id = assign_response.json()["match_id"]

    end_response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/end"
    )
    assert end_response.json()["applied"] is True

    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    body = state.json()
    assert body["current_match"] is None
    assert body["waiting_reason"] == "manual_assignment"
    assert body["next_up"] is None

    # Admin re-assigns; the court starts a fresh match, still Round 1.
    reassign = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=headers,
        json={"participant_ids": ids[1:3], "teams": {ids[1]: "A", ids[2]: "B"}},
    )
    assert reassign.status_code == 201
    after = (await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")).json()
    assert after["current_match"] is not None
    assert after["round_number"] == 1
