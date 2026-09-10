"""Contract test for PATCH /courts/{court_id} per
specs/002-court-management/contracts/courts-api.md — this endpoint has
never had any test coverage until now (021-group-creation-defaults,
research.md #3).

Every group created via `POST /groups` now already has one auto-created
court named "球場一" (021-group-creation-defaults FR-006) — these tests
use that existing court directly rather than creating a redundant
same-named one (which would collide with it)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group_with_default_court(client: AsyncClient, token: str) -> dict:
    group_response = await client.post(
        "/groups",
        json={
            "name": "Rename Court Contract Test",
            "max_members": 4,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿宏",
            "turnstile_token": token,
        },
    )
    assert group_response.status_code == 201
    group = group_response.json()
    headers = {"Authorization": f"Bearer {group['admin_token']}"}

    courts_response = await client.get(f"/groups/{group['group_id']}/courts", headers=headers)
    assert courts_response.status_code == 200
    courts = courts_response.json()["courts"]
    assert len(courts) == 1  # the auto-created "球場一"
    return {**group, "headers": headers, "court": courts[0]}


async def test_rename_court_succeeds_and_keeps_tokens(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    ctx = await _create_group_with_default_court(client, valid_turnstile_token)

    response = await client.patch(
        f"/courts/{ctx['court']['court_id']}",
        headers=ctx["headers"],
        json={"name": "羽球場A"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "羽球場A"
    assert body["scoreboard_token"] == ctx["court"]["scoreboard_token"]
    assert body["control_panel_token"] == ctx["court"]["control_panel_token"]


async def test_rename_court_duplicate_name_rejected(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    ctx = await _create_group_with_default_court(client, valid_turnstile_token)
    second_court = (
        await client.post(
            f"/groups/{ctx['group_id']}/courts", headers=ctx["headers"], json={"name": "場地B"}
        )
    ).json()

    response = await client.patch(
        f"/courts/{second_court['court_id']}",
        headers=ctx["headers"],
        json={"name": ctx["court"]["name"]},  # "球場一", already taken
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "COURT_NAME_ALREADY_EXISTS"


async def test_rename_deleted_court_rejected(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    ctx = await _create_group_with_default_court(client, valid_turnstile_token)
    delete_response = await client.delete(
        f"/courts/{ctx['court']['court_id']}", headers=ctx["headers"]
    )
    assert delete_response.status_code == 200

    response = await client.patch(
        f"/courts/{ctx['court']['court_id']}", headers=ctx["headers"], json={"name": "新名字"}
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "COURT_DELETED"


async def test_rename_court_requires_admin_token(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    ctx = await _create_group_with_default_court(client, valid_turnstile_token)

    response = await client.patch(
        f"/courts/{ctx['court']['court_id']}", json={"name": "新名字"}
    )
    assert response.status_code == 401
