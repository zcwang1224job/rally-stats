"""043 T088: the generic sport type's params, estimate and dashboard grid."""

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.sports import registry
from app.sports.plugin import DashboardContext, DashboardRow
from app.sports.types import register_all


@pytest.fixture(autouse=True)
def _plugins() -> None:
    register_all()


def test_params_are_an_empty_object() -> None:
    plugin = registry.get("generic")
    assert plugin.parse_params({}).model_dump() == {}
    with pytest.raises(ValidationError):
        plugin.parse_params({"anything": 1})
    assert plugin.event_schemas() == {}
    assert plugin.direct_points is True


def test_estimate_minutes() -> None:
    plugin = registry.get("generic")
    assert plugin.estimate_minutes(end_mode="target", target_score=10, type_params={}) == (
        pytest.approx(6.0)
    )
    assert plugin.estimate_minutes(end_mode="manual", target_score=10, type_params={}) == 15.0


def _row(score_a: int, score_b: int, result: str) -> DashboardRow:
    match = cast(Any, SimpleNamespace(id=uuid.uuid4(), score_a=score_a, score_b=score_b))
    return DashboardRow(
        match=match,
        player_key="m:me",
        my_team="A",
        result=cast(Any, result),
        opponent_keys=("r:x",),
        opponent_names=("X",),
    )


@pytest.mark.asyncio
async def test_dashboard_grid_counts_draws() -> None:
    plugin = registry.get("generic")
    ctx = DashboardContext(
        mine=[_row(3, 1, "win"), _row(2, 2, "draw"), _row(0, 4, "loss")],
        peers={},
        me_key="m:me",
    )
    grid, table = await plugin.dashboard_sections(cast(Any, None), ctx)
    assert grid.kind == "metric_grid"
    assert table.kind == "stat_table"
    values = {m["key"]: m["value"] for m in grid.data["metrics"]}
    assert list(values) == [
        "match_win_rate",
        "matches",
        "wins",
        "losses",
        "draws",
        "avg_points_for",
        "avg_points_against",
    ]
    assert values["match_win_rate"] == pytest.approx(1 / 3)
    assert (values["wins"], values["losses"], values["draws"]) == (1.0, 1.0, 1.0)
    assert values["avg_points_for"] == pytest.approx(5 / 3)
    assert values["avg_points_against"] == pytest.approx(7 / 3)


@pytest.mark.asyncio
async def test_empty_dashboard_is_a_note() -> None:
    plugin = registry.get("generic")
    sections = await plugin.dashboard_sections(
        cast(Any, None), DashboardContext(mine=[], peers={}, me_key="m:me")
    )
    assert [s.kind for s in sections] == ["text_note"]
