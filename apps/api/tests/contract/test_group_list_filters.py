"""Contract test for GET /groups filter query parameters per
contracts/group-list-api.md (US5)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_group_with_court(
    client: AsyncClient, valid_turnstile_token: str, name: str, court_name: str
) -> dict:
    group_response = await client.post(
        "/groups",
        json={
            "name": name,
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    created = group_response.json()
    headers = {"Authorization": f"Bearer {created['admin_token']}"}
    await client.post(
        f"/groups/{created['group_id']}/courts", headers=headers, json={"name": court_name}
    )
    return created


async def test_filter_by_court_name(client: AsyncClient, valid_turnstile_token: str) -> None:
    await _create_group_with_court(
        client, valid_turnstile_token, "篩選團A", "羽球館北場"
    )
    await _create_group_with_court(
        client, valid_turnstile_token, "篩選團B", "羽球館南場"
    )

    response = await client.get("/groups?court_name=北場")
    assert response.status_code == 200
    names = [g["name"] for g in response.json()["groups"]]
    assert "篩選團A" in names
    assert "篩選團B" not in names


async def test_filter_by_group_name(client: AsyncClient, valid_turnstile_token: str) -> None:
    await client.post(
        "/groups",
        json={
            "name": "週三夜羽球團",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    await client.post(
        "/groups",
        json={
            "name": "週五晨間球敘",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )

    response = await client.get("/groups?group_name=夜羽球")
    assert response.status_code == 200
    names = [g["name"] for g in response.json()["groups"]]
    assert "週三夜羽球團" in names
    assert "週五晨間球敘" not in names


async def test_filter_by_creator_nickname(client: AsyncClient, valid_turnstile_token: str) -> None:
    await client.post(
        "/groups",
        json={
            "name": "阿明開的團",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    await client.post(
        "/groups",
        json={
            "name": "阿華開的團",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿華",
            "turnstile_token": valid_turnstile_token,
        },
    )

    response = await client.get("/groups?creator_nickname=阿明")
    assert response.status_code == 200
    names = [g["name"] for g in response.json()["groups"]]
    assert "阿明開的團" in names
    assert "阿華開的團" not in names


async def test_filter_by_match_mode(client: AsyncClient, valid_turnstile_token: str) -> None:
    await client.post(
        "/groups",
        json={
            "name": "雙打篩選團",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )
    await client.post(
        "/groups",
        json={
            "name": "單打篩選團",
            "max_members": 8,
            "match_mode": "singles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )

    response = await client.get("/groups?match_mode=singles")
    assert response.status_code == 200
    names = [g["name"] for g in response.json()["groups"]]
    assert "單打篩選團" in names
    assert "雙打篩選團" not in names


async def test_filter_by_time_range(client: AsyncClient, valid_turnstile_token: str) -> None:
    await client.post(
        "/groups",
        json={
            "name": "時間篩選團",
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "activity_time_start": "19:00:00",
            "activity_time_end": "21:00:00",
            "creator_nickname": "阿明",
            "turnstile_token": valid_turnstile_token,
        },
    )

    response = await client.get("/groups?time_start=18:00:00&time_end=22:00:00")
    assert response.status_code == 200
    names = [g["name"] for g in response.json()["groups"]]
    assert "時間篩選團" in names

    non_overlap_response = await client.get("/groups?time_start=07:00:00&time_end=09:00:00")
    non_overlap_names = [g["name"] for g in non_overlap_response.json()["groups"]]
    assert "時間篩選團" not in non_overlap_names
