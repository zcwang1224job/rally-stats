"""043-sport-type-plugin-foundation data-model §5: members' custom activities.

Built-in activities are code constants (app/sports/catalog.py, research
Decision 5); only what a member defines lives here. Deleting a row leaves the
groups that used it untouched: they keep their own `sport_name` snapshot and
`custom_sport_id` goes NULL.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

# FR-003: at most this many custom activities per member.
MAX_CUSTOM_SPORTS_PER_MEMBER = 20


class MemberSport(Base):
    __tablename__ = "member_sports"
    __table_args__ = (UniqueConstraint("member_id", "name", name="uq_member_sports_member_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    type_key: Mapped[str] = mapped_column(String(16), nullable=False)
    team_size_options: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    # {team_size, end_mode, target_score, win_by, cap_score, allow_draw,
    #  score_steps, type_params, nouns}
    defaults: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
