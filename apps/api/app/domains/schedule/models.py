"""Match, MatchParticipant, PairHistory, Partnership — per
specs/003-schedule-rotation/data-model.md §1-4."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    court_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courts.id"), nullable=True, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # queued | in_progress | completed | abandoned
    score_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_b: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winner_team: Mapped[str | None] = mapped_column(String(1), nullable=True)

    # Match Scoring Settings snapshot (copied from groups at creation time)
    target_score: Mapped[int] = mapped_column(Integer, nullable=False)
    deuce_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    cap_score: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # 030-score-serve-record: persistent "serve state", initialized once the
    # match becomes in_progress (_initialize_serve_state()) and advanced on
    # every scoring +1 (_advance_serve_state_and_snapshot()) — NULL until
    # then, and never backfilled for matches created before this feature.
    # `-1` (score corrections) MUST NOT touch these three columns.
    serving_team: Mapped[str | None] = mapped_column(String(1), nullable=True)  # 'A' | 'B'
    team_a_reference_server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=True
    )
    team_b_reference_server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=True
    )


class ScoreEvent(Base):
    """One +1/-1 scoring action applied to a match, per apply_score_delta()
    (service.py) — an append-only audit trail alongside Match's running
    score_a/score_b totals."""

    __tablename__ = "score_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    side: Mapped[str] = mapped_column(String(1), nullable=False)  # 'A' | 'B'
    delta: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 | -1
    score_a: Mapped[int] = mapped_column(Integer, nullable=False)  # resulting totals
    score_b: Mapped[int] = mapped_column(Integer, nullable=False)
    # which control surface issued the action: control_panel | admin |
    # all_courts | scoreboard (018-plan-then-start follow-up — only reachable
    # once a group opts into `scoreboard_scoring_enabled`)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ScoreServeRecord(Base):
    """030-score-serve-record: a snapshot of "who served this point and
    where everyone stood", written once per +1 ScoreEvent (never for -1,
    per Clarifications) in the same transaction as that ScoreEvent —
    immutable afterwards, no code path ever UPDATEs an existing row.
    Station formula: apps/api/app/domains/schedule/service.py
    `_compute_station()`; per specs/030-score-serve-record/data-model.md."""

    __tablename__ = "score_serve_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    score_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("score_events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized from match.group_id, same rationale as ScoreEvent.group_id
    # — lets a future group-scoped query filter this table directly instead
    # of joining through matches.
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    server_roster_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=False
    )
    server_team: Mapped[str] = mapped_column(String(1), nullable=False)  # 'A' | 'B'
    # Station slots — nullable because singles occupies exactly one of the
    # two slots per team (data-model.md validation rules); application-level
    # invariant, not a DB CHECK constraint (same convention as
    # member.language_preference's allow-list living in code).
    team_a_right_roster_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=True
    )
    team_a_left_roster_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=True
    )
    team_b_right_roster_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=True
    )
    team_b_left_roster_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class MatchParticipant(Base):
    __tablename__ = "match_participants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    roster_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=False, index=True
    )
    team: Mapped[str] = mapped_column(String(1), nullable=False)  # 'A' | 'B'


class PairHistory(Base):
    __tablename__ = "pair_history"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )
    player_lo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), primary_key=True
    )
    player_hi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), primary_key=True
    )
    pair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Partnership(Base):
    __tablename__ = "partnerships"
    __table_args__ = (CheckConstraint("player_a_id <> player_b_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    player_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=False, unique=True
    )
    player_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
