"""043 T011: Group's team_size ↔ match_mode sync and the common-parameter
invariants (research Decisions 6–7, data-model §2)."""

import pytest

from app.domains.group.models import Group
from app.domains.group.sport_params import CommonParams, SportParamsError, validate_common_params


def test_match_mode_doubles_implies_team_size_two() -> None:
    group = Group(match_mode="doubles")
    assert group.team_size == 2


def test_team_size_one_implies_singles() -> None:
    group = Group(team_size=1)
    assert group.match_mode == "singles"


def test_assigning_match_mode_later_keeps_team_size_in_step() -> None:
    group = Group(match_mode="singles")
    group.match_mode = "doubles"
    assert group.team_size == 2
    group.team_size = 1
    assert group.match_mode == "singles"


def test_contradicting_match_mode_and_team_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="contradicts"):
        Group(match_mode="doubles", team_size=1)


def test_badminton_defaults_on_a_bare_group() -> None:
    group = Group(match_mode="singles")
    # Python-side defaults are applied at flush; the model still carries the
    # badminton column defaults.
    columns = Group.__table__.columns
    assert columns["sport_key"].default.arg == "badminton"  # type: ignore[union-attr]
    assert columns["type_key"].default.arg == "net_rally"  # type: ignore[union-attr]
    assert group.team_size == 1


def _params(**overrides: object) -> CommonParams:
    base: dict[str, object] = {
        "end_mode": "target",
        "target_score": 21,
        "win_by": 2,
        "cap_score": 30,
        "allow_draw": False,
        "score_steps": [1],
    }
    base.update(overrides)
    return CommonParams.model_validate(base)


def test_valid_badminton_params_pass() -> None:
    validate_common_params(_params())


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"target_score": 1, "win_by": 2, "cap_score": None}, "target_score"),
        ({"cap_score": 20}, "cap_score"),
        ({"win_by": 0}, "win_by"),
        ({"score_steps": []}, "score_steps"),
        ({"score_steps": [2, 1]}, "score_steps"),
        ({"score_steps": [1, 1]}, "score_steps"),
        ({"score_steps": [0]}, "score_steps"),
        ({"allow_draw": True}, "allow_draw"),
    ],
)
def test_invalid_common_params_are_rejected(overrides: dict[str, object], field: str) -> None:
    with pytest.raises(SportParamsError) as excinfo:
        validate_common_params(_params(**overrides))
    assert excinfo.value.field == field


def test_manual_end_mode_ignores_target_and_cap_and_allows_draws() -> None:
    validate_common_params(
        _params(end_mode="manual", target_score=1, win_by=1, cap_score=None, allow_draw=True)
    )


def test_no_cap_is_valid() -> None:
    validate_common_params(_params(target_score=11, cap_score=None))


def test_a_one_point_match_with_a_cap_stays_valid() -> None:
    # Pre-043 custom scoring (target 1 / cap 1) ends on the cap.
    validate_common_params(_params(target_score=1, win_by=2, cap_score=1))
