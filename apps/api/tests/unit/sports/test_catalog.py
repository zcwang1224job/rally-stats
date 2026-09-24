"""043 T017: the built-in activity catalogue."""

from app.sports.catalog import (
    BUILTIN_SPORTS,
    DEFAULT_SPORT_KEY,
    get_builtin,
    summary_for,
)

EXPECTED_ORDER = [
    "badminton",
    "table_tennis",
    "pickleball",
    "tennis_tiebreak",
    "billiards",
    "darts",
    "board_game",
    "esports",
    "other",
]


def test_nine_builtins_in_catalogue_order_with_other_last() -> None:
    assert [sport.sport_key for sport in BUILTIN_SPORTS] == EXPECTED_ORDER
    assert DEFAULT_SPORT_KEY == "badminton"


def test_each_builtin_belongs_to_one_of_this_releases_types() -> None:
    by_type = {sport.sport_key: sport.type_key for sport in BUILTIN_SPORTS}
    assert by_type == {
        "badminton": "net_rally",
        "table_tennis": "net_rally",
        "pickleball": "net_rally",
        "tennis_tiebreak": "net_rally",
        "billiards": "frames",
        "darts": "frames",
        "board_game": "frames",
        "esports": "frames",
        "other": "generic",
    }


def test_defaults_satisfy_the_common_parameter_rules() -> None:
    for sport in BUILTIN_SPORTS:
        d = sport.defaults
        assert d.team_size in sport.team_size_options, sport.sport_key
        assert set(sport.team_size_options) <= {1, 2}, sport.sport_key
        assert d.win_by >= 1
        assert d.target_score >= d.win_by, sport.sport_key
        assert d.cap_score is None or d.cap_score >= d.target_score
        assert d.score_steps and all(step > 0 for step in d.score_steps)
        assert list(d.score_steps) == sorted(set(d.score_steps))
        assert d.allow_draw is (d.end_mode == "manual")


def test_badminton_defaults_are_exactly_the_pre_043_group_defaults() -> None:
    badminton = get_builtin("badminton")
    assert badminton is not None
    d = badminton.defaults
    assert (d.target_score, d.win_by, d.cap_score, d.scoring_mode) == (21, 2, 30, "21pt")
    assert d.type_params == {"modules": {"serve_tracking": True, "shot_placement": True}}


def test_summary_of_a_builtin_uses_its_name_key() -> None:
    summary = summary_for(sport_key="billiards", type_key="frames", sport_name=None)
    assert summary.name_key == "sports.billiards"
    assert summary.name is None
    assert summary.nouns.score == "frame"


def test_summary_of_other_and_custom_uses_the_users_name() -> None:
    other = summary_for(sport_key="other", type_key="generic", sport_name="趣味賽")
    assert (other.name, other.name_key) == ("趣味賽", None)
    custom = summary_for(sport_key="custom", type_key="frames", sport_name="躲避球對抗")
    assert (custom.sport_key, custom.type_key, custom.name) == ("custom", "frames", "躲避球對抗")
