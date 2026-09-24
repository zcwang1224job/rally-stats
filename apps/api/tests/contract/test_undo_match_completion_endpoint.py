"""Contract test for POST .../matches/{match_id}/undo-completion (token,
admin, and all-courts-token variants) — 032-cancel-score's "Cancel Score"
action for the match-DECIDING point specifically, since the already-existing
plain POST .../score endpoint's `-1` can't touch a `completed` match at
all (its UPDATE requires status='in_progress')."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_manual_singles_match(
    client: AsyncClient,
    session: AsyncSession,
    token: str,
    group_name: str,
) -> tuple[dict, dict, str]:
    """Manual-scheduling singles group, one court, 2 roster entries manually
    assigned -> in_progress, with cap_score dropped to 1 so a single `+1`
    wins the match outright (the 21pt default would need 21 HTTP round
    trips just to reach a win)."""
    created = (
        await client.post(
            "/groups",
            json={
                "name": group_name,
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "manual",
                "creator_nickname": "P0",
                "turnstile_token": token,
            },
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    group_id = created["group_id"]

    await session.execute(
        text(
            "UPDATE groups SET target_score = 1, deuce_threshold = 1, cap_score = 1 "
            "WHERE id = :id"
        ),
        {"id": group_id},
    )
    await session.commit()
    session.expire_all()

    court = (
        await client.post(f"/groups/{group_id}/courts", headers=headers, json={"name": "1號場"})
    ).json()

    roster_ids = [str(uuid.uuid4()) for _ in range(2)]
    for i, rid in enumerate(roster_ids):
        await session.execute(
            text(
                "INSERT INTO roster_entries (id, group_id, nickname, status, is_creator) "
                "VALUES (:id, :group_id, :nickname, 'active', false)"
            ),
            {"id": rid, "group_id": group_id, "nickname": f"P{i + 1}"},
        )
    await session.commit()
    session.expire_all()

    teams = {roster_ids[0]: "A", roster_ids[1]: "B"}
    assign_response = await client.post(
        f"/courts/{court['court_id']}/manual-assign",
        headers=headers,
        json={"participant_ids": roster_ids, "teams": teams},
    )
    assert assign_response.status_code == 201, assign_response.text
    match_id = assign_response.json()["match_id"]
    return created, court, match_id


async def test_undo_match_completion_via_control_panel_token_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id = await _create_manual_singles_match(
        client, db_session, valid_turnstile_token, "Undo Completion Token"
    )
    token = court["control_panel_token"]

    win = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/score", json={"side": "A", "delta": 1}
    )
    assert win.status_code == 200, win.text
    assert win.json()["status"] == "completed"

    response = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/undo-completion", json={"side": "A"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] is True
    assert body["status"] == "in_progress"
    assert body["score_a"] == 0
    assert body["winner_team"] is None


async def test_undo_match_completion_via_admin_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id = await _create_manual_singles_match(
        client, db_session, valid_turnstile_token, "Undo Completion Admin"
    )
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    token = court["control_panel_token"]

    win = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/score", json={"side": "B", "delta": 1}
    )
    assert win.status_code == 200, win.text
    assert win.json()["status"] == "completed"

    response = await client.post(
        f"/groups/{created['group_id']}/courts/{court['court_id']}/matches/{match_id}/undo-completion",
        headers=headers,
        json={"side": "B"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] is True
    assert body["status"] == "in_progress"
    assert body["score_b"] == 0


async def test_undo_match_completion_via_all_courts_token_succeeds(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id = await _create_manual_singles_match(
        client, db_session, valid_turnstile_token, "Undo Completion All Courts"
    )
    group_id = created["group_id"]
    all_courts_row = (
        await db_session.execute(
            text("SELECT all_courts_control_panel_token FROM groups WHERE id = :gid"),
            {"gid": group_id},
        )
    ).first()
    assert all_courts_row is not None
    all_courts_token = str(all_courts_row[0])

    win = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/score",
        json={"side": "A", "delta": 1},
    )
    assert win.status_code == 200, win.text

    response = await client.post(
        f"/groups/by-all-courts-token/{all_courts_token}/courts/{court['court_id']}"
        f"/matches/{match_id}/undo-completion",
        json={"side": "A"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] is True
    assert body["status"] == "in_progress"


async def test_undo_match_completion_rejects_when_match_not_completed(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id = await _create_manual_singles_match(
        client, db_session, valid_turnstile_token, "Undo Completion Not Done"
    )

    response = await client.post(
        f"/courts/by-token/{court['control_panel_token']}/matches/{match_id}/undo-completion",
        json={"side": "A"},
    )

    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == "MATCH_NOT_COMPLETED"


async def test_undo_match_completion_rejects_when_side_did_not_win(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    created, court, match_id = await _create_manual_singles_match(
        client, db_session, valid_turnstile_token, "Undo Completion Wrong Side"
    )
    token = court["control_panel_token"]

    win = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/score", json={"side": "A", "delta": 1}
    )
    assert win.status_code == 200, win.text

    response = await client.post(
        f"/courts/by-token/{token}/matches/{match_id}/undo-completion", json={"side": "B"}
    )

    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == "SIDE_DID_NOT_WIN_THIS_MATCH"
