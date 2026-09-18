"""Contract tests for 036-match-insights-benchmarks US3, per
specs/036-match-insights-benchmarks/contracts/group-benchmark-api.md."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.member.models import Member
from app.domains.member.service import register
from app.domains.roster.models import RosterEntry
from tests.unit.domains._match_history import make_entry, make_group, make_played_match

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
METRIC_FIELDS = {
    "key",
    "kind",
    "better_when",
    "mine",
    "status",
    "group_average",
    "pool_size",
    "rank",
}
# Distinctive on purpose: the anonymity scan below looks for these strings.
OTHER_NICKNAMES = ("祕密會員甲", "祕密訪客乙", "祕密訪客丙")


async def _register(session: AsyncSession, email: str, *, verified: bool = True) -> Member:
    member = await register(session, email, "abc12345")
    if verified:
        member.verification_status = "verified"
        await session.commit()
    return member


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": "abc12345"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _league(
    session: AsyncSession, me: Member, name: str, my_status: str = "active"
) -> tuple[Group, list[RosterEntry], Member]:
    """A singles group of four — me, another member, two guests — where every
    pair has played twice (six matches each)."""
    other = await _register(session, f"bm-other-{uuid.uuid4().hex[:8]}@example.com")
    group = await make_group(session, name, match_mode="singles")
    mine = await make_entry(session, group, "我", me.id, status=my_status)
    others = [
        await make_entry(session, group, OTHER_NICKNAMES[0], other.id),
        await make_entry(session, group, OTHER_NICKNAMES[1]),
        await make_entry(session, group, OTHER_NICKNAMES[2]),
    ]
    players = [mine, *others]
    age = 0
    for _ in range(2):
        for index, first in enumerate(players):
            for second in players[index + 1 :]:
                await make_played_match(
                    session,
                    group,
                    team_a=[first.id],
                    team_b=[second.id],
                    sides="A" * 21,
                    ended_at=NOW - timedelta(days=age),
                )
                age += 1
    return group, others, other


async def test_both_endpoints_require_a_verified_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    for path in (
        "/members/me/benchmark-groups",
        f"/members/me/group-benchmark?group_id={uuid.uuid4()}",
    ):
        anonymous = await client.get(path)
        assert anonymous.status_code == 401
        assert anonymous.json()["error_code"] == "MEMBER_TOKEN_INVALID"

    await _register(db_session, "bm-unverified@example.com", verified=False)
    headers = await _login(client, "bm-unverified@example.com")
    for path in (
        "/members/me/benchmark-groups",
        f"/members/me/group-benchmark?group_id={uuid.uuid4()}",
    ):
        locked = await client.get(path, headers=headers)
        assert locked.status_code == 403
        assert locked.json()["error_code"] == "EMAIL_NOT_VERIFIED"


async def test_benchmark_groups_shape_and_default_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    me = await _register(db_session, "bm-groups@example.com")
    await _league(db_session, me, "BM Busy")
    quiet = await make_group(db_session, "BM Quiet")
    await make_entry(db_session, quiet, "我", me.id, status="left")

    response = await client.get(
        "/members/me/benchmark-groups", headers=await _login(client, "bm-groups@example.com")
    )

    assert response.status_code == 200
    groups = response.json()["groups"]
    assert [(g["name"], g["my_completed_matches"], g["member_status"]) for g in groups] == [
        ("BM Busy", 6, "active"),
        ("BM Quiet", 0, "left"),
    ]
    assert set(groups[0]) == {
        "group_id",
        "group_number",
        "name",
        "status",
        "member_status",
        "my_completed_matches",
    }


async def test_a_member_of_no_group_gets_an_empty_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(db_session, "bm-nogroups@example.com")
    response = await client.get(
        "/members/me/benchmark-groups", headers=await _login(client, "bm-nogroups@example.com")
    )
    assert response.json() == {"groups": []}


async def test_group_benchmark_shape(client: AsyncClient, db_session: AsyncSession) -> None:
    me = await _register(db_session, "bm-shape@example.com")
    group, _, _ = await _league(db_session, me, "BM Shape")

    response = await client.get(
        f"/members/me/group-benchmark?group_id={group.id}",
        headers=await _login(client, "bm-shape@example.com"),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"group", "total_matches", "my_matches", "metrics", "insights"}
    assert body["group"] == {"group_id": str(group.id), "name": "BM Shape"}
    assert (body["total_matches"], body["my_matches"]) == (12, 6)
    assert len(body["metrics"]) == 23
    assert all(set(metric) == METRIC_FIELDS for metric in body["metrics"])
    points_for = next(m for m in body["metrics"] if m["key"] == "avg_points_for")
    assert (points_for["status"], points_for["pool_size"], points_for["rank"]) == ("ok", 4, 1)
    assert points_for["mine"]["value"] == 21.0
    saved = next(m for m in body["metrics"] if m["key"] == "match_points_saved")
    assert saved["better_when"] is None and saved["rank"] is None
    assert body["insights"]["benchmark_group_name"] == "BM Shape"
    from_group = [i for i in body["insights"]["strengths"] if i["source"] == "benchmark"]
    assert from_group and all(i["rule"] == "benchmark_quartile" for i in from_group)


def _benchmark_text(body: dict[str, object]) -> str:
    """Everything the group comparison itself produced: the group, the 23
    metrics, and any sentence whose source is the group. `insights` also holds
    the viewer's OWN sentences (strengths, recent changes, partners/opponents)
    — the same ones their dashboard response carries — which are not the
    benchmark's and are checked separately below."""
    insights = body["insights"]
    assert isinstance(insights, dict)
    from_group = [
        item
        for name in ("strengths", "weaknesses", "recent", "matchups")
        for item in insights[name]
        if item["source"] == "benchmark"
    ]
    return json.dumps(
        {"group": body["group"], "metrics": body["metrics"], "from_group": from_group},
        ensure_ascii=False,
    )


