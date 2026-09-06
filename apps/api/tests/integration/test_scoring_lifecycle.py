"""Mandatory full-lifecycle integration test (constitution principle II):
+1/-1 → 自然達標 → 場地立即領取下一場排隊中比賽 → 延遲請求 no-op → 另一
場地提前結束 → 整輪（全員循環賽）消耗完畢 → Auto Next Round 自動觸發
下一輪（007's complete scoring loop, chaining US1+US2+US3+US5's underlying
hooks, and 011-round-robin-scheduling's full round-robin generation)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_full_scoring_lifecycle(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Scoring Lifecycle",
                "max_members": 8,
                "match_mode": "singles",
                "scheduling_mechanism": "fair_rotation",
                "creator_nickname": "阿信",
                "turnstile_token": valid_turnstile_token,
                "scoring_mode": "custom",
                "custom_scoring": {"target_score": 3, "deuce_threshold": 2, "cap_score": 5},
            },
        )
    ).json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    court1 = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()
    court2 = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "2號場"})
    ).json()

    # 4 more members (+ creator = 5) -> C(5,2) = 10 matches this round.
    for i in range(4):
        await db_session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": str(uuid.uuid4()), "group_id": group_id, "nickname": f"P{i}"},
        )
    await db_session.commit()

    # Auto Next Round is armed before anything finishes, per FR-034/035.
    auto_response = await client.patch(
        f"/groups/{group_id}/auto-next-round", headers=headers, json={"enabled": True}
    )
    assert auto_response.json()["auto_next_round"] is True

    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    state1 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    state2 = (await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")).json()
    assert state1["round_number"] == state2["round_number"] == 1
    match1_id = state1["current_match"]["match_id"]
    match2_id = state2["current_match"]["match_id"]

    control1 = f"/courts/by-token/{court1['control_panel_token']}/matches/{match1_id}"

    # Step 1: +1/-1 dynamics on court 1, including a floor-guarded -1.
    floor = await client.post(f"{control1}/score", json={"side": "A", "delta": -1})
    assert floor.json() == {
        "applied": False,
        "match_id": match1_id,
        "status": "in_progress",
        "score_a": 0,
        "score_b": 0,
        "winner_team": None,
    }
    await client.post(f"{control1}/score", json={"side": "A", "delta": 1})
    await client.post(f"{control1}/score", json={"side": "A", "delta": 1})

    # Step 2: third point reaches target_score=3 with a 2-point lead ->
    # natural completion.
    win = await client.post(f"{control1}/score", json={"side": "A", "delta": 1})
    assert win.json()["applied"] is True
    assert win.json()["status"] == "completed"
    assert win.json()["winner_team"] == "A"

    # Step 3: court 1 immediately picks up the next eligible queued match
    # (10-match round-robin, plenty left besides court 2's 2 busy players);
    # round unchanged.
    after1 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    assert after1["current_match"] is not None
    assert after1["current_match"]["match_id"] != match1_id
    assert after1["current_match"]["score_a"] == 0
    assert after1["round_number"] == 1

    # Step 4: a delayed +1 against the now-completed match is a no-op and
    # does not resurrect it or touch court 2.
    delayed = await client.post(f"{control1}/score", json={"side": "A", "delta": 1})
    assert delayed.json()["applied"] is False
    assert delayed.json()["score_a"] == 3

    unaffected = (await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")).json()
    assert unaffected["current_match"]["match_id"] == match2_id
    assert unaffected["current_match"]["score_a"] == 0

    # Step 5: court 2's match is ended early via the all-courts token —
    # exercising US5's endpoint as part of the same chained lifecycle.
    admin_view = (await client.get(f"/groups/{group_id}/admin", headers=headers)).json()
    all_courts_token = admin_view["all_courts_control_panel_token"]
    end_response = await client.post(
        f"/groups/by-all-courts-token/{all_courts_token}/courts/{court2['court_id']}/"
        f"matches/{match2_id}/end"
    )
    assert end_response.json()["applied"] is True
    assert end_response.json()["status"] == "abandoned"
    assert end_response.json()["winner_team"] is None

    # Step 6: keep draining the round-robin (10 matches total; 2 are already
    # terminal, several more may already be in progress via the idle-court
    # recheck) via the all-courts endpoint until every match is terminal and
    # Auto Next Round fires automatically — no manual Next Round call.
    for _ in range(20):  # generous cap; the round only ever has 10 matches
        snapshot = (
            await client.get(f"/groups/by-all-courts-token/{all_courts_token}/state")
        ).json()
        if snapshot["round_number"] == 2:
            break
        for court_state in snapshot["courts"]:
            current = court_state["current_match"]
            if current is not None:
                await client.post(
                    f"/groups/by-all-courts-token/{all_courts_token}/courts/"
                    f"{court_state['court_id']}/matches/{current['match_id']}/end"
                )
    else:
        pytest.fail("round never auto-advanced after draining all matches")

    final1 = (await client.get(f"/courts/by-token/{court1['scoreboard_token']}/state")).json()
    final2 = (await client.get(f"/courts/by-token/{court2['scoreboard_token']}/state")).json()
    assert final1["round_number"] == 2
    assert final2["round_number"] == 2
    assert final1["current_match"] is not None
    assert final2["current_match"] is not None
    assert final1["current_match"]["score_a"] == 0
    assert final2["current_match"]["score_a"] == 0
