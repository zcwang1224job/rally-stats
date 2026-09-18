"""Pydantic request/response schemas for the group domain, per
specs/001-create-manage-group/contracts/groups-api.md."""

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.schedule.schemas import EndingType, ParticipantSummary

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
    name: str | None = None
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
    def name_blank_normalizes_to_none(cls, v: str | None) -> str | None:
        """021-group-creation-defaults (FR-001): omitted, `null`, or
        whitespace-only `name` all normalize to `None` — `create_group()`
        substitutes the default "{建立者暱稱}的羽球團" in that case
        (research.md #1). A non-blank value still enforces the existing
        1-30 char limit."""
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            return None
        if len(stripped) > 30:
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
    # 013-group-invite-friends: True only for a group created by a logged-in
    # Member (Group.created_by_member_id is not None) — gates whether the
    # admin page's "邀請好友" section is offered at all (FR-012). Not
    # sensitive (a boolean, never reveals which member).
    created_by_member: bool = False


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
    # 018-plan-then-start follow-up: admin-only, deliberately not part of
    # `GroupPublicResponse` (that schema also backs the public join-flow
    # lookup — this setting has no reason to be visible there).
    scoreboard_scoring_enabled: bool
    # 031-shot-placement-scoring: same admin-only rationale as
    # scoreboard_scoring_enabled above.
    detailed_scoring_enabled: bool


class ScoreboardScoringRequest(BaseModel):
    enabled: bool


class ScoreboardScoringResponse(BaseModel):
    scoreboard_scoring_enabled: bool


class DetailedScoringRequest(BaseModel):
    enabled: bool


class DetailedScoringResponse(BaseModel):
    detailed_scoring_enabled: bool


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


class AddGuestRequest(BaseModel):
    """015-manual-add-guest: deliberately no format validator on `nickname`
    (unlike `JoinGroupRequest`) — the empty/too-long check must happen
    inside `join_group()` itself so it raises `NICKNAME_REQUIRED_FOR_GUEST`
    (a proper `ApiError` the frontend can render), not a generic FastAPI
    422 the error interceptor can't map to an i18n key."""

    nickname: str


class GuestSessionResponse(BaseModel):
    roster_entry_id: str
    group_id: str
    nickname: str


# --- 028-guest-stats-binding: 訪客即時戰況頁面建立帳號並綁定戰績 ---


class BindingStatusResponse(BaseModel):
    """contracts/guest-binding-api.md `GET /groups/guest-token/{token}/
    binding-status` — deliberately does not require `RosterEntry`/`Group`
    to be active (research.md #1), unlike `GuestSessionResponse`'s
    `resolve_guest_session()`."""

    already_bound: bool
    roster_entry_id: str
    group_id: str
    group_name: str
    nickname: str
    group_status: Literal["active", "disbanded"]
    roster_status: Literal["active", "left", "kicked"]


class BindRequest(BaseModel):
    """contracts/guest-binding-api.md `POST /groups/guest-token/{token}/
    bind`. Deliberately flat rather than a Pydantic discriminated union —
    the "already logged in" path's body is `{}` (no `mode` field at all),
    which a strict discriminator can't represent. `mode` is `None` for that
    path; the router/service validate the mode-specific fields are present
    when `mode` is `"register"`/`"login"` and raise `INVALID_REQUEST`
    otherwise (research.md #2)."""

    mode: Literal["register", "login"] | None = None
    email: str | None = None
    password: str | None = None
    turnstile_token: str | None = None


class BindResponse(BaseModel):
    bound: bool
    group_id: str
    access_token: str | None = None
    refresh_token: str | None = None


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
    rank: int
    """018-group-leaderboard FR-001/FR-006: standard competition ranking
    ("1224") over `total_wins`, ties broken by `RosterEntry.joined_at`
    (earlier joiner sorts first within a tie) — computed once server-side
    in `build_group_standings`, never re-derived client-side (constitution
    X)."""
    total_wins: int
    total_losses: int


class GroupStandingsResponse(BaseModel):
    current_round_number: int
    rounds: list[int]
    members: list[MemberStandingRow]


