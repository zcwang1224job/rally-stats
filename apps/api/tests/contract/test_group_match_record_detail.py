"""Contract test for GET /groups/{group_id}/match-records/{match_id} per
contracts/match-record-detail-api.md (016-match-score-timeline)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_group_with_active_match(
    client: AsyncClient, session: AsyncSession, token: str, *, name: str = "Match Detail Contract"
) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": name,
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "scoring_mode": "custom",
            "custom_scoring": {"target_score": 3, "deuce_threshold": 2, "cap_score": 5},
            "creator_nickname": "阿翔",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    # 021-group-creation-defaults FR-006: the group already has one
    # auto-created "球場一" court — use that instead of adding a second one,
    # so round generation has exactly one court to assign this test's single
    # match to (a second court would otherwise compete for it).
    courts_response = await client.get(f"/groups/{created['group_id']}/courts", headers=headers)
    court = courts_response.json()["courts"][0]

    await session.execute(
        text(
            "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
            "VALUES (:id, :group_id, 'P0', 'active', false)"
        ),
        {"id": str(uuid.uuid4()), "group_id": created["group_id"]},
    )
    await session.commit()
    await client.post(f"/groups/{created['group_id']}/next-round", headers=headers)

    return created, court


async def _get_match_id(client: AsyncClient, court: dict) -> str:
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id: str = state.json()["current_match"]["match_id"]
    return match_id


async def _complete_match(client: AsyncClient, court: dict, match_id: str) -> None:
    """Plays out the 3-point custom-scoring match to a natural finish via
    the real control-panel scoring endpoint (same write path production
    traffic uses), so score_events end up populated exactly like they
    would for a real match."""
    for _ in range(3):
        response = await client.post(
            f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
            json={"side": "A", "delta": 1},
        )
        assert response.status_code == 200


async def test_success_with_guest_token_returns_complete_record(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)
    await _complete_match(client, court, match_id)

    guest_join = await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})
    guest_token = guest_join.json()["guest_session_token"]

    response = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": guest_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["match_id"] == match_id
    assert body["record_completeness"] == "complete"
    assert body["score_a"] == 3
    assert body["winner_team"] == "A"
    assert len(body["events"]) == 3
    assert [e["elapsed_seconds"] for e in body["events"]] == sorted(
        e["elapsed_seconds"] for e in body["events"]
    )
    assert body["events"][0]["score_a"] == 1
    assert body["events"][-1]["score_a"] == 3


async def test_without_token_returns_membership_required(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)
    await _complete_match(client, court, match_id)

    response = await client.get(f"/groups/{created['group_id']}/match-records/{match_id}")

    assert response.status_code == 403
    assert response.json()["error_code"] == "MEMBERSHIP_REQUIRED"


async def test_incomplete_match_returns_match_not_found(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    match_id = await _get_match_id(client, court)
    guest_join = await client.post(f"/groups/{created['group_id']}/join", json={"nickname": "小美"})
    guest_token = guest_join.json()["guest_session_token"]

    response = await client.get(
        f"/groups/{created['group_id']}/match-records/{match_id}",
        params={"guest_session_token": guest_token},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "MATCH_NOT_FOUND"


async def test_match_from_different_group_returns_match_not_found(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created_a, court_a = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, name="Match Detail Contract A"
    )
    match_id_a = await _get_match_id(client, court_a)
    await _complete_match(client, court_a, match_id_a)

    created_b, _court_b = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, name="Match Detail Contract B"
    )
    guest_join_b = await client.post(
        f"/groups/{created_b['group_id']}/join", json={"nickname": "小華"}
    )
    guest_token_b = guest_join_b.json()["guest_session_token"]

    response = await client.get(
        f"/groups/{created_b['group_id']}/match-records/{match_id_a}",
        params={"guest_session_token": guest_token_b},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "MATCH_NOT_FOUND"
