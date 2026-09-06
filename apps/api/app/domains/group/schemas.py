"""Pydantic request/response schemas for the group domain, per
specs/001-create-manage-group/contracts/groups-api.md."""

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.schedule.schemas import ParticipantSummary

MatchMode = Literal["singles", "doubles"]
SchedulingMechanism = Literal["fair_rotation", "fixed_partner", "individual_mixed", "manual"]
ScoringMode = Literal["21pt", "15pt", "custom"]
PartnerSource = Literal["manual", "auto"]


class CustomScoring(BaseModel):
    target_score: int = Field(ge=1)
    deuce_threshold: int = Field(ge=1)
    cap_score: int = Field(ge=1)

    @model_validator(mode="after")
    def check_consistency(self) -> "CustomScoring":
        if self.deuce_threshold > self.target_score:
            raise ValueError("deuce_threshold must not exceed target_score")
        if self.cap_score < self.deuce_threshold:
            raise ValueError("cap_score must be >= deuce_threshold")
        if self.cap_score < self.target_score:
            raise ValueError("cap_score must be >= target_score")
        return self


class CreateGroupRequest(BaseModel):
    name: str
    password: str | None = None
    max_members: int
    match_mode: MatchMode
    scheduling_mechanism: SchedulingMechanism
    scoring_mode: ScoringMode = "21pt"
    custom_scoring: CustomScoring | None = None
    activity_time_start: time | None = None
    activity_time_end: time | None = None
    creator_nickname: str | None = None
    turnstile_token: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped or len(stripped) > 30:
            raise ValueError("name must be 1-30 chars after trimming")
        return stripped

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not (1 <= len(v) <= 20):
            raise ValueError("password must be 1-20 chars")
        return v

    @field_validator("creator_nickname")
    @classmethod
    def nickname_length(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped or len(stripped) > 20:
            raise ValueError("creator_nickname must be 1-20 chars after trimming")
        return stripped

    @model_validator(mode="after")
    def check_activity_time_pair(self) -> "CreateGroupRequest":
        if (self.activity_time_start is None) != (self.activity_time_end is None):
            raise ValueError("activity_time_start and activity_time_end must be provided together")
        if (
            self.activity_time_start is not None
            and self.activity_time_end is not None
            and self.activity_time_start >= self.activity_time_end
        ):
            raise ValueError("activity_time_start must be before activity_time_end")
        return self

    @model_validator(mode="after")
    def check_max_members_min(self) -> "CreateGroupRequest":
        minimum = 2 if self.match_mode == "singles" else 4
        if self.max_members < minimum:
            raise ValueError(f"max_members must be >= {minimum} for {self.match_mode}")
        return self

    @model_validator(mode="after")
    def check_custom_scoring_present(self) -> "CreateGroupRequest":
        if self.scoring_mode == "custom" and self.custom_scoring is None:
            raise ValueError("custom_scoring is required when scoring_mode=custom")
        return self

    @model_validator(mode="after")
    def check_scheduling_mechanism_requires_doubles(self) -> "CreateGroupRequest":
        # spec 003 FR-042: fixed_partner/individual_mixed only make sense
        # with a partner, i.e. doubles.
        if self.scheduling_mechanism in ("fixed_partner", "individual_mixed") and (
            self.match_mode == "singles"
        ):
            raise ValueError(
                f"scheduling_mechanism={self.scheduling_mechanism} requires match_mode=doubles"
            )
        return self


class CreateGroupResponse(BaseModel):
    group_id: str
    group_number: int
    admin_pin: str
    admin_token: str
    current_member_count: int
    roster_entry_id: str
    guest_session_token: str | None = None


class GroupPublicResponse(BaseModel):
    group_id: str
    group_number: int
    name: str
    has_password: bool
    current_member_count: int
    max_members: int
    match_mode: MatchMode
    scheduling_mechanism: SchedulingMechanism
    partner_source: PartnerSource
    activity_time_start: time | None
    activity_time_end: time | None
    status: Literal["active", "disbanded"]
    # Only populated by GET /groups/{group_id} when a logged-in Member's
    # Bearer token is presented (None for Guests/unauthenticated callers) —
    # lets the join flow skip the password step entirely for a member who
    # already has an active roster entry in this group (FR-020a short-
    # circuit), same signal as GroupListItem.joined_by_me.
    already_joined: bool | None = None


class ReauthRequest(BaseModel):
    group_number: int
    admin_pin: str


class ReauthResponse(BaseModel):
    admin_token: str
    group_id: str


class EditGroupRequest(BaseModel):
    expected_version: int
    name: str | None = None
    password: str | None = None
    match_mode: MatchMode | None = None
    scheduling_mechanism: SchedulingMechanism | None = None
    partner_source: PartnerSource | None = None
    max_members: int | None = None
    activity_time_start: time | None = None
    activity_time_end: time | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped or len(stripped) > 30:
            raise ValueError("name must be 1-30 chars after trimming")
        return stripped

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not (1 <= len(v) <= 20):
            raise ValueError("password must be 1-20 chars")
        return v


class EditScoringSettingsRequest(BaseModel):
    expected_version: int
    scoring_mode: ScoringMode
    target_score: int | None = None
    deuce_threshold: int | None = None
    cap_score: int | None = None


class RegeneratePinResponse(BaseModel):
    admin_pin: str
    admin_token: str


class AdminGroupResponse(BaseModel):
    group: GroupPublicResponse
    password_plaintext: str | None
    read_only: bool
    base_settings_version: int
    admin_token_version: int
    join_link_token: str
    join_link_version: int
    all_courts_control_panel_token: str
    all_courts_link_version: int


class RegenerateLinkRequest(BaseModel):
    expected_version: int


class RegenerateJoinLinkResponse(BaseModel):
    join_link_token: str
    join_link_version: int


class RegenerateAllCourtsLinkResponse(BaseModel):
    all_courts_control_panel_token: str
    all_courts_link_version: int


class AllCourtsCourtSummary(BaseModel):
    court_id: str
    name: str


class AllCourtsBootstrapResponse(BaseModel):
    group_id: str
    all_courts_link_version: int
    group_disbanded: bool
    courts: list[AllCourtsCourtSummary]


class GroupListItem(BaseModel):
    group_id: str
    group_number: int
    name: str
    has_password: bool
    current_member_count: int
    max_members: int
    match_mode: MatchMode
    scheduling_mechanism: SchedulingMechanism
    activity_time_start: time | None
    activity_time_end: time | None
    status: Literal["active", "disbanded"]
    court_names: list[str]
    creator_nickname: str
    joined_by_me: bool | None = None
    # True only when the logged-in Member is this group's creator (a
    # subset of joined_by_me — the creator is always auto-added to the
    # roster too) — lets "回到我的團" route the creator straight to the
    # admin page instead of the read-only member view.
    created_by_me: bool | None = None
    # True when the logged-in Member has an active RosterEntry in a
    # DIFFERENT group (never true alongside joined_by_me for the same
    # item — they're mutually exclusive by the one-active-group invariant).
    # Lets the browse list disable "加入" for every other group up front
    # instead of only failing after the Member picks one and confirms
    # (ALREADY_ACTIVE_IN_ANOTHER_GROUP would still reject it server-side
    # either way — this is a UI nicety, not the enforcement).
    member_active_elsewhere: bool | None = None


class GroupListResponse(BaseModel):
    groups: list[GroupListItem]
    page: int
    total_pages: int


class VerifyPasswordRequest(BaseModel):
    password: str


class VerifyPasswordResponse(BaseModel):
    correct: bool


class JoinLinkPreviewResponse(BaseModel):
    group_id: str
    group_number: int
    name: str
    has_password: bool
    current_member_count: int
    max_members: int
    match_mode: MatchMode
    scheduling_mechanism: SchedulingMechanism
    activity_time_start: time | None
    activity_time_end: time | None
    status: Literal["active", "disbanded"]
    court_names: list[str]
    creator_nickname: str
    already_joined: bool
    roster_entry_id: str | None = None


class JoinGroupRequest(BaseModel):
    password: str | None = None
    nickname: str | None = None

    @field_validator("nickname")
    @classmethod
    def nickname_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped or len(stripped) > 20:
            raise ValueError("nickname must be 1-20 chars after trimming")
        return stripped


class JoinGroupResponse(BaseModel):
    roster_entry_id: str
    nickname: str
    guest_session_token: str | None
    created_new: bool


class GuestSessionResponse(BaseModel):
    roster_entry_id: str
    group_id: str
    nickname: str


# --- 005-member-view: 團內成員視圖（戰績/對戰紀錄/退出組團）---


class RoundRecord(BaseModel):
    """011-round-robin-scheduling made this a per-round *tally*, not a
    single outcome: singles fair_rotation's full round-robin
    (_generate_singles_round_robin_matches) plays every other active
    member once *within the same round_number*, so a Member can rack up
    several wins/losses before the round changes — the original
    won/lost/did_not_play/left four-state enum silently dropped every
    match but the last one processed for that (member, round) pair.
    `left` still means what it did before (irreversible once left_at is at
    or before this round's start) and is mutually exclusive with ever
    accumulating wins/losses for that round; did_not_play is simply
    `wins == 0 and losses == 0 and not left`."""

    wins: int
    losses: int
    left: bool


class MemberStandingRow(BaseModel):
    roster_entry_id: str
    nickname: str
    current_status: Literal["active", "left", "kicked"]
    rounds: dict[int, RoundRecord]


class GroupStandingsResponse(BaseModel):
    current_round_number: int
    rounds: list[int]
    members: list[MemberStandingRow]


class MatchRecordSummary(BaseModel):
    match_id: str
    round_number: int
    team_a: list[ParticipantSummary]
    team_b: list[ParticipantSummary]
    score_a: int
    score_b: int
    winner_team: Literal["A", "B"]
    # Only completed matches ever reach this schema (_completed_matches_query
    # filters on status == "completed"), and a match can't reach "completed"
    # without having been pulled onto a court (started_at set) and finished
    # (ended_at set) — so both are always populated here in practice, even
    # though the column itself is nullable for queued/abandoned-before-start
    # matches elsewhere.
    started_at: datetime | None
    ended_at: datetime | None


class GroupMatchRecordsResponse(BaseModel):
    matches: list[MatchRecordSummary]
    page: int
    total_pages: int


class MemberMatchRecordSummary(MatchRecordSummary):
    group_id: str
    group_name: str


class MemberMatchRecordsResponse(BaseModel):
    matches: list[MemberMatchRecordSummary]
    total_matches: int
    total_wins: int
    total_losses: int
    win_rate: float
    page: int
    total_pages: int


class LeaveGroupRequest(BaseModel):
    guest_session_token: str | None = None


class LeaveGroupResponse(BaseModel):
    roster_entry_id: str
    status: Literal["left"]
