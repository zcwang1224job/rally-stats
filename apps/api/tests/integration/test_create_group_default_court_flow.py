"""Integration test: 021-group-creation-defaults end-to-end through the
real HTTP layer, per quickstart.md 情境 3/4 — a freshly created group
already has a "球場一" court that behaves exactly like a manually-created
one, and a failed group-creation attempt leaves zero orphan courts."""

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.models import Court

pytestmark = pytest.mark.asyncio


async def test_default_court_exists_and_behaves_like_a_manual_court(
    client: AsyncClient, valid_turnstile_token: str
) -> None:
    created = (
        await client.post(
            "/groups",
            json={
                "max_members": 4,
                "match_mode": "singles",
                "scheduling_mechanism": "fair_rotation",
                "creator_nickname": "阿宏",
                "turnstile_token": valid_turnstile_token,
            },
        )
    ).json()
    admin_headers = {"Authorization": f"Bearer {created['admin_token']}"}

    courts_response = await client.get(
        f"/groups/{created['group_id']}/courts", headers=admin_headers
    )
    assert courts_response.status_code == 200
    courts = courts_response.json()["courts"]
    assert len(courts) == 1
    default_court = courts[0]
    assert default_court["name"] == "球場一"
    assert default_court["scoreboard_link_version"] == 0

    # FR-008: the auto-created court supports existing court operations
    # exactly like a manually-created one — regenerating its scoreboard
    # link here.
    regenerate_response = await client.post(
        f"/courts/{default_court['court_id']}/regenerate-scoreboard-link",
        headers=admin_headers,
        json={"expected_version": 0},
    )
    assert regenerate_response.status_code == 200
    body = regenerate_response.json()
    assert body["scoreboard_token"] != default_court["scoreboard_token"]
    assert body["scoreboard_link_version"] == 1


async def test_failed_group_creation_leaves_no_orphan_court(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    async def _fail_verify(token: str, remote_ip: str | None = None) -> None:
        raise ApiError("CAPTCHA_INVALID", status_code=400)

    monkeypatch.setattr("app.domains.group.router.verify_turnstile_token", _fail_verify)

    before = (await db_session.execute(select(func.count()).select_from(Court))).scalar_one()

    response = await client.post(
        "/groups",
        json={
            "max_members": 4,
            "match_mode": "singles",
            "scheduling_mechanism": "fair_rotation",
            "creator_nickname": "阿宏",
            "turnstile_token": "definitely-invalid",
        },
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CAPTCHA_INVALID"

    after = (await db_session.execute(select(func.count()).select_from(Court))).scalar_one()
    assert after == before
