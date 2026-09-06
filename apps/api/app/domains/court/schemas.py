"""Pydantic request/response schemas for the court domain, per
specs/002-court-management/contracts/courts-api.md."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

LinkType = Literal["scoreboard", "control_panel"]


def _validate_name(v: str) -> str:
    stripped = v.strip()
    if not stripped or len(stripped) > 20:
        raise ValueError("name must be 1-20 chars after trimming")
    return stripped


class CreateCourtRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        return _validate_name(v)


class RenameCourtRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        return _validate_name(v)


class RegenerateLinkRequest(BaseModel):
    expected_version: int


class CourtResponse(BaseModel):
    court_id: str
    name: str
    scoreboard_token: str
    control_panel_token: str
    scoreboard_link_version: int
    control_panel_link_version: int
    created_at: datetime


class CourtListResponse(BaseModel):
    courts: list[CourtResponse]
    active_court_count: int


class DeleteCourtResponse(BaseModel):
    court_id: str
    deleted: bool
    had_active_match: bool


class RegenerateScoreboardLinkResponse(BaseModel):
    scoreboard_token: str
    scoreboard_link_version: int


class RegenerateControlPanelLinkResponse(BaseModel):
    control_panel_token: str
    control_panel_link_version: int


class CourtByTokenResponse(BaseModel):
    court_id: str
    group_id: str
    name: str
    link_type: LinkType
    link_version: int
    deleted: bool
    group_disbanded: bool
