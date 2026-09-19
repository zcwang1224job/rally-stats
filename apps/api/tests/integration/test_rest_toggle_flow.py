"""Integration test for 037-rest-ready-toggle through the real API — the
constitution II end-to-end path "create → join → schedule → score" with a
player resting in the middle of it (T035, SC-008).

Each group has the one court every new group starts with."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

MAX_POINTS = 40  # a 21-point game can't take more calls than this


async def _group(
    client: AsyncClient, token: str, *, mechanism: str, mode: str, guests: int
) -> tuple[dict, list[dict], dict[str, str], dict]:
    created = (
        await client.post(
            "/groups",
            json={
                "name": "Rest Flow",
                "max_members": 12,
                "match_mode": mode,
                "scheduling_mechanism": mechanism,
                "creator_nickname": "阿正",
                "turnstile_token": token,
            },
        )
    ).json()
    group_id = created["group_id"]
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    joined = []
    for i in range(guests):
        response = await client.post(f"/groups/{group_id}/join", json={"nickname": f"G{i}"})
        joined.append(response.json())
    [court] = (await client.get(f"/groups/{group_id}/courts", headers=headers)).json()["courts"]
    return created, joined, headers, court


async def _state(client: AsyncClient, court: dict) -> dict:
    response = await client.get(f"/courts/by-token/{court['control_panel_token']}/state")
    assert response.status_code == 200
    return response.json()


async def _finish_current(client: AsyncClient, court: dict) -> None:
    """Scores the court's current match to a 21-0 win for side A."""
    match_id = (await _state(client, court))["current_match"]["match_id"]
    for _ in range(MAX_POINTS):
        response = await client.post(
            f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
            json={"side": "A", "delta": 1},
        )
        assert response.status_code == 200
        if response.json()["status"] == "completed":
            return
    raise AssertionError("match never finished")


def _ids(participants: list[dict]) -> set[str]:
    return {p["roster_entry_id"] for p in participants}


async def _auto_next_round(client: AsyncClient, group_id: str, headers: dict[str, str]) -> None:
    response = await client.patch(
        f"/groups/{group_id}/auto-next-round", headers=headers, json={"enabled": True}
    )
    assert response.status_code == 200


async def _set_rest(  # type: ignore[no-untyped-def]
    client: AsyncClient, group_id: str, player: dict, resting: bool, **extra
):
    return await client.put(
        f"/groups/{group_id}/roster/{player['roster_entry_id']}/rest-state",
        json={"resting": resting, "guest_session_token": player["guest_session_token"], **extra},
    )


async def _completed_wins(db_session: AsyncSession, group_id: str) -> dict[str, tuple[int, int]]:
    """(wins, losses) per roster entry, straight from completed matches."""
    rows = await db_session.execute(
        text(
            "SELECT mp.roster_entry_id::text AS player, "
            "  SUM(CASE WHEN mp.team = m.winner_team THEN 1 ELSE 0 END) AS wins, "
            "  SUM(CASE WHEN mp.team <> m.winner_team THEN 1 ELSE 0 END) AS losses "
            "FROM match_participants mp JOIN matches m ON m.id = mp.match_id "
            "WHERE m.group_id = :gid AND m.status = 'completed' GROUP BY mp.roster_entry_id"
        ),
        {"gid": group_id},
    )
    return {row.player: (row.wins, row.losses) for row in rows.all()}


