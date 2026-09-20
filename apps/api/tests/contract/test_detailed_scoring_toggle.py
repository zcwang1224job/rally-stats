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
    client: AsyncClient, session: AsyncSession, token: str, detailed: bool = False
) -> tuple[dict, dict]:
    """`detailed=True` flips the group's toggle BEFORE the round is started,
    so the match below snapshots it as enabled (038-admin-detailed-scoring —
    matches.detailed_scoring_enabled is copied at creation, never read live)."""
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
    if detailed:
        await client.patch(
            f"/groups/{created['group_id']}/detailed-scoring",
            headers=headers,
            json={"enabled": True},
        )
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


async def _current_match(client: AsyncClient, group_id: str, headers: dict) -> dict:
    """The one in-progress match in the admin schedule snapshot."""
    response = await client.get(f"/groups/{group_id}/schedule", headers=headers)
    assert response.status_code == 200
    courts = [c for c in response.json()["courts"] if c["current_match"] is not None]
    assert len(courts) == 1
    match: dict = courts[0]["current_match"]
    return match


async def test_schedule_snapshot_reports_match_detailed_scoring_flag(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """038: the admin page's court-control block picks its scoring UI from
    this field, so GET /schedule MUST carry the match's own snapshot."""
    enabled_group, _ = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, detailed=True
    )
    enabled_headers = {"Authorization": f"Bearer {enabled_group['admin_token']}"}
    match = await _current_match(client, enabled_group["group_id"], enabled_headers)
    assert match["detailed_scoring_enabled"] is True

    plain_group, _ = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    plain_headers = {"Authorization": f"Bearer {plain_group['admin_token']}"}
    plain_match = await _current_match(client, plain_group["group_id"], plain_headers)
    assert plain_match["detailed_scoring_enabled"] is False


async def test_schedule_snapshot_flag_does_not_follow_a_mid_match_group_toggle(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """Constitution III: a group-setting change MUST NOT retroactively alter a
    match already underway. Turning the group toggle OFF mid-match leaves the
    running match in detailed mode — the admin board keeps offering the detail
    dialog for it, and only the NEXT match starts plain."""
    created, _ = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token, detailed=True
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    before = await _current_match(client, created["group_id"], headers)
    assert before["detailed_scoring_enabled"] is True

    disable = await client.patch(
        f"/groups/{created['group_id']}/detailed-scoring",
        headers=headers,
        json={"enabled": False},
    )
    assert disable.status_code == 200
    assert disable.json()["detailed_scoring_enabled"] is False

    still_detailed = await _current_match(client, created["group_id"], headers)
    assert still_detailed["detailed_scoring_enabled"] is True


async def test_schedule_snapshot_carries_match_scoring_rules(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """039-match-point-confirm: the admin board needs the match's own
    target/cap to tell whether the next point would END the match.
    deuce_threshold is deliberately NOT exposed — it takes no part in the
    win test (match_wins()), and sending it would only invite misuse."""
    created, _ = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    match = await _current_match(client, created["group_id"], headers)

    assert match["target_score"] == 21
    assert match["cap_score"] == 30
    assert "deuce_threshold" not in match


async def test_schedule_snapshot_scoring_rules_do_not_follow_the_group(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    """Constitution III: changing the group's scoring settings mid-match MUST
    NOT move an in-progress match's goalposts, or the confirm dialog would
    fire at a different score than the one being played to."""
    created, _ = await _create_group_with_active_match(
        client, db_session, valid_turnstile_token
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}

    await db_session.execute(
        text("UPDATE groups SET target_score = 15, cap_score = 21 WHERE id = :id"),
        {"id": created["group_id"]},
    )
    await db_session.commit()

    match = await _current_match(client, created["group_id"], headers)

    assert match["target_score"] == 21
    assert match["cap_score"] == 30
