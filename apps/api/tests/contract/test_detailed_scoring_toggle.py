"""Contract test for PATCH /groups/{group_id}/detailed-scoring
(031-shot-placement-scoring) — complete mirror of
tests/contract/test_scoreboard_scoring.py's structure (research.md
Decision 5: same "plain immediate toggle" implementation pattern)."""

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
            "name": "Detailed Scoring Contract",
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


async def test_detailed_scoring_defaults_to_disabled(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Detailed Scoring Default",
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
    assert response.json()["detailed_scoring_enabled"] is False


async def test_enable_detailed_scoring(client: AsyncClient, valid_turnstile_token: str) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Detailed Scoring Enable",
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
        f"/groups/{created['group_id']}/detailed-scoring",
        headers=headers,
        json={"enabled": True},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["detailed_scoring_enabled"] is True

    admin_response = await client.get(f"/groups/{created['group_id']}/admin", headers=headers)
    assert admin_response.json()["detailed_scoring_enabled"] is True


async def test_detailed_scoring_requires_admin(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Detailed Scoring No Auth",
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿凱",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()

    response = await client.patch(
        f"/groups/{created['group_id']}/detailed-scoring",
        json={"enabled": True},
    )

    assert response.status_code in (401, 403)


async def test_toggling_detailed_scoring_broadcasts_to_every_court(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, court = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    calls: list[tuple[str, str, dict]] = []

    async def fake_publish(channel: str, event: str, payload: dict) -> None:
        calls.append((channel, event, payload))

    monkeypatch.setattr(group_service, "publish", fake_publish)

    response = await client.patch(
        f"/groups/{created['group_id']}/detailed-scoring",
        headers=headers,
        json={"enabled": True},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    channel, event, _payload = calls[0]
    assert channel == f"court:{created['group_id']}:{court['court_id']}"
    assert event == "match.nextRound"
