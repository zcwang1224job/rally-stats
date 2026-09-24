"""sport type plugin foundation (043)

Revision ID: a3f0c2d91e47
Revises: b7e2d4a9c130
Create Date: 2026-09-24 00:00:00.000000

043-sport-type-plugin-foundation data-model §2–§6. Every group and match that
already exists becomes a badminton ("net_rally") one with exactly the rules it
had; every new NOT NULL column carries a server default so raw-SQL inserts in
old code paths and tests keep working (research F6).

- groups / matches: sport + common parameters (team_size, end_mode, win_by,
  allow_draw, score_steps, type_params), cap_score nullable. groups.team_size
  is backfilled from match_mode; matches.team_size from the participant count.
- score_events: the match event spine gains `kind` ('point' for every
  existing row) and `side` becomes nullable for non-scoring events.
- member_sports: members' custom activities (built-ins live in code,
  app/sports/catalog.py — research Decision 5).
- system_config: per-sport default group-name suffix and court name.

The frames plugin's own tables are created by that plugin's migration, not
here (contracts/plugin-boundary.md §5).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3f0c2d91e47'
down_revision: Union[str, None] = 'b7e2d4a9c130'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SYSTEM_CONFIG_ROWS: tuple[tuple[str, str, str], ...] = (
    ("default_group_name_suffix.table_tennis", "的桌球團", "預設團名後綴：桌球"),
    ("default_group_name_suffix.pickleball", "的匹克球團", "預設團名後綴：匹克球"),
    ("default_group_name_suffix.tennis_tiebreak", "的網球團", "預設團名後綴：網球（搶十）"),
    ("default_group_name_suffix.billiards", "的撞球團", "預設團名後綴：撞球"),
    ("default_group_name_suffix.darts", "的飛鏢團", "預設團名後綴：飛鏢"),
    ("default_group_name_suffix.board_game", "的桌遊團", "預設團名後綴：桌遊"),
    ("default_group_name_suffix.esports", "的電競團", "預設團名後綴：電競"),
    ("default_group_name_suffix.other", "的團", "預設團名後綴：其他／自訂活動"),
    ("default_court_name.table_tennis", "球桌一", "預設場地名稱：桌球"),
    ("default_court_name.pickleball", "球場一", "預設場地名稱：匹克球"),
    ("default_court_name.tennis_tiebreak", "球場一", "預設場地名稱：網球（搶十）"),
    ("default_court_name.billiards", "球桌一", "預設場地名稱：撞球"),
    ("default_court_name.darts", "靶台一", "預設場地名稱：飛鏢"),
    ("default_court_name.board_game", "棋桌一", "預設場地名稱：桌遊"),
    ("default_court_name.esports", "機台一", "預設場地名稱：電競"),
    ("default_court_name.other", "場地一", "預設場地名稱：其他／自訂活動"),
)


def _common_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("sport_key", sa.String(32), nullable=False, server_default="badminton"),
        sa.Column("type_key", sa.String(16), nullable=False, server_default="net_rally"),
        sa.Column("sport_name", sa.String(20), nullable=True),
        sa.Column("team_size", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("end_mode", sa.String(8), nullable=False, server_default="target"),
        sa.Column("win_by", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("allow_draw", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "score_steps",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[1]'::jsonb"),
        ),
        sa.Column(
            "type_params",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "member_sports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(20), nullable=False),
        sa.Column("type_key", sa.String(16), nullable=False),
        sa.Column("team_size_options", postgresql.JSONB(), nullable=False),
        sa.Column("defaults", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("member_id", "name", name="uq_member_sports_member_name"),
    )
    op.create_index("ix_member_sports_member_id", "member_sports", ["member_id"])

    for column in _common_columns():
        op.add_column("groups", column)
    op.add_column(
        "groups",
        sa.Column(
            "custom_sport_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("member_sports.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute("UPDATE groups SET team_size = 2 WHERE match_mode = 'doubles'")
    op.alter_column("groups", "cap_score", existing_type=sa.Integer(), nullable=True)

    for column in _common_columns():
        op.add_column("matches", column)
    op.execute(
        "UPDATE matches SET team_size = 2 WHERE id IN ("
        "  SELECT match_id FROM match_participants GROUP BY match_id HAVING count(*) > 2"
        ")"
    )
    op.alter_column("matches", "cap_score", existing_type=sa.Integer(), nullable=True)

    op.add_column(
        "score_events",
        sa.Column("kind", sa.String(24), nullable=False, server_default="point"),
    )
    op.alter_column("score_events", "side", existing_type=sa.String(1), nullable=True)

    values = ", ".join(
        f"('{key}', '{value}', '{description}')" for key, value, description in _SYSTEM_CONFIG_ROWS
    )
    op.execute(
        f"INSERT INTO system_config (key, value, description) VALUES {values} "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    keys = ", ".join(f"'{key}'" for key, _, _ in _SYSTEM_CONFIG_ROWS)
    op.execute(f"DELETE FROM system_config WHERE key IN ({keys})")

    # Non-scoring spine events have no pre-043 meaning.
    op.execute("DELETE FROM score_events WHERE kind <> 'point'")
    op.alter_column("score_events", "side", existing_type=sa.String(1), nullable=False)
    op.drop_column("score_events", "kind")

    # Matches/groups created after the upgrade may have no cap; give them the
    # smallest cap that never ends a match earlier than their own rule would.
    op.execute("UPDATE matches SET cap_score = 2 * target_score WHERE cap_score IS NULL")
    op.alter_column("matches", "cap_score", existing_type=sa.Integer(), nullable=False)
    for column in reversed(_common_columns()):
        op.drop_column("matches", column.name)

    op.execute("UPDATE groups SET cap_score = 2 * target_score WHERE cap_score IS NULL")
    op.alter_column("groups", "cap_score", existing_type=sa.Integer(), nullable=False)
    op.drop_column("groups", "custom_sport_id")
    for column in reversed(_common_columns()):
        op.drop_column("groups", column.name)

    op.drop_index("ix_member_sports_member_id", table_name="member_sports")
    op.drop_table("member_sports")
