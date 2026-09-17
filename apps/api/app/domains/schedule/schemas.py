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
    # 026-match-record-friend-invite: RosterEntry.member_id, projected only
    # by the two already-authenticated match-record builders that need it
    # (_build_match_record_summaries(), _build_member_match_record_summaries())
    # — MUST stay None everywhere else, including every schedule/live-status
    # builder (build_schedule_snapshot()'s current_match/next_up,
    # _match_participants_payload()/court_live_state(), build_round_matches_list()):
    # the "加好友" entry point for live/roster contexts lives on
    # RosterScheduleStatus.member_id instead, per research.md #1's redesign.
    member_id: str | None = None


class NextUpPreview(BaseModel):
    match_id: str
    participants: list[ParticipantSummary]


class ServeStationInfo(BaseModel):
    """029-serve-rotation-display: who's serving and where everyone stands
    right now — mirrors 030-score-serve-record's `ScoreServeRecord` column
    shape 1:1 (this is the live/current equivalent of that per-point
    snapshot), computed by the shared `_compute_station()` (service.py)."""

    server_roster_entry_id: str
    server_team: Team
    team_a_right_roster_entry_id: str | None
    team_a_left_roster_entry_id: str | None
    team_b_right_roster_entry_id: str | None
    team_b_left_roster_entry_id: str | None


class MatchSummary(BaseModel):
    match_id: str
    status: str
    participants: list[ParticipantSummary]
    score_a: int
    score_b: int
    # feature/control-panel-scoreboard-style: lets the admin page's court-
    # control block show the same serve-rotation stations as the scoreboard/
    # public control panel — None when the match has no serve state yet
    # (research.md Decision 4, 029-serve-rotation-display — a match created
    # before 030-score-serve-record's migration).
    serve: ServeStationInfo | None = None


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
    # 026-match-record-friend-invite: the roster list (both the member-facing
    # and admin-facing schedule pages, same builder) is the "加好友" entry
    # point's canonical home — None for Guests (mirrors is_guest).
    member_id: str | None = None


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


# 032-cancel-score: `side` MUST be the team `undo_match_completion()`
# (service.py) finds as `match.winner_team` — a plain `-1` (ScoreRequest
# above) can't target an already-`completed` match at all.
class UndoMatchCompletionRequest(BaseModel):
    side: Team


# 032-score-then-record: attaches shot-placement detail to a `+1` point
# that's already been applied via a plain ScoreRequest above — the score
# itself is never blocked on the scorer filling this in (see
# attach_shot_placement() in service.py). `score_event_id` pins this to the
# exact point being annotated; `roster_entry_id`'s team is server-validated
# against that ScoreEvent's own `side` (it's no longer inferred from the
# player, since which side scored was already decided).
class RecordShotPlacementRequest(BaseModel):
    score_event_id: str
    # 032-optional-shot-placement-detail: every field below is independently
    # optional — the scorer can confirm with only whatever they actually
    # picked (see attach_shot_placement()) rather than being forced to fill
    # in all of them before submitting anything.
    roster_entry_id: str | None = None
    # The opposing-team player at fault for the rally ending —
    # attach_shot_placement() enforces it's on the other team from
    # roster_entry_id (and, for an in-bounds landing, that the credited side
    # matches which half of the court it landed in).
    losing_roster_entry_id: str | None = None
    # data-model.md: [-0.3, 1.3] is wider than the [0, 1] court itself (FR-010
    # allows a genuinely out-of-bounds landing) but still rejects nonsense
    # input. Pydantic enforces this at the request boundary;
    # attach_shot_placement() re-checks it too so the same
    # INVALID_LANDING_COORDINATES error_code is reachable when that function
    # is called directly (unit tests, defense in depth per Constitution X).
    # Both null or both set — attach_shot_placement() rejects one without
    # the other.
    landing_x: float | None = Field(default=None, ge=-0.3, le=1.3)
    landing_y: float | None = Field(default=None, ge=-0.3, le=1.3)


class ShotPlacementAttachResponse(BaseModel):
    recorded: bool = True


class ScoreMutationResult(BaseModel):
    applied: bool
    match_id: str
    status: str
    score_a: int
    score_b: int
    winner_team: Team | None
    # 032-score-then-record: the ScoreEvent this mutation created — `None`
    # when `applied` is false, or for a mutation that isn't a score change
    # (e.g. end_match_early()). A `+1`'s caller uses this to attach a
    # ShotPlacementRecord afterward (POST .../shot-placement) without
    # blocking the score itself on that follow-up UI.
    score_event_id: str | None = None
    # feature/control-panel-scoreboard-style: the acting client's own +1/-1
    # request previously only got score_a/score_b back — it had to wait for
    # its own match.scoreUpdated realtime echo to learn the new serve
    # rotation, which meant the station display went stale (or never
    # updated at all, if that echo didn't reach it) right after the very
    # button press that changed it. Riding the same already-computed
    # station on this direct response removes that dependency. `None` when
    # `applied` is false, when the match just ended (no more serve state to
    # show), or for a mutation with no serve concept (end_match_early()).
    serve: ServeStationInfo | None = None


class MatchLiveDetail(BaseModel):
    match_id: str
    status: str
    score_a: int
    score_b: int
    participants: list[ParticipantSummary]
    # None when the match has no serve state yet (research.md Decision 4 —
    # a match created before 030-score-serve-record's migration).
    serve: ServeStationInfo | None = None
    # 031-shot-placement-scoring: the match's OWN snapshot (matches.detailed_
    # scoring_enabled), not a live read of the group's current setting — see
    # contracts/score-detailed-api.md. Tells the frontend which scoring UI
    # (plain +1/-1 vs. tap-the-court) to render for this specific match.
    detailed_scoring_enabled: bool = False


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
    # 018-plan-then-start follow-up: the group's admin-controlled opt-in for
    # letting THIS (scoreboard) link also score — always the group's actual
    # setting regardless of `link_type`, so a `control_panel` link (already
    # always allowed to score) doesn't need special-casing on the frontend.
    scoreboard_scoring_enabled: bool
    round_number: int
    current_match: MatchLiveDetail | None
    waiting_reason: WaitingReason | None
    next_up: NextUpPreview | None
