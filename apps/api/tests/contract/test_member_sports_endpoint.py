"""043 T103: POST/DELETE /members/me/sports, GET /sports `custom[]`, and
opening a group from a custom activity (contracts/sports-api.md §2, §3)."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio

DODGEBALL: dict[str, Any] = {
    "name": "躲避球對抗",
    "type_key": "generic",
    "team_size_options": [2],
    "defaults": {
        "team_size": 2,
        "end_mode": "manual",
        "target_score": 1,
        "win_by": 1,
        "cap_score": None,
        "allow_draw": True,
        "score_steps": [1, 2],
        "type_params": {},
        "nouns": {"venue": "arena", "score": "point", "member": "player"},
    },
}


async def _login(
    client: AsyncClient, session: AsyncSession, email: str, *, verified: bool = True
) -> dict[str, str]:
    member = await register(session, email, "abc12345")
    member.nickname = email.split("@")[0][:20]
    if verified:
        member.verification_status = "verified"
    await session.commit()
    response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_create_list_and_delete(client: AsyncClient, db_session: AsyncSession) -> None:
    auth = await _login(client, db_session, "custom@example.com")
    created = await client.post("/members/me/sports", headers=auth, json=DODGEBALL)
    assert created.status_code == 201, created.text
    body = created.json()
    assert set(body) == {"id", "name", "type_key", "team_size_options", "defaults", "created_at"}
    assert body["name"] == "躲避球對抗"
    assert body["defaults"]["score_steps"] == [1, 2]

    catalog = (await client.get("/sports", headers=auth)).json()
    assert [c["id"] for c in catalog["custom"]] == [body["id"]]
    assert (await client.get("/sports")).json()["custom"] == []

    deleted = await client.delete(f"/members/me/sports/{body['id']}", headers=auth)
    assert deleted.status_code == 204
    again = await client.delete(f"/members/me/sports/{body['id']}", headers=auth)
    assert again.status_code == 404
    assert again.json()["error_code"] == "CUSTOM_SPORT_NOT_FOUND"


async def test_unverified_member_is_refused(client: AsyncClient, db_session: AsyncSession) -> None:
    auth = await _login(client, db_session, "unverified@example.com", verified=False)
    response = await client.post("/members/me/sports", headers=auth, json=DODGEBALL)
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": ""}, None),
        ({"name": "x" * 21}, None),
        ({"type_key": "polo"}, "type_key"),
        ({"team_size_options": [3]}, "team_size_options"),
        ({"defaults": {**DODGEBALL["defaults"], "team_size": 1}}, "defaults.team_size"),
        ({"defaults": {**DODGEBALL["defaults"], "score_steps": [2, 1]}}, "defaults.score_steps"),
        (
            {"defaults": {**DODGEBALL["defaults"], "end_mode": "target", "allow_draw": True}},
            "defaults.allow_draw",
        ),
        ({"defaults": {**DODGEBALL["defaults"], "type_params": {"x": 1}}}, "defaults.type_params"),
        # Review finding: a target of 0 with a cap used to pass (cap 0 ended every match).
        (
            {
                "defaults": {
                    **DODGEBALL["defaults"],
                    "end_mode": "target",
                    "allow_draw": False,
                    "target_score": 0,
                    "cap_score": 0,
                }
            },
            "defaults.target_score",
        ),
    ],
)
async def test_invalid_bodies_are_422(
    change: dict[str, Any], field: str | None, client: AsyncClient, db_session: AsyncSession
) -> None:
    auth = await _login(client, db_session, "bad@example.com")
    response = await client.post("/members/me/sports", headers=auth, json={**DODGEBALL, **change})
    assert response.status_code == 422, response.text
    if field is not None:
        assert response.json()["detail"]["field"] == field


async def test_names_and_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    auth = await _login(client, db_session, "names@example.com")
    first = await client.post("/members/me/sports", headers=auth, json=DODGEBALL)
    assert first.status_code == 201
    taken = await client.post("/members/me/sports", headers=auth, json=DODGEBALL)
    assert taken.status_code == 409
    assert taken.json()["error_code"] == "CUSTOM_SPORT_NAME_TAKEN"
    # A built-in activity's name is the member's to reuse.
    same_as_builtin = await client.post(
        "/members/me/sports", headers=auth, json={**DODGEBALL, "name": "羽球"}
    )
    assert same_as_builtin.status_code == 201
    for i in range(18):
        ok = await client.post(
            "/members/me/sports", headers=auth, json={**DODGEBALL, "name": f"活動{i}"}
        )
        assert ok.status_code == 201, ok.text
    limit = await client.post(
        "/members/me/sports", headers=auth, json={**DODGEBALL, "name": "第二十一"}
    )
    assert limit.status_code == 409
    assert limit.json()["error_code"] == "CUSTOM_SPORT_LIMIT"


async def _open(
    client: AsyncClient, token: str, sport: dict[str, Any], headers: dict[str, str] | None = None
) -> Any:
    return await client.post(
        "/groups",
        headers=headers or {},
        json={
            "max_members": 8,
            "team_size": 2,
            "sport": sport,
            "scheduling_mechanism": "manual",
            "creator_nickname": "開團",
            "turnstile_token": token,
        },
    )


async def test_open_a_group_from_a_custom_activity(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    owner = await _login(client, db_session, "owner@example.com")
    other = await _login(client, db_session, "other@example.com")
    sport_id = (await client.post("/members/me/sports", headers=owner, json=DODGEBALL)).json()[
        "id"
    ]
    custom = {"sport_key": "custom", "custom_sport_id": sport_id}

    assert (await _open(client, valid_turnstile_token, custom)).status_code == 403
    forbidden = await _open(client, valid_turnstile_token, custom, other)
    assert forbidden.status_code == 403
    assert forbidden.json()["error_code"] == "CUSTOM_SPORT_FORBIDDEN"

    opened = await _open(client, valid_turnstile_token, custom, owner)
    assert opened.status_code == 201, opened.text
    group_id = opened.json()["group_id"]
    admin_headers = {"Authorization": f"Bearer {opened.json()['admin_token']}"}
    admin = (await client.get(f"/groups/{group_id}/admin", headers=admin_headers)).json()
    public = (await client.get(f"/groups/{group_id}")).json()
    assert public["sport"]["name"] == "躲避球對抗"
    assert public["sport"]["type_key"] == "generic"
    assert admin["score_steps"] == [1, 2]
    assert admin["end_mode"] == "manual"

    # Deleting the activity leaves the group's own snapshot alone.
    await client.delete(f"/members/me/sports/{sport_id}", headers=owner)
    after = (await client.get(f"/groups/{group_id}")).json()
    assert after["sport"]["name"] == "躲避球對抗"


async def test_guest_other_activity_keeps_its_name(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    opened = await _open(
        client, valid_turnstile_token, {"sport_key": "other", "name": "趣味賽"}
    )
    assert opened.status_code == 201, opened.text
    public = (await client.get(f"/groups/{opened.json()['group_id']}")).json()
    assert public["sport"]["name"] == "趣味賽"
    assert public["sport"]["sport_key"] == "other"
