"""Unit test: GET /groups lists the viewer's own groups first — the group a
Member is active in, any group they created, or (for a Guest) the group the
client passes as `pinned_group_id`. Everything else keeps newest-first, and
the pinning happens in the query, so it holds across pages."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group import service
from app.domains.group.models import Group
from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _register_and_login(client: AsyncClient, db_session: AsyncSession, email: str) -> str:
    member = await register(db_session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = "小明"
    await db_session.commit()
    login_response = await client.post(
        "/auth/login", json={"email": email, "password": "abc12345"}
    )
    return str(login_response.json()["access_token"])


async def _make_group(client: AsyncClient, valid_turnstile_token: str, name: str) -> dict:
    response = await client.post(
        "/groups",
        json={
            "name": name,
            "max_members": 8,
            "match_mode": "doubles",
            "scheduling_mechanism": "manual",
            "creator_nickname": "開團者",
            "turnstile_token": valid_turnstile_token,
        },
    )
    assert response.status_code == 201
    return response.json()


def _names(response_json: dict) -> list[str]:
    return [g["name"] for g in response_json["groups"]]


async def test_joined_group_is_listed_first(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    joined = await _make_group(client, valid_turnstile_token, "置頂-已加入")
    await _make_group(client, valid_turnstile_token, "置頂-較新")
    access_token = await _register_and_login(client, db_session, "pin-joined@example.com")
    headers = {"Authorization": f"Bearer {access_token}"}
    join_response = await client.post(
        f"/groups/{joined['group_id']}/join", headers=headers, json={}
    )
    assert join_response.status_code == 201

    names = _names((await client.get("/groups", headers=headers)).json())
    assert names[0] == "置頂-已加入"
    # Not pinned for anyone else.
    assert _names((await client.get("/groups")).json())[0] == "置頂-較新"


async def test_created_groups_are_listed_first_newest_first(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    older_own = await _make_group(client, valid_turnstile_token, "置頂-我開的舊團")
    newer_own = await _make_group(client, valid_turnstile_token, "置頂-我開的新團")
    await _make_group(client, valid_turnstile_token, "置頂-別人的團")
    access_token = await _register_and_login(client, db_session, "pin-creator@example.com")
    member_id = await db_session.scalar(
        select(Member.id).where(Member.email == "pin-creator@example.com")
    )
    await db_session.execute(
        update(Group)
        .where(Group.id.in_([uuid.UUID(older_own["group_id"]), uuid.UUID(newer_own["group_id"])]))
        .values(created_by_member_id=member_id)
    )
    await db_session.commit()

    names = _names(
        (await client.get("/groups", headers={"Authorization": f"Bearer {access_token}"})).json()
    )
    assert names[:3] == ["置頂-我開的新團", "置頂-我開的舊團", "置頂-別人的團"]


async def test_guest_pinned_group_id_is_listed_first(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    mine = await _make_group(client, valid_turnstile_token, "置頂-訪客的團")
    await _make_group(client, valid_turnstile_token, "置頂-訪客看到的新團")

    response = await client.get("/groups", params={"pinned_group_id": mine["group_id"]})
    assert response.status_code == 200
    assert _names(response.json())[0] == "置頂-訪客的團"


async def test_pinned_group_id_is_ignored_for_a_member(
    client: AsyncClient, db_session: AsyncSession, valid_turnstile_token: str
) -> None:
    other = await _make_group(client, valid_turnstile_token, "置頂-不屬於會員的團")
    await _make_group(client, valid_turnstile_token, "置頂-最新的團")
    access_token = await _register_and_login(client, db_session, "pin-ignored@example.com")

    response = await client.get(
        "/groups",
        params={"pinned_group_id": other["group_id"]},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert _names(response.json())[0] == "置頂-最新的團"


async def test_pinned_group_is_on_page_one_only(
    client: AsyncClient,
    db_session: AsyncSession,
    valid_turnstile_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "_GROUP_LIST_PAGE_SIZE", 2)
    oldest = await _make_group(client, valid_turnstile_token, "置頂分頁-最舊")
    for i in range(3):
        await _make_group(client, valid_turnstile_token, f"置頂分頁-{i}")

    params = {"pinned_group_id": oldest["group_id"], "group_name": "置頂分頁"}
    page1 = (await client.get("/groups", params={**params, "page": 1})).json()
    page2 = (await client.get("/groups", params={**params, "page": 2})).json()
    assert page1["total_pages"] == 2
    assert _names(page1) == ["置頂分頁-最舊", "置頂分頁-2"]
    assert _names(page2) == ["置頂分頁-1", "置頂分頁-0"]


async def test_pinning_does_not_bypass_filters(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    mine = await _make_group(client, valid_turnstile_token, "置頂-不符篩選")
    await _make_group(client, valid_turnstile_token, "置頂篩選-符合")

    response = await client.get(
        "/groups", params={"pinned_group_id": mine["group_id"], "group_name": "置頂篩選"}
    )
    assert _names(response.json()) == ["置頂篩選-符合"]
