"""Pydantic request/response schemas for the schedule domain, per
specs/003-schedule-rotation/contracts/schedule-api.md."""

from typing import Literal

from pydantic import BaseModel, Field

Team = Literal["A", "B"]
WaitingReason = Literal["manual_assignment", "no_queued_match"]
# 018-plan-then-start: derived (not stored) round state for the algorithmic
# mechanisms' "規劃賽程安排" -> "Next Round" two-step admin flow — always
# None for scheduling_mechanism == "manual", which has no plan/start split.
RoundPhase = Literal["awaiting_plan", "awaiting_start", "in_progress"]


class ParticipantSummary(BaseModel):
    roster_entry_id: str
    nickname: str
    team: Team


class NextUpPreview(BaseModel):
    match_id: str
    participants: list[ParticipantSummary]


class MatchSummary(BaseModel):
    match_id: str
    status: str
    participants: list[ParticipantSummary]
    score_a: int
    score_b: int


class CourtScheduleStatus(BaseModel):
    court_id: str
    name: str
    current_match: MatchSummary | None
    waiting_reason: WaitingReason | None
    next_up: NextUpPreview | None


class RosterScheduleStatus(BaseModel):
    roster_entry_id: str
    nickname: str
    status: str
    wait_count: int | None
    currently_playing: bool
    is_creator: bool
    # Whether this entry has no Member account (member_id IS NULL) — the
    # admin page uses this to decide whether "regenerate guest link" makes
    # sense for the row (a Member entry has no guest_session_token concept).
    is_guest: bool


class ScheduleResponse(BaseModel):
    current_round_number: int
    scheduling_mechanism: str
    auto_next_round: bool
    round_phase: RoundPhase | None
    courts: list[CourtScheduleStatus]
    roster: list[RosterScheduleStatus]


class RoundMatchSummary(BaseModel):
    """011-round-robin-scheduling: one row of the admin-facing "本輪賽程清單"
    — unlike `CourtScheduleStatus.current_match`, this is shown regardless
    of status (queued/in_progress/completed/abandoned), since the whole
    point is to let the admin see the full pre-generated schedule, not just
    what's currently on a court."""

    match_id: str
    status: str
    court_name: str | None
    participants: list[ParticipantSummary]
    score_a: int
    score_b: int
    winner_team: Team | None


class RoundMatchesResponse(BaseModel):
    round_number: int
    matches: list[RoundMatchSummary]


class AutoNextRoundRequest(BaseModel):
    enabled: bool


class AutoNextRoundResponse(BaseModel):
    auto_next_round: bool


class RosterSummary(BaseModel):
    roster_entry_id: str
    nickname: str


class PartnershipSummary(BaseModel):
    partnership_id: str
    player_a: RosterSummary
    player_b: RosterSummary


class PartnershipsResponse(BaseModel):
    partnerships: list[PartnershipSummary]
    unpaired: list[RosterSummary]


class PartnershipReassignRequest(BaseModel):
    player_a_id: str
    player_b_id: str


# --- 017-fixed-partner-autofill ---


class TemporaryPairing(BaseModel):
    """暫時隨機配對 — 前端草稿狀態 + API 傳輸格式，刻意不含 `partnership_id`
    （data-model.md）：它從來不是一筆寫入資料庫、有主鍵的資料列。"""

    player_a: RosterSummary
    player_b: RosterSummary


class TemporaryPairingsResponse(BaseModel):
    pairings: list[TemporaryPairing]


class TemporaryPairingInput(BaseModel):
    player_a_id: str
    player_b_id: str


class NextRoundRequest(BaseModel):
    temporary_pairings: list[TemporaryPairingInput] = Field(default_factory=list)


class SwapPlannedMatchPlayersRequest(BaseModel):
    """018-plan-then-start: swaps two players' match assignments while the
    current round is `awaiting_start` (planned, not yet pulled onto any
    court) — e.g. the admin wants these two to trade opponents/partners
    before play begins."""

    match_id_1: str
    roster_entry_id_1: str
    match_id_2: str
    roster_entry_id_2: str


class ReorderPlannedMatchesRequest(BaseModel):
    """018-plan-then-start: `match_ids` in the admin's desired new call-up
    order — MUST be a permutation of the current round's existing match ids
    (drag-reordering, not adding/removing matches)."""

    match_ids: list[str]


class ChangeMatchPlayerRequest(BaseModel):
    """018-plan-then-start: directly replaces `old_roster_entry_id` in
    `match_id` with `new_roster_entry_id` — a specific substitute, as
    opposed to `SwapPlannedMatchPlayersRequest`'s "trade with another
    match"."""

    match_id: str
    old_roster_entry_id: str
    new_roster_entry_id: str


class ManualAssignRequest(BaseModel):
    participant_ids: list[str]
    teams: dict[str, Team]


class MatchDetailResponse(BaseModel):
    match_id: str
    status: str
    participants: list[ParticipantSummary]
    target_score: int
    deuce_threshold: int
    cap_score: int


class KickMemberResponse(BaseModel):
    roster_entry_id: str
    status: str


class RegenerateGuestLinkResponse(BaseModel):
    roster_entry_id: str
    guest_session_token: str


# --- 007-live-scoreboard, per data-model.md ---


class ScoreRequest(BaseModel):
    side: Team
    delta: Literal[1, -1]


class ScoreMutationResult(BaseModel):
    applied: bool
    match_id: str
    status: str
    score_a: int
    score_b: int
    winner_team: Team | None


class MatchLiveDetail(BaseModel):
    match_id: str
    status: str
    score_a: int
    score_b: int
    participants: list[ParticipantSummary]


class CourtLiveState(BaseModel):
    court_id: str
    round_number: int
    current_match: MatchLiveDetail | None
    waiting_reason: WaitingReason | None
    next_up: NextUpPreview | None


class AllCourtsLiveState(BaseModel):
    group_id: str
    round_number: int
    courts: list[CourtLiveState]


class CourtStateResponse(BaseModel):
    """`GET /courts/by-token/{token}/state` — CourtByTokenResponse's link
    fields flattened alongside CourtLiveState's match fields (contracts/
    scoring-api.md), so the frontend needs only one bootstrap call."""

    court_id: str
    group_id: str
    name: str
    link_type: str
    link_version: int
    deleted: bool
    group_disbanded: bool
    round_number: int
    current_match: MatchLiveDetail | None
    waiting_reason: WaitingReason | None
    next_up: NextUpPreview | None
