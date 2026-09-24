"""Group entity — includes embedded Match Scoring Settings and Admin Credential
fields, per specs/001-create-manage-group/data-model.md §1–3."""

import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Sequence,
    SmallInteger,
    String,
    Time,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.sql import func

from app.core.db import Base

# groups.custom_sport_id references member_sports: the table has to be on
# Base.metadata whenever Group is flushed.
from app.domains.member.sports_models import MemberSport  # noqa: F401

group_number_seq = Sequence("group_number_seq", start=100000, increment=1)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_number: Mapped[int] = mapped_column(
        BigInteger,
        group_number_seq,
        server_default=group_number_seq.next_value(),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(String(30), nullable=False)

    password_ciphertext: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    password_nonce: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)

    max_members: Mapped[int] = mapped_column(Integer, nullable=False)
    match_mode: Mapped[str] = mapped_column(String(8), nullable=False)  # singles | doubles
    scheduling_mechanism: Mapped[str] = mapped_column(String(16), nullable=False)
    # fair_rotation | fixed_partner | individual_mixed | manual

    activity_time_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    activity_time_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    current_member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # active | disbanded

    # Nullable — NULL for every group that is still active, and for groups
    # disbanded before this column existed (backfilling those is not
    # possible; their disband time was never recorded).
    disbanded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    last_activity_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True, index=True
    )

    admin_pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    admin_failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    admin_locked_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    admin_token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    base_settings_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    join_link_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    all_courts_link_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    join_link_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, unique=True
    )
    all_courts_control_panel_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, unique=True
    )

    # Match Scoring Settings (embedded, see data-model.md §2)
    scoring_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="21pt")
    # 21pt | 15pt | custom
    target_score: Mapped[int] = mapped_column(Integer, nullable=False, default=21)
    deuce_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    # 043: nullable — no cap means only the win_by lead ends a match (FR-016).
    cap_score: Mapped[int | None] = mapped_column(Integer, nullable=True, default=30)

    current_round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    auto_next_round: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # fair_rotation doubles only: when a court frees up and nothing is queued,
    # immediately seat the four longest-waiting idle players there, instead
    # of leaving the court empty until every court's match ends and the next
    # round is generated. A plain immediate toggle like auto_next_round.
    continuous_rotation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 018-plan-then-start follow-up: off by default — the scoreboard link is
    # typically shared more widely (posted for spectators) than the
    # control-panel link, so letting it also score is an admin-opt-in widening
    # of who can mutate scores, not a client-side/per-device preference.
    scoreboard_scoring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 031-shot-placement-scoring: group-level opt-in for the "tap the court,
    # pick the scoring player" interaction in place of the plain +1 button.
    # Same "plain immediate toggle" shape as scoreboard_scoring_enabled above
    # (research.md Decision 5) — not part of the optimistic-locked Match
    # Scoring Settings form, since it's a single independent boolean.
    detailed_scoring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 011-round-robin-scheduling: only meaningful when scheduling_mechanism ==
    # "fixed_partner" — "manual" reads the partnerships table (existing
    # admin-configured pairs); "auto" recomputes teams fresh each round
    # without ever writing to partnerships (research.md #6).
    partner_source: Mapped[str] = mapped_column(String(8), nullable=False, default="manual")
    # manual | auto

    # 043-sport-type-plugin-foundation (data-model §2). Python defaults are the
    # badminton values every pre-043 group was migrated to, so code and tests
    # that build Group() without a sport keep getting a badminton group.
    # sport_key / type_key / sport_name / custom_sport_id are immutable once
    # the group exists (FR-007, enforced by edit_group).
    sport_key: Mapped[str] = mapped_column(String(32), nullable=False, default="badminton")
    type_key: Mapped[str] = mapped_column(String(16), nullable=False, default="net_rally")
    sport_name: Mapped[str | None] = mapped_column(String(20), nullable=True)
    custom_sport_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("member_sports.id", ondelete="SET NULL"), nullable=True
    )
    # Players per team. Supersedes match_mode (research Decision 6): the two
    # are kept in step by the validators below, so either can be written.
    team_size: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    end_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="target")
    # target | manual
    win_by: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    allow_draw: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score_steps: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, default=lambda: [1]
    )
    # Sport-type-specific parameters, validated by the type's plugin
    # (params_schema()) on create/edit; core only stores and snapshots them.
    type_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    def __init__(self, **kwargs: Any) -> None:
        match_mode = kwargs.get("match_mode")
        team_size = kwargs.get("team_size")
        if match_mode is not None and team_size is not None:
            if team_size_for_match_mode(match_mode) != team_size:
                raise ValueError(
                    f"match_mode={match_mode!r} contradicts team_size={team_size!r}"
                )
        super().__init__(**kwargs)

    # Each validator writes the other column; the flag stops the second write
    # from bouncing back (a validator runs before its own value is stored).
    # Deliberately unannotated: a plain class attribute, not a mapped column.
    _syncing_team_size = False

    @validates("match_mode")
    def _sync_team_size(self, _key: str, value: str) -> str:
        size = team_size_for_match_mode(value)
        if not self._syncing_team_size:
            self._syncing_team_size = True
            try:
                self.team_size = size
            finally:
                self._syncing_team_size = False
        return value

    @validates("team_size")
    def _sync_match_mode(self, _key: str, value: int) -> int:
        mode = match_mode_for_team_size(value)
        if not self._syncing_team_size:
            self._syncing_team_size = True
            try:
                self.match_mode = mode
            finally:
                self._syncing_team_size = False
        return value


def team_size_for_match_mode(match_mode: str) -> int:
    """043 research Decision 6: singles ↔ 1, doubles ↔ 2."""
    if match_mode == "singles":
        return 1
    if match_mode == "doubles":
        return 2
    raise ValueError(f"unknown match_mode {match_mode!r}")


def match_mode_for_team_size(team_size: int) -> str:
    """Inverse of team_size_for_match_mode(); this release allows 1 or 2."""
    if team_size == 1:
        return "singles"
    if team_size == 2:
        return "doubles"
    raise ValueError(f"team_size {team_size!r} is not supported yet (1 or 2)")


class RoundHistory(Base):
    """005-member-view research.md #1/#2: written once per round generated
    (including round 1) by 003's `generate_next_round()`, read-only for this
    feature's "已離開" (left) state determination."""

    __tablename__ = "round_history"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )
    round_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
