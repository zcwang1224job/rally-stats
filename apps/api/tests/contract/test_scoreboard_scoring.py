"""Contract test for PATCH /groups/{group_id}/scoreboard-scoring, and the
`link_type` widening it grants on the by-token score/end-match endpoints
(018-plan-then-start follow-up)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group import service as group_service

pytestmark = pytest.mark.asyncio


async def _create_group_with_active_match(
    client: AsyncClient, session: AsyncSession, token: str
) -> tuple[dict, dict]:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Scoreboard Scoring Contract",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿凱",
            "turnstile_token": token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
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


async def test_scoreboard_scoring_defaults_to_disabled(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Scoreboard Scoring Default",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    response = await client.get(f"/groups/{created['group_id']}/admin", headers=headers)

    assert response.status_code == 200
    assert response.json()["scoreboard_scoring_enabled"] is False


async def test_enable_scoreboard_scoring(client: AsyncClient, valid_turnstile_token: str) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Scoreboard Scoring Enable",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    patch_response = await client.patch(
        f"/groups/{created['group_id']}/scoreboard-scoring",
        headers=headers,
        json={"enabled": True},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["scoreboard_scoring_enabled"] is True

    admin_response = await client.get(f"/groups/{created['group_id']}/admin", headers=headers)
    assert admin_response.json()["scoreboard_scoring_enabled"] is True


async def test_score_via_scoreboard_token_succeeds_once_enabled(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.patch(
        f"/groups/{created['group_id']}/scoreboard-scoring",
        headers=headers,
        json={"enabled": True},
    )
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id = state.json()["current_match"]["match_id"]
    assert state.json()["scoreboard_scoring_enabled"] is True

    response = await client.post(
        f"/courts/by-token/{court['scoreboard_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["score_a"] == 1


async def test_end_match_via_scoreboard_token_succeeds_once_enabled(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.patch(
        f"/groups/{created['group_id']}/scoreboard-scoring",
        headers=headers,
        json={"enabled": True},
    )
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id = state.json()["current_match"]["match_id"]

    response = await client.post(
        f"/courts/by-token/{court['scoreboard_token']}/matches/{match_id}/end",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "abandoned"


async def test_score_via_scoreboard_token_still_rejected_when_disabled(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """Regression guard: adding the opt-in path MUST NOT loosen the default
    boundary (research.md #3) for groups that never touch the new setting."""
    _created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    state = await client.get(f"/courts/by-token/{court['scoreboard_token']}/state")
    match_id = state.json()["current_match"]["match_id"]
    assert state.json()["scoreboard_scoring_enabled"] is False

    response = await client.post(
        f"/courts/by-token/{court['scoreboard_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "LINK_NOT_FOUND"


async def test_toggling_scoreboard_scoring_broadcasts_to_every_court(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard for the bug report: an already-open scoreboard page
    only refetches on the NEXT unrelated event unless this toggle itself
    broadcasts — without this, checking/unchecking the admin setting has no
    visible effect until something else happens to trigger a refetch."""
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    calls: list[tuple[str, str, dict]] = []

    async def fake_publish(channel: str, event: str, payload: dict) -> None:
        calls.append((channel, event, payload))

    monkeypatch.setattr(group_service, "publish", fake_publish)

    response = await client.patch(
        f"/groups/{created['group_id']}/scoreboard-scoring",
        headers=headers,
        json={"enabled": True},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    channel, event, _payload = calls[0]
    assert channel == f"court:{created['group_id']}:{court['court_id']}"
    assert event == "match.nextRound"
