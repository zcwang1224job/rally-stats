"""Contract test for GET /groups/{group_id}/standings's 018-group-leaderboard
extension — `rank`/`total_wins`/`total_losses` per contracts/standings-api.md.
Regression: existing `rounds`/`current_round_number` fields unaffected."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group_and_join(client: AsyncClient, token: str) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Standings Ranking Contract",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿正",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    join_response = await client.post(
        f"/groups/{created['group_id']}/join", json={"nickname": "小美"}
    )
    return created, join_response.json()


async def test_standings_response_includes_ranking_fields(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created, joined = await _create_group_and_join(client, valid_turnstile_token)

    response = await client.get(
        f"/groups/{created['group_id']}/standings",
        params={"guest_session_token": joined["guest_session_token"]},
    )
    assert response.status_code == 200
    body = response.json()

    # Existing fields untouched (regression).
    assert body["current_round_number"] == 1
    assert body["rounds"] == []
    assert len(body["members"]) == 2

    for member in body["members"]:
        assert isinstance(member["rank"], int)
        assert isinstance(member["total_wins"], int)
        assert isinstance(member["total_losses"], int)
        # No completed matches yet — everyone is winless and tied at rank 1.
        assert member["rank"] == 1
        assert member["total_wins"] == 0
        assert member["total_losses"] == 0
        # Existing per-round shape untouched.
        assert member["rounds"] == {}
