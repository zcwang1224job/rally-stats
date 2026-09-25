"""043 T049: creating and editing a group for an activity
(contracts/sports-api.md §3)."""

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create(client: AsyncClient, token: str, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "max_members": 4,
        "scheduling_mechanism": "fair_rotation",
        "creator_nickname": "小華",
        "turnstile_token": token,
    }
    body.update(overrides)
    return await client.post("/groups", json=body)


async def _admin(client: AsyncClient, created: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    return (await client.get(f"/groups/{created['group_id']}/admin", headers=headers)).json()


async def test_no_sport_means_badminton_exactly_as_before(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await _create(client, valid_turnstile_token, match_mode="singles")
    assert response.status_code == 201
    admin = await _admin(client, response.json())
    assert admin["scoring_mode"] == "21pt"
    assert (admin["target_score"], admin["deuce_threshold"], admin["cap_score"]) == (21, 20, 30)
    assert admin["win_by"] == 2 and admin["end_mode"] == "target"
    group = admin["group"]
    assert group["name"] == "小華的羽球團"
    assert group["match_mode"] == "singles" and group["team_size"] == 1
    assert group["sport"]["sport_key"] == "badminton"
    assert group["sport"]["type_key"] == "net_rally"
    assert group["sport"]["name_key"] == "sports.badminton"


async def test_billiards_takes_its_defaults_and_names(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await _create(
        client, valid_turnstile_token, sport={"sport_key": "billiards"}, team_size=1
    )
    assert response.status_code == 201, response.text
    created = response.json()
    admin = await _admin(client, created)
    assert admin["group"]["sport"]["type_key"] == "frames"
    assert admin["group"]["match_mode"] == "singles"
    assert (admin["target_score"], admin["win_by"], admin["cap_score"]) == (5, 1, None)
    assert admin["type_params"]["frame_scoring_enabled"] is False
    assert admin["group"]["name"] == "小華的撞球團"
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    courts = (await client.get(f"/groups/{created['group_id']}/courts", headers=headers)).json()
    assert courts["courts"][0]["name"] == "球桌一"


async def test_table_tennis_has_no_cap_and_no_modules(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await _create(
        client, valid_turnstile_token, sport={"sport_key": "table_tennis"}, team_size=2
    )
    assert response.status_code == 201, response.text
    admin = await _admin(client, response.json())
    assert (admin["target_score"], admin["win_by"], admin["cap_score"]) == (11, 2, None)
    assert admin["type_params"] == {"modules": {"serve_tracking": False, "shot_placement": False}}
    assert admin["group"]["team_size"] == 2 and admin["group"]["match_mode"] == "doubles"


async def test_other_needs_a_name_and_shows_it(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    missing = await _create(
        client, valid_turnstile_token, sport={"sport_key": "other"}, team_size=1
    )
    assert missing.status_code == 422
    assert missing.json()["error_code"] == "SPORT_NAME_REQUIRED"

    named = await _create(
        client,
        valid_turnstile_token,
        sport={"sport_key": "other", "name": "趣味賽"},
        team_size=1,
    )
    assert named.status_code == 201
    admin = await _admin(client, named.json())
    assert admin["group"]["sport"]["name"] == "趣味賽"
    assert admin["end_mode"] == "manual" and admin["allow_draw"] is True


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"sport": {"sport_key": "billiards"}, "team_size": 2}, "TEAM_SIZE_NOT_ALLOWED"),
        ({"sport": {"sport_key": "curling"}, "team_size": 1}, "UNKNOWN_SPORT"),
        (
            {"sport": {"sport_key": "table_tennis"}, "team_size": 1, "score_steps": []},
            "INVALID_SPORT_PARAMS",
        ),
        (
            {
                "sport": {"sport_key": "billiards"},
                "team_size": 1,
                "type_params": {"frame_target": "eleven"},
            },
            "INVALID_SPORT_PARAMS",
        ),
    ],
)
async def test_invalid_activity_choices_are_refused(
    client: AsyncClient, valid_turnstile_token: str, overrides: dict[str, Any], error_code: str
) -> None:
    response = await _create(client, valid_turnstile_token, **overrides)
    assert response.status_code == 422
    assert response.json()["error_code"] == error_code


async def test_match_mode_and_team_size_must_agree(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    response = await _create(client, valid_turnstile_token, match_mode="doubles", team_size=1)
    assert response.status_code == 422


async def test_the_activity_cannot_change_but_parameters_can(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = (
        await _create(
            client, valid_turnstile_token, sport={"sport_key": "table_tennis"}, team_size=1
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    refused = await client.patch(
        f"/groups/{created['group_id']}",
        headers=headers,
        json={"expected_version": 0, "sport": {"sport_key": "badminton"}},
    )
    assert refused.status_code == 409
    assert refused.json()["error_code"] == "SPORT_IMMUTABLE"

    changed = await client.patch(
        f"/groups/{created['group_id']}/scoring-settings",
        headers=headers,
        json={
            "expected_version": 0,
            "scoring_mode": "custom",
            "target_score": 21,
            "deuce_threshold": 20,
            "cap_score": None,
            "win_by": 2,
        },
    )
    assert changed.status_code == 200, changed.text
    admin = await _admin(client, created)
    assert (admin["target_score"], admin["cap_score"]) == (21, None)


async def test_detailed_scoring_needs_the_shot_placement_module(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = (
        await _create(
            client, valid_turnstile_token, sport={"sport_key": "table_tennis"}, team_size=1
        )
    ).json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    response = await client.patch(
        f"/groups/{created['group_id']}/detailed-scoring",
        headers=headers,
        json={"enabled": True},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "MODULE_NOT_SUPPORTED"


async def test_badminton_with_explicit_target_is_a_custom_scheme(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    """Review finding: a target sent without a named preset used to keep
    `scoring_mode=21pt` with the preset's deuce (20) above the target."""
    created = await client.post(
        "/groups",
        json={
            "max_members": 4,
            "team_size": 1,
            "sport": {"sport_key": "badminton"},
            "scheduling_mechanism": "manual",
            "creator_nickname": "P0",
            "turnstile_token": valid_turnstile_token,
            "target_score": 15,
        },
    )
    assert created.status_code == 201, created.text
    headers = {"Authorization": f"Bearer {created.json()['admin_token']}"}
    group_id = created.json()["group_id"]
    admin = (await client.get(f"/groups/{group_id}/admin", headers=headers)).json()
    assert admin["scoring_mode"] == "custom"
    assert admin["target_score"] == 15
    assert admin["deuce_threshold"] == 14
