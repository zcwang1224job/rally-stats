"""`type_params` of the frames sport type (spec 043 data-model §7, FR-018a)."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FramesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Keep an in-frame score point by point (+1/-1) as well as who won it.
    frame_scoring_enabled: bool = False
    # In-frame points that end a frame on their own; None = only the scorer
    # ends a frame. Ignored unless frame_scoring_enabled.
    frame_target: int | None = Field(default=None, ge=1)
    # The in-frame lead frame_target also needs.
    frame_win_by: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def check_target_against_lead(self) -> "FramesParams":
        if self.frame_target is not None and self.frame_target < self.frame_win_by:
            raise ValueError("frame_target must be at least frame_win_by")
        return self


def parse_params(raw: Mapping[str, Any]) -> FramesParams:
    return FramesParams.model_validate(dict(raw))
