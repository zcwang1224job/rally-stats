"""043 T109: `sport` on GET /groups and GET /members/me/groups
(contracts/sports-api.md §4, US6)."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _open(
    client: AsyncClient,
    token: str,
    sport: dict[str, Any],
    *,
    team_size: int = 1,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = await client.post(
        "/groups",
        headers=headers or {},
        json={
            "max_members": 8,
            "team_size": team_size,
            "sport": sport,
            "scheduling_mechanism": "manual",
            "creator_nickname": "開團",
            "turnstile_token": token,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _disband(client: AsyncClient, created: dict[str, Any]) -> None:
    response = await client.post(
        f"/groups/{created['group_id']}/disband",
        headers={"Authorization": f"Bearer {created['admin_token']}"},
    )
    assert response.status_code in (200, 204), response.text


async def test_group_list_filter(client: AsyncClient, valid_turnstile_token: str) -> None:
    badminton = await _open(client, valid_turnstile_token, {"sport_key": "badminton"})
    billiards = await _open(client, valid_turnstile_token, {"sport_key": "billiards"})
    other = await _open(
        client, valid_turnstile_token, {"sport_key": "other", "name": "趣味賽"}, team_size=2
    )

    async def ids(**params: Any) -> set[str]:
        response = await client.get("/groups", params=params)
        assert response.status_code == 200, response.text
        return {item["group_id"] for item in response.json()["groups"]}

    assert await ids(sport="billiards") == {billiards["group_id"]}
    assert await ids(sport="custom_or_other") == {other["group_id"]}
    assert await ids(sport="badminton", match_mode="singles") == {badminton["group_id"]}
    assert await ids(sport="billiards", match_mode="doubles") == set()
    assert await ids() >= {badminton["group_id"], billiards["group_id"], other["group_id"]}
    listed = (await client.get("/groups", params={"sport": "billiards"})).json()["groups"]
    assert listed[0]["sport"]["sport_key"] == "billiards"

    for bad in ("polo", "custom", "custom:not-a-uuid"):
        invalid = await client.get("/groups", params={"sport": bad})
        assert invalid.status_code == 422, bad
        assert invalid.json()["error_code"] == "INVALID_SPORT_FILTER"


async def _member(
    client: AsyncClient, session: AsyncSession, email: str
) -> dict[str, str]:
    member = await register(session, email, "abc12345")
    member.nickname = email.split("@")[0]
    member.verification_status = "verified"
    await session.commit()
    login = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_my_groups_filter(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    me = await _member(client, db_session, "mine@example.com")
    someone = await _member(client, db_session, "someone@example.com")
    sport_body = {
        "name": "躲避球",
        "type_key": "generic",
        "team_size_options": [1],
        "defaults": {
            "team_size": 1,
            "end_mode": "manual",
            "target_score": 1,
            "win_by": 1,
            "allow_draw": True,
            "score_steps": [1],
        },
    }
    mine_id = (await client.post("/members/me/sports", headers=me, json=sport_body)).json()["id"]
    theirs_id = (
        await client.post("/members/me/sports", headers=someone, json=sport_body)
    ).json()["id"]

    # A member is active in one group at a time: disband each before the next.
    custom = await _open(
        client,
        valid_turnstile_token,
        {"sport_key": "custom", "custom_sport_id": mine_id},
        headers=me,
    )
    await _disband(client, custom)
    badminton = await _open(client, valid_turnstile_token, {"sport_key": "badminton"}, headers=me)

    async def ids(**params: Any) -> set[str]:
        response = await client.get("/members/me/groups", headers=me, params=params)
        assert response.status_code == 200, response.text
        return {item["group_id"] for item in response.json()["groups"]}

    assert await ids() == {custom["group_id"], badminton["group_id"]}
    assert await ids(sport=f"custom:{mine_id}") == {custom["group_id"]}
    assert await ids(sport=f"custom:{theirs_id}") == set()
    assert await ids(sport="custom_or_other") == {custom["group_id"]}
    assert await ids(sport="badminton", role="creator") == {badminton["group_id"]}
    rows = (await client.get("/members/me/groups", headers=me)).json()["groups"]
    labels = {row["group_id"]: row["sport"] for row in rows}
    assert labels[custom["group_id"]]["name"] == "躲避球"
    assert labels[badminton["group_id"]]["sport_key"] == "badminton"
