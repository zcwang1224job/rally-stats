"""Integration test: 018-group-leaderboard end-to-end — real match
completion via the score endpoint correctly sorts/ranks the standings
endpoint (US1, T006), publishes `standings.updated` only on actual
completion (US2, T012), and produces stable/reproducible ranking across
repeated calls including ties (US3, T016)."""

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_quick_scoring_group(
    client: AsyncClient, token: str, target_score: int = 1
) -> dict:
    """`scoring_mode="custom"` with a low `target_score` so a match
    completes after just `target_score` points, keeping the test fast."""
    response = await client.post(
        "/groups",
        json={
            "name": "Standings Realtime Flow",
            "max_members": 8,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "scoring_mode": "custom",
            "custom_scoring": {
                "target_score": target_score,
                "deuce_threshold": target_score,
                "cap_score": target_score,
            },
            "creator_nickname": "P0",
            "turnstile_token": token,
        },
    )
    return response.json()


async def _creator_roster_entry_id(db_session: AsyncSession, group_id: str) -> str:
    result = await db_session.execute(
        text("SELECT id FROM roster_entries WHERE group_id = :gid AND nickname = 'P0'"),
        {"gid": group_id},
    )
    return str(result.scalar_one())


async def test_standings_endpoint_reflects_real_completed_matches_sorted_by_rank(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created = await _create_quick_scoring_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()
    court_id = court["court_id"]

    p1 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P1"})).json()
    p2 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P2"})).json()

    await client.post(f"/groups/{group_id}/next-round", headers=headers)
    p0_id = await _creator_roster_entry_id(db_session, group_id)
    p1_id, p2_id = p1["roster_entry_id"], p2["roster_entry_id"]

    async def _play(a_id: str, b_id: str) -> None:
        """A beats B in one point (target_score=1)."""
        match = (
            await client.post(
                f"/courts/{court_id}/manual-assign",
                headers=headers,
                json={"participant_ids": [a_id, b_id], "teams": {a_id: "A", b_id: "B"}},
            )
        ).json()
        await client.post(
            f"/groups/{group_id}/courts/{court_id}/matches/{match['match_id']}/score",
            headers=headers,
            json={"side": "A", "delta": 1},
        )

    # P0 beats P1, P1 beats P2, P0 beats P2 -> P0: 2W0L, P1: 1W1L, P2: 0W2L
    # (distinct win counts, no ties, so rank order is unambiguous).
    await _play(p0_id, p1_id)
    await _play(p1_id, p2_id)
    await _play(p0_id, p2_id)

    response = await client.get(
        f"/groups/{group_id}/standings",
        params={"guest_session_token": created["guest_session_token"]},
    )
    body = response.json()
    rows = {row["roster_entry_id"]: row for row in body["members"]}

    assert rows[p0_id]["total_wins"] == 2
    assert rows[p0_id]["total_losses"] == 0
    assert rows[p0_id]["rank"] == 1
    assert rows[p1_id]["total_wins"] == 1
    assert rows[p1_id]["total_losses"] == 1
    assert rows[p1_id]["rank"] == 2
    assert rows[p2_id]["total_wins"] == 0
    assert rows[p2_id]["total_losses"] == 2
    assert rows[p2_id]["rank"] == 3
    assert [m["roster_entry_id"] for m in body["members"]] == [p0_id, p1_id, p2_id]

    # Kick P2 — excluded from members, but P1's win over P2 still counts.
    kick = await client.delete(f"/groups/{group_id}/members/{p2_id}", headers=headers)
    assert kick.json()["status"] == "kicked"

    after_kick = (
        await client.get(
            f"/groups/{group_id}/standings",
            params={"guest_session_token": created["guest_session_token"]},
        )
    ).json()
    ids_after_kick = {m["roster_entry_id"] for m in after_kick["members"]}
    assert p2_id not in ids_after_kick
    rows_after_kick = {m["roster_entry_id"]: m for m in after_kick["members"]}
    assert rows_after_kick[p1_id]["total_wins"] == 1


async def test_standings_updated_published_only_on_actual_completion(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_mock = AsyncMock()
    monkeypatch.setattr("app.domains.schedule.service.publish", publish_mock)

    # target_score=2 so the match takes two points to complete — lets us
    # observe "no event on a non-completing delta" before completion.
    created = await _create_quick_scoring_group(client, valid_turnstile_token, target_score=2)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()
    court_id = court["court_id"]
    p1 = (await client.post(f"/groups/{group_id}/join", json={"nickname": "P1"})).json()

    await client.post(f"/groups/{group_id}/next-round", headers=headers)
    p0_id = await _creator_roster_entry_id(db_session, group_id)
    p1_id = p1["roster_entry_id"]

    match = (
        await client.post(
            f"/courts/{court_id}/manual-assign",
            headers=headers,
            json={"participant_ids": [p0_id, p1_id], "teams": {p0_id: "A", p1_id: "B"}},
        )
    ).json()
    match_id = match["match_id"]

    def standings_updated_calls() -> list:
        return [c for c in publish_mock.await_args_list if c.args[1] == "standings.updated"]

    # First point: does not complete the match (target_score=2) -> no event.
    await client.post(
        f"/groups/{group_id}/courts/{court_id}/matches/{match_id}/score",
        headers=headers,
        json={"side": "A", "delta": 1},
    )
    assert standings_updated_calls() == []

    # Second point: completes the match -> exactly one event, correct payload.
    await client.post(
        f"/groups/{group_id}/courts/{court_id}/matches/{match_id}/score",
        headers=headers,
        json={"side": "A", "delta": 1},
    )
    calls = standings_updated_calls()
    assert len(calls) == 1
    assert calls[0].args[0] == f"group:{group_id}:notifications"
    assert calls[0].args[2] == {"group_id": group_id}

    # Abandoning a second match must NOT publish standings.updated.
    match2 = (
        await client.post(
            f"/courts/{court_id}/manual-assign",
            headers=headers,
            json={"participant_ids": [p0_id, p1_id], "teams": {p0_id: "A", p1_id: "B"}},
        )
    ).json()
    await client.post(
        f"/groups/{group_id}/courts/{court_id}/matches/{match2['match_id']}/end", headers=headers
    )
    assert len(standings_updated_calls()) == 1  # still just the one from completion above


async def test_tied_standings_are_stable_across_repeated_calls(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = await _create_quick_scoring_group(client, valid_turnstile_token)
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    await client.post(f"/groups/{group_id}/join", json={"nickname": "P1"})
    await client.post(f"/groups/{group_id}/join", json={"nickname": "P2"})
    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    # Nobody has played yet — P0/P1/P2 all tied at 0 wins, all rank 1.
    responses = []
    for _ in range(3):
        responses.append(
            (
                await client.get(
                    f"/groups/{group_id}/standings",
                    params={"guest_session_token": created["guest_session_token"]},
                )
            ).json()
        )

    first = responses[0]
    for other in responses[1:]:
        assert other["members"] == first["members"]
    assert len(first["members"]) == 3
    assert all(m["rank"] == 1 for m in first["members"])