class FinalStandingRow(BaseModel):
    """019-group-final-standings: "我的團" 歷史頁面的最終團隊排名列——與
    `MemberStandingRow`（即時戰績頁）的差異：涵蓋該團所有曾參與者（不限
    現役，含訪客），同一位會員的多筆歷史 `RosterEntry`（先退出後又重新
    加入）合併為一列，且不含逐輪矩陣（只有累計總數）。"""

    roster_entry_id: str
    nickname: str
    current_status: Literal["active", "left", "kicked"]
    is_self: bool
    """research.md #4: 是否為目前呼叫端點的會員自己——伺服器端依
    `member_id` 比對算好，前端 MUST 直接渲染，MUST NOT 自行比對任何 ID
    （憲章原則 X）。"""
    rank: int
    total_matches: int
    total_wins: int
    total_losses: int


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


class OpponentRecord(BaseModel):
    """One row of a "球員戰績排行" table — a distinct player's win/loss
    tally, aggregated over whatever matches/filters are active. Despite
    the name (its original use was the cross-group "對戰對象戰績排行"),
    this is a generic per-player win/loss shape — `GroupMatchRecordsResponse
    .player_records` below reuses it for "every player who appeared in the
    (filtered) matches," not specifically "opponents of someone.\""""

    nickname: str
    wins: int
    losses: int
    matches: int
    win_rate: float


class GroupMatchRecordsResponse(BaseModel):
    matches: list[MatchRecordSummary]
    page: int
    total_pages: int
    # group-history filters follow-up (pie-chart addition): every player
    # who appeared in the FULL filtered result set (not just this page),
    # each with their win/loss tally — mirrors `MemberMatchRecordsResponse
    # .opponent_records`'s "aggregate over the whole filtered set, not the
    # page" rule (build_group_match_records()'s docstring/research.md #8).
    player_records: list[OpponentRecord] = []


class MemberMatchRecordSummary(MatchRecordSummary):
    group_id: str
    group_name: str
    won: bool


# 032-match-record-scoring-stats: a per-point snapshot of "who scored, who
# was at fault, where it landed" for a single +1 ScoreEvent — read-only
# projection of an existing ShotPlacementRecord row (031/032-shot-placement-
# scoring), never written by this feature. Every field independently
# optional since a ShotPlacementRecord's own fields are each independently
# optional (the scorer may confirm with only some of them picked).
class ShotPlacementSummary(BaseModel):
    scoring_roster_entry_id: str | None = None
    scoring_nickname: str | None = None
    losing_roster_entry_id: str | None = None
    losing_nickname: str | None = None
    landing_x: float | None = None
    landing_y: float | None = None
    # 035-point-ending-type: how the rally ended (the five values of
    # schedule.schemas.EndingType); None = not recorded, including every
    # point scored before 035. Returned whatever record_completeness is —
    # it's a per-point fact, not a derivation.
    ending_type: EndingType | None = None


class ScoreEventSummary(BaseModel):
    side: Literal["A", "B"]
    delta: Literal[1, -1]
    score_a: int
    score_b: int
    elapsed_seconds: int
    # research.md Decision 2: None for a -1 event, a +1 event with no
    # ShotPlacementRecord at all, or one whose five fields are all NULL
    # (confirmed with nothing picked) — those three cases must render
    # identically (no badge, not expandable), so build_match_record_detail()
    # collapses them to the same None here rather than letting the frontend
    # tell them apart.
    detail: ShotPlacementSummary | None = None


# 032-match-record-scoring-stats: one match participant's aggregate across
# every ShotPlacementRecord row in this match — independently counts
# `roster_entry_id` occurrences (scored_count) and `losing_roster_entry_id`
# occurrences (fault_count), per research.md Decision 3 (a row may set only
# one of the two fields).
class PlayerScoringStat(BaseModel):
    roster_entry_id: str
    nickname: str
    team: Literal["A", "B"]
    scored_count: int
    fault_count: int


class ServeCounts(BaseModel):
    """033-match-record-derived-stats: counts only — the frontend derives
    the percentage and renders "—" for a zero total, so no divide-by-zero
    representation has to be invented here."""

    serve_points_won: int
    serve_points_total: int
    receive_points_won: int
    receive_points_total: int