async def test_nothing_about_any_other_player_leaves_the_server(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """FR-032 / SC-007 / Clarifications 2026-09-18: anonymity is enforced by
    what the server sends, not by what the page chooses to draw."""
    me = await _register(db_session, "bm-anon@example.com")
    group, others, other_member = await _league(db_session, me, "BM Anon")

    response = await client.get(
        f"/members/me/group-benchmark?group_id={group.id}",
        headers=await _login(client, "bm-anon@example.com"),
    )

    assert response.status_code == 200
    text = _benchmark_text(response.json())
    for nickname in OTHER_NICKNAMES:
        assert nickname not in text
    assert str(other_member.id) not in text
    for entry in others:
        assert str(entry.id) not in text
    assert "rank_from_bottom" not in json.dumps(response.json())  # an insight-rule internal


async def test_my_own_partner_sentences_are_the_dashboards_and_nothing_more(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The merged summary keeps MY partner/opponent sentences — my own record
    with people from my own match list, exactly as `/match-dashboard` already
    sends them. They are the only place another player's name may appear, and
    they say nothing the group computed about that player."""
    me = await _register(db_session, "bm-own@example.com")
    group = await make_group(db_session, "BM Own", match_mode="doubles")
    mine = await make_entry(db_session, group, "我", me.id)
    good = await make_entry(db_session, group, "祕密好搭檔")
    poor = await make_entry(db_session, group, "祕密壞搭檔")
    rivals = [
        (await make_entry(db_session, group, "祕密對手甲")).id,
        (await make_entry(db_session, group, "祕密對手乙")).id,
    ]
    for age in range(6):
        await make_played_match(
            db_session,
            group,
            team_a=[mine.id, good.id],
            team_b=rivals,
            sides="A" * 21,
            ended_at=NOW - timedelta(days=age),
        )
        await make_played_match(
            db_session,
            group,
            team_a=[mine.id, poor.id],
            team_b=rivals,
            sides="B" * 21,
            ended_at=NOW - timedelta(days=20 + age),
        )
    headers = await _login(client, "bm-own@example.com")

    benchmark = (
        await client.get(f"/members/me/group-benchmark?group_id={group.id}", headers=headers)
    ).json()
    dashboard = (await client.get("/members/me/match-dashboard", headers=headers)).json()

    named = benchmark["insights"]["matchups"]
    assert [item["player"]["nickname"] for item in named] == ["祕密好搭檔"]
    assert named == dashboard["insights"]["matchups"]  # nothing new: the dashboard says the same
    assert set(named[0]["params"]) == {"win_rate", "matches", "wins", "losses", "baseline", "diff"}
    # …and the comparison itself still names nobody.
    assert "祕密" not in _benchmark_text(benchmark)


@pytest.mark.parametrize("my_status", ["left", "kicked"])
async def test_a_former_member_may_still_compare(
    client: AsyncClient, db_session: AsyncSession, my_status: str
) -> None:
    me = await _register(db_session, f"bm-former-{my_status}@example.com")
    group, _, _ = await _league(db_session, me, f"BM {my_status}", my_status=my_status)
    group.status = "disbanded"
    await db_session.commit()

    response = await client.get(
        f"/members/me/group-benchmark?group_id={group.id}",
        headers=await _login(client, f"bm-former-{my_status}@example.com"),
    )
    assert response.status_code == 200


async def test_a_member_with_two_stints_may_compare(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    me = await _register(db_session, "bm-stints@example.com")
    group, _, _ = await _league(db_session, me, "BM Stints", my_status="left")
    await make_entry(db_session, group, "我又來了", me.id)

    response = await client.get(
        f"/members/me/group-benchmark?group_id={group.id}",
        headers=await _login(client, "bm-stints@example.com"),
    )
    assert response.status_code == 200  # research.md Decision 7


async def test_a_group_i_never_joined_or_that_does_not_exist_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _register(db_session, "bm-owner@example.com")
    group, _, _ = await _league(db_session, owner, "BM Private")
    await _register(db_session, "bm-outsider@example.com")
    headers = await _login(client, "bm-outsider@example.com")

    for group_id in (group.id, uuid.uuid4()):
        response = await client.get(
            f"/members/me/group-benchmark?group_id={group_id}", headers=headers
        )
        assert response.status_code == 403
        assert response.json()["error_code"] == "GROUP_MEMBERSHIP_NEVER_HELD"
        assert "metrics" not in response.json()

    malformed = await client.get("/members/me/group-benchmark?group_id=nope", headers=headers)
    assert malformed.status_code == 422
    missing = await client.get("/members/me/group-benchmark", headers=headers)
    assert missing.status_code == 422


async def test_filters_are_ignored(client: AsyncClient, db_session: AsyncSession) -> None:
    me = await _register(db_session, "bm-nofilter@example.com")
    group, _, _ = await _league(db_session, me, "BM NoFilter")
    headers = await _login(client, "bm-nofilter@example.com")

    plain = await client.get(f"/members/me/group-benchmark?group_id={group.id}", headers=headers)
    filtered = await client.get(
        f"/members/me/group-benchmark?group_id={group.id}&result=loss&opponent_key=m:{uuid.uuid4()}",
        headers=headers,
    )

    assert filtered.status_code == 200
    assert filtered.json() == plain.json()  # FR-028, FR-032
