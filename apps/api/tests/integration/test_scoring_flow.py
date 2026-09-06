"""Integration test: +1/-1 → 自然達標 → 場地立即領取下一場排隊中比賽 →
針對已結束 match_id 的延遲 +1 請求 no-op、不影響其他場地（quickstart.md
情境 1、2）。

Note (011-round-robin-scheduling): 單打 fair_rotation 一個 round 產生的是
「全員兩兩對戰恰一次」的完整循環賽賽程（C(n,2) 場），不再是「剛好填滿
場地數」的一批比賽——8 人的賽程共 28 場，遠多於 2 個場地，所以某場地的
比賽結束後，只要賽程表中還有「參與者皆未在其他場地進行中」的排隊比賽，
該場地就會立刻領到下一場，而不是等到下一輪。本測試以此真實行為為準。"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_score_to_natural_completion_then_picks_up_next_queued_match(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Scoring Flow",
            "max_members": 8,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
            "scoring_mode": "custom",
            "custom_scoring": {"target_score": 3, "deuce_threshold": 2, "cap_score": 5},
        },
    )
    created = group_response.json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    court1 = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()
    court2 = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "2號場"})
    ).json()

    # 7 more members (+ creator = 8) -> C(8,2) = 28 matches this round.
    for i in range(7):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    state1 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    state2 = (await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")).json()
    assert state1["round_number"] == state2["round_number"] == 1
    first_match_id = state1["current_match"]["match_id"]

    control_url = f"/courts/by-token/{court1['control_panel_token']}/matches/{first_match_id}"

    r1 = await client.post(f"{control_url}/score", json={"side": "A", "delta": 1})
    assert r1.json() == {
        "applied": True,
        "match_id": first_match_id,
        "status": "in_progress",
        "score_a": 1,
        "score_b": 0,
        "winner_team": None,
    }
    await client.post(f"{control_url}/score", json={"side": "A", "delta": 1})

    # Third point reaches target_score=3 with a 2-point lead -> natural win.
    r3 = await client.post(f"{control_url}/score", json={"side": "A", "delta": 1})
    assert r3.json()["applied"] is True
    assert r3.json()["status"] == "completed"
    assert r3.json()["winner_team"] == "A"

    # Court 1 immediately picks up the next eligible queued match (28-match
    # round-robin, plenty left) with a fresh 0-0 score; round number
    # unchanged. Court 2, still in_progress with its own original match, is
    # untouched.
    after1 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    assert after1["current_match"] is not None
    assert after1["current_match"]["match_id"] != first_match_id
    assert after1["current_match"]["score_a"] == 0
    assert after1["round_number"] == 1

    after2 = (await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")).json()
    assert after2["current_match"] is not None
    assert after2["current_match"]["match_id"] == state2["current_match"]["match_id"]
    assert after2["round_number"] == 1

    # Delayed +1 against the now-completed old match_id is a no-op and MUST
    # NOT resurrect it or affect either court's current match.
    delayed = await client.post(f"{control_url}/score", json={"side": "A", "delta": 1})
    assert delayed.json()["applied"] is False
    assert delayed.json()["score_a"] == 3
    assert delayed.json()["status"] == "completed"

    unaffected1 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    assert unaffected1["current_match"]["match_id"] == after1["current_match"]["match_id"]
    unaffected2 = (await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")).json()
    assert unaffected2["current_match"] is not None

    # Admin can still force Next Round at any point, even mid-round-robin —
    # remaining queued/in_progress matches are discarded and a brand new
    # full round-robin is generated.
    await client.post(f"/groups/{group_id}/next-round", headers=headers)
    round2 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    assert round2["round_number"] == 2
    assert round2["current_match"] is not None
    assert round2["current_match"]["score_a"] == 0