class TeamServeStat(ServeCounts):
    team: Literal["A", "B"]


class PlayerServeStat(ServeCounts):
    roster_entry_id: str
    nickname: str
    team: Literal["A", "B"]


class ServeStats(BaseModel):
    teams: list[TeamServeStat]  # always [A, B]
    # Doubles: every participant, all-zero ones included. Singles: [] — the
    # player-level numbers would just repeat the team-level ones.
    players: list[PlayerServeStat]
    # Points whose server couldn't be determined — always >= 1, since the
    # pre-match serve draw is never persisted (research.md Decision 4).
    excluded_points: int


class ScoringRun(BaseModel):
    team: Literal["A", "B"]
    length: int
    # Score right BEFORE the run's first point / right AFTER its last; all
    # four None when length == 0.
    start_score_a: int | None = None
    start_score_b: int | None = None
    end_score_a: int | None = None
    end_score_b: int | None = None


class MaxLead(BaseModel):
    team: Literal["A", "B"]
    margin: int
    # Score the first time this margin was reached; None when margin == 0.
    score_a: int | None = None
    score_b: int | None = None


class LeadChange(BaseModel):
    new_leader: Literal["A", "B"]
    score_a: int
    score_b: int


class MomentumStats(BaseModel):
    longest_runs: list[ScoringRun]  # always [A, B]
    max_leads: list[MaxLead]  # always [A, B]
    lead_changes: list[LeadChange]


class LongestPoint(BaseModel):
    seconds: float
    score_a: int
    score_b: int


class TempoStats(BaseModel):
    average_seconds: float
    counted_points: int
    longest: LongestPoint


class LandingPoint(BaseModel):
    x: float
    y: float


class PlayerLandingDistribution(BaseModel):
    roster_entry_id: str
    nickname: str
    team: Literal["A", "B"]
    scored: list[LandingPoint]
    # Every point credited to this player, plotted or not — the denominator
    # next to `scored`. Same meaning for lost/lost_total.
    scored_total: int
    lost: list[LandingPoint]
    lost_total: int


class ClutchPhaseTotals(BaseModel):
    won: int
    total: int


class ClutchPhaseCounts(ClutchPhaseTotals):
    team: Literal["A", "B"]


class ClutchMatchPoints(BaseModel):
    team: Literal["A", "B"]
    held: int
    # Which of this team's match points (1-based) ended the match; None for
    # the loser.
    converted_on: int | None
    saved: int


class ClutchStateCounts(BaseModel):
    """Grouped by the score BEFORE each point. A `total` of 0 means "never
    in that state" — shown as "0/0 —", never as 0% (FR-015)."""

    team: Literal["A", "B"]
    leading: ClutchPhaseTotals
    tied: ClutchPhaseTotals
    trailing: ClutchPhaseTotals


class ClutchComeback(BaseModel):
    """The winner's deepest deficit — by construction the same number as the
    loser's entry in `momentum_stats.max_leads` (FR-014)."""

    winner: Literal["A", "B"]
    max_deficit: int
    score_a: int
    score_b: int


class ClutchStats(BaseModel):
    endgame_from: int | None  # None: target too low for the phase to apply
    endgame: list[ClutchPhaseCounts] | None  # [A, B], None iff endgame_from is
    deuce: list[ClutchPhaseCounts] | None  # [A, B]; None: never reached deuce
    match_points: list[ClutchMatchPoints]  # always [A, B]
    by_state: list[ClutchStateCounts]  # always [A, B]
    comeback: ClutchComeback | None  # None: the winner never trailed


class ErrorsByType(BaseModel):
    """035-point-ending-type: one count per error kind — the four
    non-winner values of EndingType, always all four keys."""

    out: int
    net: int
    serve_fault: int
    other_error: int


class TeamEndingStat(BaseModel):
    team: Literal["A", "B"]
    winners: int
    # Errors THIS team committed (= points the other team got by error).
    errors: int
    errors_by_type: ErrorsByType


