"""043 common match parameters (spec FR-008/FR-012, data-model §2).

Every sport type shares these; type-specific parameters (`type_params`) are
validated by the sport type's plugin instead.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SportParamsError(ValueError):
    """A common parameter breaks a rule; `field` names it for the 422 body."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


class CommonParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    end_mode: Literal["target", "manual"] = "target"
    target_score: int
    win_by: int = 2
    cap_score: int | None = None
    allow_draw: bool = False
    score_steps: list[int] = [1]


def validate_common_params(params: CommonParams) -> None:
    """Raise SportParamsError on the first broken rule."""
    if params.win_by < 1:
        raise SportParamsError("win_by", "win_by must be at least 1")
    steps = params.score_steps
    if not steps:
        raise SportParamsError("score_steps", "score_steps must not be empty")
    if any(step <= 0 for step in steps):
        raise SportParamsError("score_steps", "score_steps must be positive")
    if steps != sorted(set(steps)):
        raise SportParamsError("score_steps", "score_steps must be strictly increasing")
    if params.end_mode == "target":
        if params.allow_draw:
            raise SportParamsError("allow_draw", "draws only exist in manual end mode")
        if params.target_score < params.win_by:
            raise SportParamsError("target_score", "target_score must be at least win_by")
        if params.cap_score is not None and params.cap_score < params.target_score:
            raise SportParamsError("cap_score", "cap_score must be at least target_score")
    elif params.target_score < 1:
        raise SportParamsError("target_score", "target_score must be at least 1")