async def test_a_substitute_plays_for_a_resting_player_and_the_records_add_up(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, guests, headers, court = await _group(
        client, valid_turnstile_token, mechanism="individual_mixed", mode="doubles", guests=5
    )
    group_id = created["group_id"]
    assert (await client.post(f"/groups/{group_id}/next-round", headers=headers)).status_code == 200

    # Rest someone who isn't on court now but has matches coming.
    on_court = _ids((await _state(client, court))["current_match"]["participants"])
    resting = next(g for g in guests if g["roster_entry_id"] not in on_court)
    watcher = next(g for g in guests if g is not resting)
    assert (await _set_rest(client, group_id, resting, True)).status_code == 200
    listing = (await client.get(f"/groups/{group_id}/schedule/matches", headers=headers)).json()
    to_substitute = {m["match_id"] for m in listing["matches"] if m["rest_effect"] == "substitute"}
    assert to_substitute  # their matches are marked, not changed

    # Play on. Nothing with them in it is called until it's all that's
    # left; then it's called with a substitute. (That the "next up" preview
    # promises exactly the lineup called is covered by test_rest_call_up.)
    substituted_match: str | None = None
    for _ in range(30):
        await _finish_current(client, court)
        current = (await _state(client, court))["current_match"]
        assert current is not None
        assert resting["roster_entry_id"] not in _ids(current["participants"])
        if current["match_id"] in to_substitute:
            substituted_match = current["match_id"]
            break
    assert substituted_match is not None, "the resting player's match never came up"

    assert (await _set_rest(client, group_id, resting, False)).status_code == 200
    for _ in range(40):
        if (await _state(client, court))["current_match"] is None:
            break
        await _finish_current(client, court)

    standings = (
        await client.get(
            f"/groups/{group_id}/standings",
            params={"guest_session_token": watcher["guest_session_token"]},
        )
    ).json()
    expected = await _completed_wins(db_session, group_id)
    for row in standings["members"]:
        wins, losses = expected.get(row["roster_entry_id"], (0, 0))
        assert (row["total_wins"], row["total_losses"]) == (wins, losses)
    lineup = await db_session.execute(
        text("SELECT roster_entry_id::text FROM match_participants WHERE match_id = :mid"),
        {"mid": substituted_match},
    )
    assert resting["roster_entry_id"] not in set(lineup.scalars())


async def test_a_round_stalled_by_rest_moves_on_and_the_player_rejoins(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """Singles round-robin, auto next round: Z rests while another match is
    on court (no reminder); when it ends only Z's matches are left, so the
    round moves on without Z; Z comes back and is added to the new round."""
    created, (g0, g1), headers, court = await _group(
        client, valid_turnstile_token, mechanism="fair_rotation", mode="singles", guests=2
    )
    group_id = created["group_id"]
    await _auto_next_round(client, group_id, headers)
    await client.post(f"/groups/{group_id}/next-round", headers=headers)

    on_court = _ids((await _state(client, court))["current_match"]["participants"])
    creator = {
        "roster_entry_id": created["roster_entry_id"],
        "guest_session_token": created["guest_session_token"],
    }
    everyone = [creator, g0, g1]
    z = next(p for p in everyone if p["roster_entry_id"] not in on_court)
    others = {p["roster_entry_id"] for p in everyone} - {z["roster_entry_id"]}

    rested = await _set_rest(client, group_id, z, True)
    assert rested.status_code == 200  # a match is on court: no reminder

    await _finish_current(client, court)

    schedule = (await client.get(f"/groups/{group_id}/schedule", headers=headers)).json()
    assert schedule["current_round_number"] == 2
    round_two = _ids((await _state(client, court))["current_match"]["participants"])
    assert round_two == others

    assert (await _set_rest(client, group_id, z, False)).status_code == 200
    listing = (
        await client.get(f"/groups/{group_id}/schedule/matches", headers=headers)
    ).json()
    with_z = [m for m in listing["matches"] if z["roster_entry_id"] in _ids(m["participants"])]
    assert len(with_z) == 2  # one against each of the others


async def test_a_rest_that_would_end_the_round_asks_first(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """FR-031～FR-033 through the API. The prompt only fires when the round
    is idle and every queued match has Z in it — in practice a planned
    round nobody has started yet: fixed partners (auto), six players, one
    already resting when the round is planned, so it's two teams and a bye.
    Resting Z (on one of the teams) would end the round on the spot, and
    the four still ready can make the next one."""
    created, guests, headers, _court = await _group(
        client, valid_turnstile_token, mechanism="fixed_partner", mode="doubles", guests=5
    )
    group_id = created["group_id"]
    await db_session.execute(
        text("UPDATE groups SET partner_source = 'auto' WHERE id = :gid"), {"gid": group_id}
    )
    await db_session.commit()
    await _auto_next_round(client, group_id, headers)
    assert (await _set_rest(client, group_id, guests[-1], True)).status_code == 200
    planned = await client.post(f"/groups/{group_id}/schedule/plan", headers=headers, json={})
    assert planned.status_code == 200
    listing = (await client.get(f"/groups/{group_id}/schedule/matches", headers=headers)).json()
    [only_match] = listing["matches"]  # two teams and a bye: one match
    g0 = next(g for g in guests if g["roster_entry_id"] in _ids(only_match["participants"]))

    refused = await _set_rest(client, group_id, g0, True)
    assert refused.status_code == 409
    assert refused.json() == {"error_code": "REST_ENDS_ROUND", "detail": {"matches_to_cancel": 1}}
    unchanged = (await client.get(f"/groups/{group_id}/schedule", headers=headers)).json()
    assert unchanged["current_round_number"] == 1
    resting = {r["roster_entry_id"]: r["resting"] for r in unchanged["roster"]}
    assert resting[g0["roster_entry_id"]] is False

    confirmed = await _set_rest(client, group_id, g0, True, confirm_round_end=True)
    assert confirmed.status_code == 200
    moved_on = (await client.get(f"/groups/{group_id}/schedule", headers=headers)).json()
    assert moved_on["current_round_number"] == 2