class PlayerEndingStat(BaseModel):
    """Points scored = winners + opponent_errors + scored_unrecorded; points
    lost = beaten_by_winners + own_errors + lost_unrecorded — each triple
    adds up to the same player's `player_stats` scored_count/fault_count
    (FR-015), so the frontend can show the split under the existing
    totals without a second source of truth."""

    roster_entry_id: str
    nickname: str
    team: Literal["A", "B"]
    winners: int
    opponent_errors: int
    scored_unrecorded: int
    beaten_by_winners: int
    own_errors: int
    lost_unrecorded: int


class EndingStats(BaseModel):
    # How much of the match the numbers cover: effective points with a
    # recorded ending, out of all effective points (FR-016).
    recorded_points: int
    total_points: int
    teams: list[TeamEndingStat]  # always [A, B]
    players: list[PlayerEndingStat]  # every participant, team_a + team_b


class MatchRecordDetailResponse(MatchRecordSummary):
    record_completeness: Literal["complete", "partial", "none"]
    events: list[ScoreEventSummary]
    # research.md Decision 4: `[]` is the single signal for "no player was
    # ever recorded in this match" (FR-008's empty-state prompt); whenever
    # non-empty, it always lists EVERY participant in team_a + team_b, zero
    # counts included (FR-009) — there is no third state, so no separate
    # boolean flag is needed alongside this list.
    player_stats: list[PlayerScoringStat] = []
    # 033-match-record-derived-stats: four independent read-only derivations
    # (group/match_stats.py). None / [] IS the "no data" signal the frontend
    # turns into a notice — never an all-zero structure. All four stay at
    # these defaults unless record_completeness == "complete".
    serve_stats: ServeStats | None = None
    momentum_stats: MomentumStats | None = None
    tempo_stats: TempoStats | None = None
    landing_distribution: list[PlayerLandingDistribution] = []
    # 034-clutch-points-player-dashboard: same "complete record only" rule
    # as the four above.
    clutch_stats: ClutchStats | None = None
    # 035-point-ending-type: same "complete record only" rule again, and
    # None as well when not one point of the match recorded an ending
    # (every pre-035 match). 032's `player_stats` above is unchanged —
    # this is the split UNDER those totals, not a replacement.
    ending_stats: EndingStats | None = None


class RoundWinRatePoint(BaseModel):
    """One point on the "各輪勝率趨勢" line chart — matches sharing the same
    `round_number` are bucketed together across every group the member has
    played in, since a member's own round numbering only resets per group."""

    round_number: int
    wins: int
    losses: int
    win_rate: float


class MatchupRecord(OpponentRecord):
    """036-match-insights-benchmarks US2: a partner or an opponent of ONE
    member, keyed by who the player is (`m:<member_id>` / `r:<roster_entry_id>`)
    rather than by nickname. A superset of `OpponentRecord`, whose five fields
    keep their names and meaning; `nickname` is the player's name in their
    latest match in range. `OpponentRecord` itself — and the group page's
    `player_records` that uses it — is untouched."""

    player_key: str
    member_id: str | None
    avg_margin: float  # my score minus theirs, per match; one decimal
    low_sample: bool  # fewer than 3 matches: listed, flagged, never singled out


class MatchupHighlights(BaseModel):
    """Player keys; None when nobody has played enough (FR-024)."""

    most_played_partner: str | None = None
    best_partner: str | None = None
    most_faced_opponent: str | None = None
    toughest_opponent: str | None = None


class MemberMatchRecordsResponse(BaseModel):
    matches: list[MemberMatchRecordSummary]
    total_matches: int
    total_wins: int
    total_losses: int
    win_rate: float
    round_win_rates: list[RoundWinRatePoint]
    opponent_records: list[MatchupRecord]
    # 036: all three aggregate the whole filtered set, like `opponent_records`.
    partner_records: list[MatchupRecord] = []
    matchup_highlights: MatchupHighlights = MatchupHighlights()
    doubles_matches: int = 0  # 0 → "singles has no partner" instead of an empty table
    page: int
    total_pages: int


class LeaveGroupRequest(BaseModel):
    guest_session_token: str | None = None


class LeaveGroupResponse(BaseModel):
    roster_entry_id: str
    status: Literal["left"]
