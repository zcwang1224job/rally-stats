"""Pydantic request/response schemas for the member domain, per
specs/006-member-friends/contracts/auth-api.md and member-api.md."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.domains.group.schemas import (
    ErrorsByType,
    FinalStandingRow,
    MatchRecordSummary,
    OpponentRecord,
    RoundWinRatePoint,
)

VerificationStatus = str  # "unverified" | "verified"

_PASSWORD_MIN_LENGTH = 8
_PASSWORD_HAS_LETTER = re.compile(r"[A-Za-z]")
_PASSWORD_HAS_DIGIT = re.compile(r"\d")


def _check_password_strength(password: str) -> None:
    if (
        len(password) < _PASSWORD_MIN_LENGTH
        or not _PASSWORD_HAS_LETTER.search(password)
        or not _PASSWORD_HAS_DIGIT.search(password)
    ):
        raise ValueError("password too weak")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    confirm_password: str
    turnstile_token: str
    # 024-add-english-language FR-009: the registering browser's current
    # display language, used to seed `language_preference` instead of
    # always defaulting to `zh-TW`. Intentionally NOT validated against
    # `SUPPORTED_LANGUAGES` here — an unsupported/malformed value is
    # silently ignored by `service.register()` rather than blocking
    # account creation (research.md #5).
    language: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        _check_password_strength(v)
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("passwords do not match")
        return self


class RegisterResponse(BaseModel):
    member_id: str
    email: str
    user_number: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MemberPublicResponse(BaseModel):
    member_id: str
    # 027-google-line-oauth-login: nullable — a LINE-only account may not
    # have one (FR-004).
    email: str | None
    nickname: str | None
    user_number: str
    verification_status: VerificationStatus
    resend_verification_available_at: datetime | None
    """020-resend-verification-email: `None` means the member can trigger
    "重新寄送驗證信" right now (or the account is already verified —
    the frontend already distinguishes that via `verification_status`,
    so the two `None` cases never get confused); otherwise the timestamp
    at which the cooldown ends, computed server-side
    (`get_resend_verification_available_at()`, constitution X)."""
    language_preference: str
    allow_search: bool
    share_match_records_with_friends: bool
    allow_friend_invite_from_match_pages: bool
    # 027-google-line-oauth-login: which providers this member currently
    # has a `member_oauth_identities` binding for (US3, at most one entry
    # per provider — FR-006).
    linked_oauth_providers: list[Literal["google", "line"]]
    # Whether `password_hash` is set — lets the frontend decide whether
    # "current password" is required on the change-password/delete-account
    # forms (research.md #7) and whether the FR-013 reminder should show
    # (email is None AND has_password is False).
    has_password: bool


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    member: MemberPublicResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str


class VerifyEmailResponse(BaseModel):
    verified: bool


class ResendVerificationResponse(BaseModel):
    sent: bool
    available_at: datetime
    """020-resend-verification-email: cooldown end time for the *next*
    resend, even when this call was the member's first-ever manual resend
    (which always succeeds — research.md #5)."""


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    sent: bool


class ResetPasswordRequest(BaseModel):
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        _check_password_strength(v)
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("passwords do not match")
        return self


class ResetPasswordResponse(BaseModel):
    reset: bool


class SetNicknameRequest(BaseModel):
    nickname: str

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped or len(stripped) > 20:
            raise ValueError("nickname must be 1-20 characters")
        return stripped


class ChangePasswordRequest(BaseModel):
    # 027-google-line-oauth-login research.md #7: optional — a member whose
    # `password_hash` is still `None` (never set one) has nothing to
    # re-confirm; `service.change_password()` skips the check for them and
    # treats the call as "set my first password" rather than "change it".
    current_password: str | None = None
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        _check_password_strength(v)
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("passwords do not match")
        return self


class ChangePasswordResponse(BaseModel):
    changed: bool
    access_token: str
    refresh_token: str


class DeleteAccountRequest(BaseModel):
    """025-delete-account FR-002: password re-entry is the confirmation
    step, matching `ChangePasswordRequest`'s existing precedent.
    027-google-line-oauth-login research.md #7: optional — a password-less
    OAuth-only member has nothing to re-confirm; the authenticated session
    itself is the proof of identity for them."""

    current_password: str | None = None


class DeleteAccountResponse(BaseModel):
    deleted: bool


class OAuthStartResponse(BaseModel):
    """027-google-line-oauth-login contracts/oauth-login-api.md:
    GET /auth/oauth/{provider}/start."""

    authorize_url: str


class AddEmailRequest(BaseModel):
    """027-google-line-oauth-login contracts/account-recovery-api.md:
    POST /members/me/email — only for a member whose `email` is currently
    `None` (FR-013); "changing" an existing email is out of scope."""

    email: EmailStr


class AddEmailResponse(BaseModel):
    verification_email_sent: bool


class MyGroupSummary(BaseModel):
    group_id: str
    group_number: int
    name: str
    status: str
    created_at: datetime
    # NULL for a still-active group, and for a group disbanded before this
    # column existed (that disband time was never recorded).
    disbanded_at: datetime | None
    # 014-member-groups-history: whether this member created the group.
    is_creator: bool
    # This member's own most-recent RosterEntry status in this group
    # (active/left/kicked) — a member can rejoin the same group after
    # leaving, producing multiple historical rows; this reflects the
    # newest one.
    member_status: str


class MyGroupsResponse(BaseModel):
    groups: list[MyGroupSummary]


class MemberGroupStatsResponse(BaseModel):
    """This member's own performance within one group — always reflects
    their FULL history there (never narrowed by `MemberGroupHistoryResponse
    .matches`' own nickname filter, which searches the group's shared
    match list, not "my" games specifically)."""

    total_matches: int
    total_wins: int
    total_losses: int
    win_rate: float
    round_win_rates: list[RoundWinRatePoint]
    opponent_records: list[OpponentRecord]


class MemberGroupHistoryResponse(BaseModel):
    """014-member-groups-history follow-up: `matches` is the group's own
    shared history (every completed match, any participant — reuses
    `build_group_match_records()`, FR-004), filterable by any player's
    nickname; `my_stats` is this member's personal performance in the
    group (reuses `build_member_match_records(group_id=...)`, FR-005),
    always unfiltered by that same nickname search — the two sections
    answer different questions ("what happened in this team" vs. "how have
    I done"), so they deliberately don't share one filter.

    019-group-final-standings adds a third, equally independent section:
    `final_standings` — the group's whole final team ranking (reuses
    `build_group_final_standings()`), covering every ever-participant
    (active/left/kicked, member or guest), also unaffected by the
    `matches` nickname filter.

    Advanced-filters follow-up (pie-chart addition): `player_records` is
    every player who appeared anywhere in the FULL filtered `matches`
    result set (not just this page), each with a win/loss tally over that
    filtered set — reuses `build_group_match_records()`'s own
    `player_records`, so it moves with `matches`' filters exactly, never
    with `my_stats`/`final_standings`."""

    group_id: str
    group_name: str
    my_stats: MemberGroupStatsResponse
    final_standings: list[FinalStandingRow]
    matches: list[MatchRecordSummary]
    page: int
    total_pages: int
    player_records: list[OpponentRecord] = []


FriendshipStatus = str  # "none" | "pending_outgoing" | "pending_incoming" | "friends"


class SearchMemberResponse(BaseModel):
    member_id: str
    nickname: str | None
    user_number: str
    friendship_status: FriendshipStatus


# 022-member-personal-settings research.md #4: allow-list lives in code (not
# a DB CHECK constraint) so a future language needs no migration (FR-004).
# 024-add-english-language: added "en" — no migration needed (research.md #1).
SUPPORTED_LANGUAGES = ("zh-TW", "en")


class SupportedLanguagesResponse(BaseModel):
    languages: tuple[str, ...] = SUPPORTED_LANGUAGES


class SetLanguagePreferenceRequest(BaseModel):
    """`language` is intentionally NOT validated here against
    `SUPPORTED_LANGUAGES` — unlike a plain shape error, an unsupported
    language gets its own semantic `LANGUAGE_NOT_SUPPORTED` error code
    (contracts/member-settings-api.md), which requires raising `ApiError`
    from `service.set_language_preference()` rather than a Pydantic
    validator (those only ever surface as the generic `VALIDATION_ERROR`)."""

    language: str


class PrivacySettingsRequest(BaseModel):
    allow_search: bool | None = None
    share_match_records_with_friends: bool | None = None
    allow_friend_invite_from_match_pages: bool | None = None

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> "PrivacySettingsRequest":
        if (
            self.allow_search is None
            and self.share_match_records_with_friends is None
            and self.allow_friend_invite_from_match_pages is None
        ):
            raise ValueError("at least one privacy field must be provided")
        return self


class PrivacySettingsResponse(BaseModel):
    allow_search: bool
    share_match_records_with_friends: bool
    allow_friend_invite_from_match_pages: bool


class LoginRecordSummary(BaseModel):
    created_at: datetime
    device_category: str


class LoginRecordsResponse(BaseModel):
    records: list[LoginRecordSummary]
    page: int
    total_pages: int


# 034-clutch-points-player-dashboard: the cross-match technique dashboard
# (member/player_dashboard.py). Same convention as the match detail's derived
# blocks — None / [] IS the "no data" signal, never an all-zero structure.
class DashboardMetricValue(BaseModel):
    # None with matches_used > 0: applies, but the denominator is 0 (e.g.
    # never trailed) — shown as "0/0 —", never as 0%.
    value: float | None
    numerator: int
    denominator: int
    matches_used: int


class DashboardMetric(BaseModel):
    key: str
    kind: Literal["rate", "average", "ratio"]
    better_when: Literal["higher", "lower"] | None
    all: DashboardMetricValue | None  # None: no match has this metric's data
    recent: DashboardMetricValue | None  # None: no comparison is shown
    verdict: Literal["improved", "declined", "unchanged", "insufficient"] | None


class DashboardTrendPoint(BaseModel):
    from_ended_at: datetime
    to_ended_at: datetime
    value: float | None
    numerator: int
    denominator: int


class DashboardTrend(BaseModel):
    key: str
    points: list[DashboardTrendPoint]  # oldest first


class DashboardLanding(BaseModel):
    # Newest match first and already turned so the member's own side is on
    # the left (x < 0.5): the recent window is scored[:recent_scored_count].
    scored: list[tuple[float, float]]
    lost: list[tuple[float, float]]
    scored_total: int
    lost_total: int
    matches_used: int
    recent_scored_count: int
    recent_lost_count: int
    recent_scored_total: int
    recent_lost_total: int
    recent_matches_used: int


class DashboardErrorBreakdown(BaseModel):
    """035-point-ending-type: the member's own errors by kind. `recent` is
    None whenever there is no comparison (total_matches <= recent_window),
    mirroring every metric's `recent`."""

    all: ErrorsByType
    recent: ErrorsByType | None


# 036-match-insights-benchmarks US1 (member/insights.py): a rule code plus the
# numbers behind it — never a sentence (Constitution VIII); the frontend owns
# the wording. The Literal sets mirror `insights.py`; a unit test compares them.
InsightRule = Literal[
    "rate_vs_overall",
    "deuce_vs_even",
    "error_share_high",
    "winner_share_high",
    "recent_change",
    "partner_above_overall",
    "opponent_below_overall",
    "benchmark_quartile",
]


class DashboardInsightPlayer(BaseModel):
    key: str
    nickname: str
    member_id: str | None


class DashboardInsight(BaseModel):
    rule: InsightRule
    level: Literal["strong", "mild"]
    source: Literal["benchmark", "self", "trend", "matchup"]
    metric_key: str | None
    player: DashboardInsightPlayer | None
    params: dict[str, float | int | str | None]
    # Declared last: a field called `list` shadows the builtin for every
    # annotation below it in this class body.
    list: Literal["strength", "weakness", "recent", "matchup"]


class DashboardInsights(BaseModel):
    # insufficient_data: no rule had enough to go on; balanced: some did and
    # nothing stood out. Either way all four lists are empty.
    status: Literal["ok", "insufficient_data", "balanced"] = "insufficient_data"
    # Set only by the group-benchmark endpoint, whose insights merge in the
    # in-group source; always None on the dashboard endpoints (FR-037).
    benchmark_group_name: str | None = None
    strengths: list[DashboardInsight] = []
    weaknesses: list[DashboardInsight] = []
    recent: list[DashboardInsight] = []
    matchups: list[DashboardInsight] = []


class MemberMatchDashboardResponse(BaseModel):
    total_matches: int
    recent_window: int
    has_comparison: bool
    # [] iff total_matches == 0, else all 23 (034's 18 + 035's 5, appended).
    metrics: list[DashboardMetric]
    trends: list[DashboardTrend]
    landing: DashboardLanding | None
    # 035: None when not one of the member's errors was ever recorded.
    error_breakdown: DashboardErrorBreakdown | None = None
    # 036: follows the same filters as `metrics` (FR-019).
    insights: DashboardInsights = DashboardInsights()


# 036-match-insights-benchmarks US3: the in-group comparison
# (member/group_benchmark.py).
class BenchmarkGroupOption(BaseModel):
    group_id: str
    group_number: int
    name: str
    status: str  # the group's own status (active / disbanded)
    member_status: Literal["active", "left", "kicked"]  # mine, as in 014's 我的團
    my_completed_matches: int


class BenchmarkGroupsResponse(BaseModel):
    # Most of my matches first; the first one is the default choice (FR-027).
    groups: list[BenchmarkGroupOption]


class GroupBenchmarkGroup(BaseModel):
    group_id: str
    name: str


class GroupBenchmarkMetric(BaseModel):
    """ANONYMOUS BY SHAPE (FR-032, Clarifications 2026-09-18): there is no
    field here that could carry another player's name, key or individual
    value — so there is nothing for a handler to forget to strip, and Pydantic
    drops anything that is not declared. Do not add a per-player list to this
    model without revisiting that decision.

    The pure result's `rank_from_bottom` is deliberately absent: it exists for
    `insights` only."""

    key: str
    kind: Literal["rate", "average", "ratio"]
    better_when: Literal["higher", "lower"] | None
    mine: DashboardMetricValue | None  # my value over THIS group's matches only
    status: Literal["ok", "pool_too_small", "self_below_minimum", "no_direction"]
    group_average: float | None
    pool_size: int
    rank: int | None


class GroupBenchmarkResponse(BaseModel):
    group: GroupBenchmarkGroup
    total_matches: int  # every completed match of the group: the fixed range (FR-028)
    my_matches: int
    metrics: list[GroupBenchmarkMetric]  # all 23, dashboard order
    # My UNFILTERED cross-group summary with the in-group source merged in by
    # the same `insights.derive()` — the page shows this instead of the
    # dashboard's own insights while no filter is active (FR-033, FR-034).
    insights: DashboardInsights


# 036-match-insights-benchmarks US4: a friend's numbers next to mine.
class ComparisonMetric(BaseModel):
    key: str
    kind: Literal["rate", "average", "ratio"]
    better_when: Literal["higher", "lower"] | None
    friend: DashboardMetricValue | None
    me: DashboardMetricValue | None
    # None: no direction, or either side has no value / fewer than 3 matches
    # behind it — never a verdict on a sample that thin (US4-2).
    better: Literal["me", "friend", "tie"] | None


class HeadToHeadTally(BaseModel):
    """From the VIEWER's side: `wins` are mine, `avg_margin` mine minus theirs."""

    matches: int
    wins: int
    losses: int
    win_rate: float
    avg_margin: float


class HeadToHeadResponse(BaseModel):
    as_opponents: HeadToHeadTally | None  # None: never played against each other
    as_partners: HeadToHeadTally | None  # None: never partnered


class MatchComparisonResponse(BaseModel):
    friend_total_matches: int
    my_total_matches: int
    metrics: list[ComparisonMetric]  # all 23, dashboard order, unfiltered
    head_to_head: HeadToHeadResponse

