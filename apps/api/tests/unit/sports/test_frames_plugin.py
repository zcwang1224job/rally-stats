"""043 T067: frames params, estimate and first-to-N (data-model §7). Event
handling runs against the DB in tests/contract/test_match_events_endpoint.py."""

import pytest
from pydantic import ValidationError

from app.sports import registry
from app.sports.scoring import match_wins
from app.sports.types import register_all
from app.sports.types.frames.events import FRAME_END, FRAME_POINT
from app.sports.types.frames.params import FramesParams


@pytest.fixture(autouse=True)
def _plugins() -> None:
    register_all()


def test_params_defaults_and_bounds() -> None:
    params = FramesParams.model_validate({})
    assert params.frame_scoring_enabled is False
    assert params.frame_target is None
    assert params.frame_win_by == 1
    assert FramesParams.model_validate({"frame_target": None}).frame_target is None
    with pytest.raises(ValidationError):
        FramesParams.model_validate({"frame_win_by": 0})
    with pytest.raises(ValidationError):
        FramesParams.model_validate({"frame_target": 1, "frame_win_by": 2})
    with pytest.raises(ValidationError):
        FramesParams.model_validate({"unknown": True})


def test_declares_both_event_kinds_and_no_direct_points() -> None:
    plugin = registry.get("frames")
    assert set(plugin.event_schemas()) == {FRAME_POINT, FRAME_END}
    assert plugin.direct_points is False
    assert set(plugin.tables()) == {"frames_frame_results", "frames_frame_points"}


def test_first_to_five_frames_uses_win_by_one() -> None:
    assert not match_wins(4, 4, target=5, win_by=1, cap=None)
    assert match_wins(5, 4, target=5, win_by=1, cap=None)
    assert match_wins(5, 0, target=5, win_by=1, cap=None)


def test_estimate_minutes() -> None:
    plugin = registry.get("frames")
    plain = plugin.estimate_minutes(end_mode="target", target_score=5, type_params={})
    assert plain == pytest.approx(4.0 * 7.5)
    scored = plugin.estimate_minutes(
        end_mode="target",
        target_score=2,
        type_params={"frame_scoring_enabled": True, "frame_target": 11},
    )
    assert scored == pytest.approx(5.5 * 3)
