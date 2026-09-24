"""043 T055: the legacy match-dashboard drops what a net rally activity's
modules leave without data (FR-025). Badminton (both modules on) keeps all
23 metrics."""

import pytest

from app.sports import registry
from app.sports.types import register_all

SERVE = {"team_serve", "team_receive", "own_serve", "own_receive"}
ENDING = {
    "winner_share",
    "winners_per_match",
    "errors_per_match",
    "error_share_of_lost",
    "winner_error_ratio",
}


@pytest.fixture(autouse=True)
def _plugins() -> None:
    register_all()


def _hidden(modules: dict[str, bool] | None) -> frozenset[str]:
    params = {} if modules is None else {"modules": modules}
    return registry.get("net_rally").hidden_dashboard_metrics(params)


def test_badminton_hides_nothing() -> None:
    assert _hidden(None) == frozenset()
    assert _hidden({"serve_tracking": True, "shot_placement": True}) == frozenset()


def test_serve_tracking_off_hides_the_four_serve_metrics() -> None:
    assert _hidden({"serve_tracking": False, "shot_placement": True}) == SERVE


def test_shot_placement_off_hides_endings_landing_and_breakdown() -> None:
    assert _hidden({"serve_tracking": True, "shot_placement": False}) == ENDING | {
        "landing",
        "error_breakdown",
    }


def test_other_types_have_no_legacy_dashboard() -> None:
    for type_key in ("frames", "generic"):
        assert registry.get(type_key).hidden_dashboard_metrics({}) == frozenset()
